#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# ///

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

PACKAGES_URL = "https://raw.githubusercontent.com/nim-lang/packages/master/packages.json"
BASE_DIR = os.getcwd()
DEFAULT_GITHUB_PAGES_BRANCH = "gh-pages"
REMOTE_INDEX_NAME = "index.json"
REMOTE_PACKAGES_DIR = "packages"
DEFAULT_DATA_REPO_SLUG = "mkalmousli/NimArchiveData"
DEFAULT_DATA_REPO_BRANCH = "main"


def ensure_dir(directory):
    if directory and not os.path.exists(directory):
        os.makedirs(directory)


def get_json(path, default=None):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default if default is not None else {}
    return default if default is not None else {}


def save_json(path, data):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def calculate_file_hash(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def calculate_md5(filepath):
    md5_hash = hashlib.md5()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            md5_hash.update(byte_block)
    return md5_hash.hexdigest()


def create_archive(source_path, target_path):
    try:
        with tarfile.open(target_path, "w:gz", compresslevel=9) as tar:
            for item in os.listdir(source_path):
                item_path = os.path.join(source_path, item)
                tar.add(item_path, arcname=item)
        return True
    except Exception as e:
        logging.error("Compression failed: %s", e)
        return False


def collect_archive_files(root_path):
    files = {}
    for current_root, _, file_names in os.walk(root_path):
        for file_name in sorted(file_names):
            path = os.path.join(current_root, file_name)
            relative_path = os.path.relpath(path, root_path).replace(os.sep, "/")
            files[relative_path] = path
    return files


def copy_tree(src, dst):
    ensure_dir(dst)
    for entry in os.listdir(src):
        src_path = os.path.join(src, entry)
        dst_path = os.path.join(dst, entry)
        if os.path.isdir(src_path):
            shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
        else:
            shutil.copy2(src_path, dst_path)


def run_command(args, cwd=None, check=True, capture_output=False, text=True):
    return subprocess.run(args, cwd=cwd, check=check, capture_output=capture_output, text=text)


def configure_git_identity(repo_dir):
    user_name = os.environ.get("GIT_COMMITTER_NAME", "").strip() or os.environ.get("GITHUB_ACTOR", "").strip() or "github-actions[bot]"
    user_email = os.environ.get("GIT_COMMITTER_EMAIL", "").strip() or "41898282+github-actions[bot]@users.noreply.github.com"
    run_command(["git", "config", "user.name", user_name], cwd=repo_dir)
    run_command(["git", "config", "user.email", user_email], cwd=repo_dir)


def should_update_github_pages():
    return os.environ.get("SKIP_GITHUB_PAGES", "").strip().lower() not in {"1", "true", "yes"}


def update_github_pages_branch():
    if not should_update_github_pages():
        logging.info("GitHub Pages update skipped by configuration.")
        return

    site_dir = os.path.join(BASE_DIR, "site")
    site_index = os.path.join(site_dir, "index.html")
    if not os.path.isdir(site_dir) or not os.path.isfile(site_index):
        logging.info("GitHub Pages update skipped: site/ is missing or incomplete.")
        return

    branch = os.environ.get("GITHUB_PAGES_BRANCH", DEFAULT_GITHUB_PAGES_BRANCH).strip() or DEFAULT_GITHUB_PAGES_BRANCH
    worktree_dir = tempfile.mkdtemp(prefix="github_pages_")
    worktree_added = False

    try:
        run_command(["git", "rev-parse", "--is-inside-work-tree"], cwd=BASE_DIR, capture_output=True)

        local_branch_exists = run_command(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            cwd=BASE_DIR,
            check=False,
        ).returncode == 0
        remote_branch_exists = run_command(
            ["git", "ls-remote", "--exit-code", "--heads", "origin", branch],
            cwd=BASE_DIR,
            check=False,
            capture_output=True,
        ).returncode == 0

        if local_branch_exists:
            run_command(["git", "worktree", "add", "--force", worktree_dir, branch], cwd=BASE_DIR)
        elif remote_branch_exists:
            run_command(["git", "worktree", "add", "--track", "-b", branch, worktree_dir, f"origin/{branch}"], cwd=BASE_DIR)
        else:
            run_command(["git", "worktree", "add", "--detach", worktree_dir, "HEAD"], cwd=BASE_DIR)
            run_command(["git", "checkout", "--orphan", branch], cwd=worktree_dir)
        worktree_added = True

        for entry in os.listdir(worktree_dir):
            if entry == ".git":
                continue
            entry_path = os.path.join(worktree_dir, entry)
            if os.path.isdir(entry_path):
                shutil.rmtree(entry_path)
            else:
                os.remove(entry_path)

        shutil.copy2(site_index, os.path.join(worktree_dir, "index.html"))
        copy_tree(site_dir, os.path.join(worktree_dir, "site"))
        open(os.path.join(worktree_dir, ".nojekyll"), "w").close()
        with open(os.path.join(worktree_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write("# Nim Packages Archive Site\n\nThis branch contains the static site build for GitHub Pages.\n")

        run_command(["git", "add", "."], cwd=worktree_dir)
        has_changes = run_command(["git", "diff", "--cached", "--quiet"], cwd=worktree_dir, check=False).returncode != 0
        if not has_changes:
            logging.info("GitHub Pages branch is already up to date.")
            return

        configure_git_identity(worktree_dir)
        run_command(["git", "commit", "-m", "chore: update GitHub Pages site"], cwd=worktree_dir)
        if run_command(["git", "remote", "get-url", "origin"], cwd=BASE_DIR, check=False, capture_output=True).returncode == 0:
            run_command(["git", "push", "-u", "origin", branch], cwd=worktree_dir)
        logging.info("GitHub Pages branch updated: %s", branch)
    finally:
        if worktree_added:
            run_command(["git", "worktree", "remove", "--force", worktree_dir], cwd=BASE_DIR, check=False)
        if os.path.exists(worktree_dir):
            shutil.rmtree(worktree_dir, ignore_errors=True)


def build_github_repo_url(repo_slug, token=None):
    if token:
        return f"https://x-access-token:{token}@github.com/{repo_slug}.git"
    return f"https://github.com/{repo_slug}.git"


class GitRepoStore:
    def __init__(self):
        self.repo_slug = os.environ.get("DATA_REPO_SLUG", DEFAULT_DATA_REPO_SLUG).strip() or DEFAULT_DATA_REPO_SLUG
        self.branch = os.environ.get("DATA_REPO_BRANCH", DEFAULT_DATA_REPO_BRANCH).strip() or DEFAULT_DATA_REPO_BRANCH
        self.push_token = os.environ.get("DATA_REPO_PUSH_TOKEN", "").strip()
        self.clone_url = os.environ.get("DATA_REPO_CLONE_URL", "").strip() or build_github_repo_url(self.repo_slug)
        self.push_url = os.environ.get("DATA_REPO_PUSH_URL", "").strip() or build_github_repo_url(self.repo_slug, self.push_token or None)
        self.temp_dir = tempfile.mkdtemp(prefix="archive_data_repo_")
        self.repo_dir = os.path.join(self.temp_dir, "repo")
        self.lock = threading.Lock()
        self._clone_or_init_repo()
        self.index = self.load_json(REMOTE_INDEX_NAME, {})

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _clone_or_init_repo(self):
        branch_exists = run_command(
            ["git", "ls-remote", "--exit-code", "--heads", self.clone_url, self.branch],
            check=False,
            capture_output=True,
        ).returncode == 0

        if branch_exists:
            run_command(["git", "clone", "--branch", self.branch, "--single-branch", self.clone_url, self.repo_dir])
        else:
            clone_result = run_command(["git", "clone", self.clone_url, self.repo_dir], check=False, capture_output=True)
            if clone_result.returncode != 0:
                ensure_dir(self.repo_dir)
                run_command(["git", "init", "-b", self.branch], cwd=self.repo_dir)
                run_command(["git", "remote", "add", "origin", self.clone_url], cwd=self.repo_dir)
            elif run_command(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{self.branch}"], cwd=self.repo_dir, check=False).returncode == 0:
                run_command(["git", "checkout", self.branch], cwd=self.repo_dir)
            else:
                run_command(["git", "checkout", "--orphan", self.branch], cwd=self.repo_dir)

        configure_git_identity(self.repo_dir)
        run_command(["git", "remote", "set-url", "--push", "origin", self.push_url], cwd=self.repo_dir, check=False)

    def load_json(self, remote_name, default=None):
        with self.lock:
            return get_json(os.path.join(self.repo_dir, remote_name), default)

    def get_index_snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.index))

    def reserve_package_id(self, name, pkg_type, url, license_name):
        with self.lock:
            if name in self.index:
                return self.index[name]["id"], False

            existing_ids = {entry["id"] for entry in self.index.values() if isinstance(entry, dict) and "id" in entry}
            proposed_id = name
            counter = 1
            while proposed_id in existing_ids:
                proposed_id = f"{name}{counter}"
                counter += 1

            self.index[name] = {
                "id": proposed_id,
                "type": pkg_type,
                "url": url,
                "license": license_name,
                "added_at": int(time.time()),
            }
            save_json(os.path.join(self.repo_dir, REMOTE_INDEX_NAME), self.index)
            return proposed_id, True

    def _commit_and_push(self, message):
        run_command(["git", "add", "."], cwd=self.repo_dir)
        if run_command(["git", "diff", "--cached", "--quiet"], cwd=self.repo_dir, check=False).returncode == 0:
            return False
        run_command(["git", "commit", "-m", message], cwd=self.repo_dir)
        run_command(["git", "push", "-u", "origin", self.branch], cwd=self.repo_dir)
        return True

    def upload_index_snapshot(self, package_name):
        with self.lock:
            save_json(os.path.join(self.repo_dir, REMOTE_INDEX_NAME), self.index)
            changed = self._commit_and_push(f"chore: register package {package_name}")
        if changed:
            logging.info("Pushed index.json after discovering package %s.", package_name)
        return changed

    def get_next_id(self, remote_name, key):
        data = self.load_json(remote_name, {key: []})
        numeric_ids = [int(value) for value in data.get(key, []) if str(value).isdigit()]
        return str(max(numeric_ids) + 1) if numeric_ids else "0"

    def remote_file_present(self, remote_name):
        return os.path.exists(os.path.join(self.repo_dir, remote_name))

    def load_snapshot_metadata(self, remote_snapshot_dir):
        return self.load_json(f"{remote_snapshot_dir}/metadata.json", {})

    def snapshot_is_complete(self, remote_snapshot_dir, metadata):
        if not metadata:
            return False

        required_files = [
            f"{remote_snapshot_dir}/metadata.json",
            f"{remote_snapshot_dir}/source.tar.gz",
        ]
        if metadata.get("readme"):
            required_files.append(f"{remote_snapshot_dir}/{metadata['readme']}")
        if metadata.get("license"):
            required_files.append(f"{remote_snapshot_dir}/{metadata['license']}")
        return all(self.remote_file_present(path) for path in required_files)

    def upload_tree(self, root_path, package_name):
        local_files = collect_archive_files(root_path)
        if not local_files:
            logging.info("Data repo sync skipped for %s: no files generated.", package_name)
            return 0

        with self.lock:
            changed_items = []
            for remote_name, local_path in local_files.items():
                target_path = os.path.join(self.repo_dir, remote_name)
                source_md5 = calculate_md5(local_path)
                if os.path.exists(target_path) and calculate_md5(target_path) == source_md5:
                    continue
                ensure_dir(os.path.dirname(target_path))
                shutil.copy2(local_path, target_path)
                changed_items.append(remote_name)

            if not changed_items:
                logging.info("Data repo sync skipped for %s: no changed files.", package_name)
                return 0

            changed = self._commit_and_push(f"chore: archive {package_name}")

        if changed:
            logging.info("Saved package %s into %s (%s files).", package_name, self.repo_slug, len(changed_items))
            return len(changed_items)
        return 0


class Archiver:
    def __init__(self, store):
        self.store = store

    def _select_snapshot_id(self, remote_parent_dir, history_key, latest_id, commit):
        if latest_id:
            latest_remote_dir = f"{remote_parent_dir}/{latest_id}"
            latest_meta = self.store.load_snapshot_metadata(latest_remote_dir)
            if latest_meta.get("commit") == commit:
                return latest_id, not self.store.snapshot_is_complete(latest_remote_dir, latest_meta)
            if not latest_meta:
                return latest_id, True

        history = self.store.load_json(f"{remote_parent_dir}/all.json", {history_key: []})
        for snapshot_id in history.get(history_key, []):
            remote_snapshot_dir = f"{remote_parent_dir}/{snapshot_id}"
            metadata = self.store.load_snapshot_metadata(remote_snapshot_dir)
            if metadata.get("commit") == commit:
                return snapshot_id, not self.store.snapshot_is_complete(remote_snapshot_dir, metadata)

        return self.store.get_next_id(f"{remote_parent_dir}/all.json", history_key), True

    def archive_git_repo(self, name, url, license_name):
        pkg_id, is_new_package = self.store.reserve_package_id(name, "git", url, license_name)
        if is_new_package:
            self.store.upload_index_snapshot(name)

        with tempfile.TemporaryDirectory(prefix=f"archiver_{name}_") as temp_dir:
            repo_path = os.path.join(temp_dir, "repo")
            upload_root = os.path.join(temp_dir, "upload")
            package_root = os.path.join(upload_root, REMOTE_PACKAGES_DIR, pkg_id)

            logging.info("Cloning %s...", name)
            try:
                subprocess.run(["git", "clone", "--mirror", url, repo_path], check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                logging.error("Clone failed for %s: %s", name, e.stderr.decode())
                return False

            self._process_branch(repo_path, pkg_id, package_root, "HEAD", temp_dir)
            self._process_tags(repo_path, pkg_id, package_root, temp_dir)
            saved_files = self.store.upload_tree(upload_root, name)
            logging.info("Package %s synced into data repo after %s changed file(s).", name, saved_files)
        return True

    def _process_branch(self, repo_path, pkg_id, package_root, branch, temp_dir):
        code_dir = os.path.join(package_root, "code")
        remote_code_dir = f"{REMOTE_PACKAGES_DIR}/{pkg_id}/code"
        ensure_dir(code_dir)

        try:
            commit = subprocess.run(["git", "-C", repo_path, "rev-parse", branch], capture_output=True, text=True, check=True).stdout.strip()
        except subprocess.CalledProcessError:
            return False

        latest_data = self.store.load_json(f"{remote_code_dir}/latest.json", {})
        latest_code_id = latest_data.get("code")
        code_id, needs_archive = self._select_snapshot_id(remote_code_dir, "codes", latest_code_id, commit)
        target_dir = os.path.join(code_dir, code_id)

        if needs_archive:
            logging.info("Archiving code state for %s (ID: %s)", branch, code_id)
            if not self._do_archive(repo_path, target_dir, commit, temp_dir):
                return False

        save_json(os.path.join(code_dir, "latest.json"), {"code": code_id})
        all_data = self.store.load_json(f"{remote_code_dir}/all.json", {"codes": []})
        if code_id not in all_data["codes"]:
            all_data["codes"].append(code_id)
        save_json(os.path.join(code_dir, "all.json"), all_data)
        return needs_archive

    def _process_tags(self, repo_path, pkg_id, package_root, temp_dir):
        versions_dir = os.path.join(package_root, "versions")
        remote_versions_dir = f"{REMOTE_PACKAGES_DIR}/{pkg_id}/versions"
        ensure_dir(versions_dir)

        try:
            tags_output = subprocess.run(["git", "-C", repo_path, "tag"], capture_output=True, text=True, check=True).stdout.strip()
            tags = tags_output.split("\n") if tags_output else []
        except subprocess.CalledProcessError:
            tags = []

        existing_versions = self.store.load_json(f"{remote_versions_dir}/all.json", {"versions": []})
        latest_tag = None
        for tag in tags:
            if not tag:
                continue
            latest_tag = tag
            tag_dir = os.path.join(versions_dir, tag)
            remote_tag_dir = f"{remote_versions_dir}/{tag}"
            ensure_dir(tag_dir)

            try:
                commit = subprocess.run(["git", "-C", repo_path, "rev-parse", f"{tag}^{{commit}}"], capture_output=True, text=True, check=True).stdout.strip()
            except subprocess.CalledProcessError:
                continue

            t_latest_data = self.store.load_json(f"{remote_tag_dir}/latest.json", {})
            t_latest_id = t_latest_data.get("version_id")

            version_id, needs_archive = self._select_snapshot_id(remote_tag_dir, "versions", t_latest_id, commit)
            if needs_archive:
                logging.info("Archiving tag %s (ID: %s)", tag, version_id)
                if not self._do_archive(repo_path, os.path.join(tag_dir, version_id), commit, temp_dir):
                    continue

            save_json(os.path.join(tag_dir, "latest.json"), {"version_id": version_id})
            t_all_data = self.store.load_json(f"{remote_tag_dir}/all.json", {"versions": []})
            if version_id not in t_all_data["versions"]:
                t_all_data["versions"].append(version_id)
            save_json(os.path.join(tag_dir, "all.json"), t_all_data)

            if tag not in existing_versions["versions"]:
                existing_versions["versions"].append(tag)

        save_json(os.path.join(versions_dir, "all.json"), existing_versions)
        if latest_tag:
            save_json(os.path.join(versions_dir, "latest.json"), {"version": latest_tag})

    def _do_archive(self, repo_path, target_dir, commit, temp_dir):
        ensure_dir(target_dir)
        archive_file = os.path.join(target_dir, "source.tar.gz")
        temp_export = os.path.join(temp_dir, f"export_{hashlib.md5(target_dir.encode()).hexdigest()}")

        try:
            subprocess.run(["git", "clone", repo_path, temp_export], check=True, capture_output=True)
            subprocess.run(["git", "-C", temp_export, "checkout", commit], check=True, capture_output=True)

            readme_file = None
            license_file = None
            for file_name in os.listdir(temp_export):
                lower_name = file_name.lower()
                file_path = os.path.join(temp_export, file_name)
                if not os.path.isfile(file_path):
                    continue
                if not readme_file and lower_name.startswith("readme"):
                    readme_file = file_name
                if not license_file and lower_name.startswith("license"):
                    license_file = file_name

            if readme_file:
                shutil.copy2(os.path.join(temp_export, readme_file), os.path.join(target_dir, "README.md"))
            if license_file:
                shutil.copy2(os.path.join(temp_export, license_file), os.path.join(target_dir, "LICENSE.md"))

            if create_archive(temp_export, archive_file):
                metadata = {
                    "checksum": calculate_file_hash(archive_file),
                    "commit": commit,
                    "archived_at": int(time.time()),
                }
                if readme_file:
                    metadata["readme"] = "README.md"
                if license_file:
                    metadata["license"] = "LICENSE.md"
                save_json(os.path.join(target_dir, "metadata.json"), metadata)
                return True
        finally:
            if os.path.exists(temp_export):
                shutil.rmtree(temp_export)
        return False


def get_worker_count(task_count):
    workers_raw = os.environ.get("ARCHIVER_WORKERS", "").strip()
    if workers_raw:
        return max(1, min(task_count, int(workers_raw)))
    cpu_count = os.cpu_count() or 4
    return max(1, min(task_count, cpu_count * 4))


def process_package(archiver, package_info):
    index, total, pkg = package_info
    name = pkg.get("name")
    url = pkg.get("url")
    method = pkg.get("method")

    if not name or not url:
        return {"name": name or "<missing>", "status": "skipped", "reason": "missing_name_or_url"}

    logging.info("[%s/%s] Processing %s...", index, total, name)

    if method != "git":
        logging.warning("Method %s not supported for %s", method, name)
        return {"name": name, "status": "skipped", "reason": f"unsupported_method:{method}"}

    try:
        success = archiver.archive_git_repo(name, url, pkg.get("license"))
        return {"name": name, "status": "ok" if success else "failed"}
    except Exception as e:
        logging.exception("Unexpected failure while processing %s", name)
        return {"name": name, "status": "failed", "reason": str(e)}


def main():
    update_github_pages_branch()

    with GitRepoStore() as store:
        archiver = Archiver(store)

        logging.info("Fetching package list from %s...", PACKAGES_URL)
        try:
            with urllib.request.urlopen(PACKAGES_URL) as response:
                packages = json.loads(response.read().decode())
        except Exception as e:
            logging.error("Failed to fetch package list: %s", e)
            return

        total = len(packages)
        max_pkgs_raw = os.environ.get("MAX_PACKAGES", "").strip()
        max_pkgs = int(max_pkgs_raw) if max_pkgs_raw else total
        selected_packages = packages[:max_pkgs]
        if not selected_packages:
            logging.info("No packages selected for processing.")
            return

        worker_count = get_worker_count(len(selected_packages))
        logging.info("Processing %s packages with %s workers...", len(selected_packages), worker_count)

        results = []
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(process_package, archiver, (i + 1, total, pkg))
                for i, pkg in enumerate(selected_packages)
            ]
            for future in as_completed(futures):
                results.append(future.result())

        success_count = sum(1 for result in results if result["status"] == "ok")
        failed_count = sum(1 for result in results if result["status"] == "failed")
        skipped_count = sum(1 for result in results if result["status"] == "skipped")
        logging.info(
            "Finished processing packages: %s succeeded, %s failed, %s skipped",
            success_count,
            failed_count,
            skipped_count,
        )


if __name__ == "__main__":
    main()
