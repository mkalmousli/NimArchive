#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# ///

import base64
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
import urllib.error
import urllib.parse


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


class PackageNameLockedError(Exception):
    def __init__(self, name, existing_url, incoming_url):
        super().__init__(f"Package name {name} is already locked to {existing_url}")
        self.name = name
        self.existing_url = existing_url
        self.incoming_url = incoming_url


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


def sanitize_name_part(value):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return cleaned or "archive"


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


class GitRepoStore:
    def __init__(self):
        self.repo_slug = os.environ.get("DATA_REPO_SLUG", DEFAULT_DATA_REPO_SLUG).strip() or DEFAULT_DATA_REPO_SLUG
        self.branch = os.environ.get("DATA_REPO_BRANCH", DEFAULT_DATA_REPO_BRANCH).strip() or DEFAULT_DATA_REPO_BRANCH
        self.push_token = os.environ.get("DATA_REPO_PUSH_TOKEN", "").strip()
        if not self.push_token:
            raise RuntimeError("Missing required environment variable: DATA_REPO_PUSH_TOKEN")
        self.api_base = (os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com").strip() or "https://api.github.com").rstrip("/")
        self.temp_dir = tempfile.mkdtemp(prefix="archive_data_repo_")
        self.repo_dir = os.path.join(self.temp_dir, "repo")
        self.lock = threading.RLock()
        self.remote_paths = set()
        self.remote_paths_complete = True
        self.current_commit_sha = None
        self.current_tree_sha = None
        self._branch_exists = False
        self._fetch_remote_state()
        self.index = self.load_json(REMOTE_INDEX_NAME, {})

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _api_headers(self, content_type=None):
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "NimArchive",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {self.push_token}",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _api_url(self, path):
        return f"{self.api_base}/repos/{self.repo_slug}/{path.lstrip('/')}"

    def _request_json(self, method, path, payload=None, allow_404=False):
        data = None
        headers = self._api_headers()
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self._api_url(path), data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            if allow_404 and exc.code == 404:
                return None
            message = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API request failed ({method} {path}): {exc.code} {message}") from exc

    def _fetch_remote_state(self):
        ref = self._request_json("GET", f"git/ref/heads/{urllib.parse.quote(self.branch, safe='')}", allow_404=True)
        if not ref:
            ensure_dir(self.repo_dir)
            logging.info("GitHub data branch %s does not exist yet; starting from an empty mirror.", self.branch)
            return

        self._branch_exists = True
        self.current_commit_sha = ref.get("object", {}).get("sha")
        if not self.current_commit_sha:
            return

        commit = self._request_json("GET", f"git/commits/{self.current_commit_sha}", allow_404=True) or {}
        self.current_tree_sha = commit.get("tree", {}).get("sha")
        if self.current_tree_sha:
            self._refresh_remote_paths(self.current_tree_sha)

        ensure_dir(self.repo_dir)
        logging.info("Configured GitHub API mirror for %s on branch %s.", self.repo_slug, self.branch)

    def _refresh_remote_paths(self, tree_sha):
        tree = self._request_json("GET", f"git/trees/{tree_sha}?recursive=1", allow_404=True) or {}
        paths = set()
        for entry in tree.get("tree", []):
            if entry.get("type") == "blob" and entry.get("path"):
                paths.add(entry["path"])
        self.remote_paths = paths
        self.remote_paths_complete = not bool(tree.get("truncated"))

    def _remote_path_known(self, remote_name):
        if os.path.exists(os.path.join(self.repo_dir, remote_name)):
            return True
        if self.remote_paths_complete:
            return remote_name in self.remote_paths
        return None

    def _fetch_remote_file(self, remote_name):
        local_path = os.path.join(self.repo_dir, remote_name)
        ensure_dir(os.path.dirname(local_path))

        contents = self._request_json(
            "GET",
            f"contents/{urllib.parse.quote(remote_name, safe='/')}?ref={urllib.parse.quote(self.branch, safe='')}",
            allow_404=True,
        )
        if not contents or isinstance(contents, list) or contents.get("type") != "file":
            return False

        encoding = contents.get("encoding")
        payload = contents.get("content", "")
        if encoding == "base64":
            data = base64.b64decode(payload.encode("utf-8"))
            with open(local_path, "wb") as f:
                f.write(data)
        else:
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(payload)

        self.remote_paths.add(remote_name)
        return True

    def load_json(self, remote_name, default=None):
        with self.lock:
            local_path = os.path.join(self.repo_dir, remote_name)
            if not os.path.exists(local_path):
                known = self._remote_path_known(remote_name)
                if known is False:
                    return default if default is not None else {}
                if known is None and not self._fetch_remote_file(remote_name):
                    return default if default is not None else {}
            return get_json(local_path, default)

    def get_index_snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.index))

    def reserve_package_id(self, name, pkg_type, url, license_name):
        with self.lock:
            if name in self.index:
                existing = self.index[name]
                if not isinstance(existing, dict):
                    raise PackageNameLockedError(name, "<invalid index entry>", url)

                existing_id = existing.get("id") or name
                existing_url = existing.get("url")
                existing_type = existing.get("type")
                if existing_url != url or existing_type != pkg_type:
                    raise PackageNameLockedError(name, existing_url or "<missing url>", url)

                return existing_id, False

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

    def _push_changed_files(self, changed_files, message):
        changed_files = sorted({path for path in changed_files if os.path.exists(os.path.join(self.repo_dir, path))})
        if not changed_files:
            return False

        with self.lock:
            blobs = {}
            for remote_path in changed_files:
                local_path = os.path.join(self.repo_dir, remote_path)
                with open(local_path, "rb") as f:
                    content = base64.b64encode(f.read()).decode("ascii")
                blob = self._request_json(
                    "POST",
                    "git/blobs",
                    {"content": content, "encoding": "base64"},
                )
                blobs[remote_path] = blob["sha"]

            tree_payload = {
                "tree": [
                    {"path": remote_path, "mode": "100644", "type": "blob", "sha": blobs[remote_path]}
                    for remote_path in changed_files
                ]
            }
            if self.current_tree_sha:
                tree_payload["base_tree"] = self.current_tree_sha
            tree = self._request_json("POST", "git/trees", tree_payload)

            user_name = os.environ.get("GIT_COMMITTER_NAME", "").strip() or os.environ.get("GITHUB_ACTOR", "").strip() or "github-actions[bot]"
            user_email = os.environ.get("GIT_COMMITTER_EMAIL", "").strip() or "41898282+github-actions[bot]@users.noreply.github.com"
            commit_payload = {
                "message": message,
                "tree": tree["sha"],
                "author": {"name": user_name, "email": user_email},
                "committer": {"name": user_name, "email": user_email},
            }
            if self.current_commit_sha:
                commit_payload["parents"] = [self.current_commit_sha]
            commit = self._request_json("POST", "git/commits", commit_payload)

            ref_path = f"git/refs/heads/{urllib.parse.quote(self.branch, safe='')}"
            if self._branch_exists:
                self._request_json("PATCH", ref_path, {"sha": commit["sha"]})
            else:
                self._request_json("POST", "git/refs", {"ref": f"refs/heads/{self.branch}", "sha": commit["sha"]})
                self._branch_exists = True

            self.current_commit_sha = commit["sha"]
            self.current_tree_sha = tree["sha"]
            self.remote_paths.update(changed_files)
            self.remote_paths_complete = True
            return True

    def upload_index_snapshot(self, package_name):
        with self.lock:
            save_json(os.path.join(self.repo_dir, REMOTE_INDEX_NAME), self.index)
            changed = self._push_changed_files([REMOTE_INDEX_NAME], f"chore: register package {package_name}")
        if changed:
            logging.info("Pushed index.json after discovering package %s.", package_name)
        return changed

    def get_next_id(self, remote_name, key):
        data = self.load_json(remote_name, {key: []})
        numeric_ids = [int(value) for value in data.get(key, []) if str(value).isdigit()]
        return str(max(numeric_ids) + 1) if numeric_ids else "0"

    def remote_file_present(self, remote_name):
        with self.lock:
            known = self._remote_path_known(remote_name)
            if known is not None:
                return known
            return self._fetch_remote_file(remote_name)

    def ensure_remote_file_cached(self, remote_name):
        with self.lock:
            local_path = os.path.join(self.repo_dir, remote_name)
            if os.path.exists(local_path):
                return True

            known = self._remote_path_known(remote_name)
            if known is False:
                return False
            return self._fetch_remote_file(remote_name)

    def load_snapshot_metadata(self, remote_snapshot_dir):
        return self.load_json(f"{remote_snapshot_dir}/metadata.json", {})

    def snapshot_is_complete(self, remote_snapshot_dir, metadata):
        if not metadata:
            return False

        required_files = [
            f"{remote_snapshot_dir}/metadata.json",
            f"{remote_snapshot_dir}/{metadata.get('archive_name', 'source.tar.gz')}",
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
                self.ensure_remote_file_cached(remote_name)
                source_md5 = calculate_md5(local_path)
                if os.path.exists(target_path) and calculate_md5(target_path) == source_md5:
                    continue
                ensure_dir(os.path.dirname(target_path))
                shutil.copy2(local_path, target_path)
                changed_items.append(remote_name)

            if not changed_items:
                logging.info("Data repo sync skipped for %s: no changed files.", package_name)
                return 0

            changed = self._push_changed_files(changed_items, f"chore: archive {package_name}")

        if changed:
            logging.info("Saved package %s into %s (%s files).", package_name, self.repo_slug, len(changed_items))
            return len(changed_items)
        return 0


class Archiver:
    def __init__(self, store):
        self.store = store

    def _git_tree_hash(self, repo_path, commit):
        try:
            return subprocess.run(
                ["git", "-C", repo_path, "rev-parse", f"{commit}^{{tree}}"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except subprocess.CalledProcessError:
            return ""

    def _snapshot_matches(self, metadata, commit, source_hash):
        if not metadata:
            return False
        if source_hash and metadata.get("source_hash") == source_hash:
            return True
        return metadata.get("commit") == commit

    def _select_snapshot_id(self, remote_parent_dir, history_key, latest_id, commit, source_hash):
        if latest_id:
            latest_remote_dir = f"{remote_parent_dir}/{latest_id}"
            latest_meta = self.store.load_snapshot_metadata(latest_remote_dir)
            if self._snapshot_matches(latest_meta, commit, source_hash):
                return latest_id, not self.store.snapshot_is_complete(latest_remote_dir, latest_meta)
            if not latest_meta:
                return latest_id, True

        history = self.store.load_json(f"{remote_parent_dir}/all.json", {history_key: []})
        for snapshot_id in history.get(history_key, []):
            remote_snapshot_dir = f"{remote_parent_dir}/{snapshot_id}"
            metadata = self.store.load_snapshot_metadata(remote_snapshot_dir)
            if self._snapshot_matches(metadata, commit, source_hash):
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

            self._process_branch(repo_path, name, pkg_id, package_root, "HEAD", temp_dir)
            self._process_tags(repo_path, name, pkg_id, package_root, temp_dir)
            saved_files = self.store.upload_tree(upload_root, name)
            logging.info("Package %s synced into data repo after %s changed file(s).", name, saved_files)
        return True

    def _process_branch(self, repo_path, package_name, pkg_id, package_root, branch, temp_dir):
        code_dir = os.path.join(package_root, "code")
        remote_code_dir = f"{REMOTE_PACKAGES_DIR}/{pkg_id}/code"
        ensure_dir(code_dir)

        try:
            commit = subprocess.run(["git", "-C", repo_path, "rev-parse", branch], capture_output=True, text=True, check=True).stdout.strip()
        except subprocess.CalledProcessError:
            return False

        latest_data = self.store.load_json(f"{remote_code_dir}/latest.json", {})
        latest_code_id = latest_data.get("code")
        source_hash = self._git_tree_hash(repo_path, commit)
        code_id, needs_archive = self._select_snapshot_id(remote_code_dir, "codes", latest_code_id, commit, source_hash)
        target_dir = os.path.join(code_dir, code_id)
        archive_label = "latest"

        if needs_archive:
            logging.info("Archiving code state for %s (ID: %s)", branch, code_id)
            if not self._do_archive(repo_path, package_name, archive_label, target_dir, commit, source_hash, temp_dir):
                return False
        else:
            logging.info("Skipping code state for %s: source hash is already archived as ID %s.", branch, code_id)

        save_json(os.path.join(code_dir, "latest.json"), {"code": code_id})
        all_data = self.store.load_json(f"{remote_code_dir}/all.json", {"codes": []})
        if code_id not in all_data["codes"]:
            all_data["codes"].append(code_id)
        save_json(os.path.join(code_dir, "all.json"), all_data)
        return needs_archive

    def _process_tags(self, repo_path, package_name, pkg_id, package_root, temp_dir):
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

            source_hash = self._git_tree_hash(repo_path, commit)
            version_id, needs_archive = self._select_snapshot_id(remote_tag_dir, "versions", t_latest_id, commit, source_hash)
            if needs_archive:
                logging.info("Archiving tag %s (ID: %s)", tag, version_id)
                if not self._do_archive(repo_path, package_name, tag, os.path.join(tag_dir, version_id), commit, source_hash, temp_dir):
                    continue
            else:
                logging.info("Skipping tag %s: source hash is already archived as ID %s.", tag, version_id)

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

    def _do_archive(self, repo_path, package_name, archive_label, target_dir, commit, source_hash, temp_dir):
        ensure_dir(target_dir)
        archive_name = f"{sanitize_name_part(package_name)}-{sanitize_name_part(archive_label)}.tar.gz"
        archive_file = os.path.join(target_dir, archive_name)
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
                    "source_hash": source_hash,
                    "source_hash_kind": "git_tree",
                    "archived_at": int(time.time()),
                    "archive_name": archive_name,
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
    except PackageNameLockedError as e:
        logging.warning(
            "Skipping %s: package name is already locked to %s; incoming URL was %s.",
            e.name,
            e.existing_url,
            e.incoming_url,
        )
        return {"name": name, "status": "skipped", "reason": "name_locked"}
    except Exception as e:
        logging.exception("Unexpected failure while processing %s", name)
        return {"name": name, "status": "failed", "reason": str(e)}


def run_archive():
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

        logging.info("Processing %s packages serially...", len(selected_packages))

        results = []
        for i, pkg in enumerate(selected_packages):
            results.append(process_package(archiver, (i + 1, total, pkg)))

        success_count = sum(1 for result in results if result["status"] == "ok")
        failed_count = sum(1 for result in results if result["status"] == "failed")
        skipped_count = sum(1 for result in results if result["status"] == "skipped")
        logging.info(
            "Finished processing packages: %s succeeded, %s failed, %s skipped",
            success_count,
            failed_count,
            skipped_count,
        )


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "archive"

    if command == "site":
        update_github_pages_branch()
        return

    if command not in {"archive", "run"}:
        raise SystemExit(f"Unknown subcommand: {command}")

    run_archive()


if __name__ == "__main__":
    main()
