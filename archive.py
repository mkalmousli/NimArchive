#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "internetarchive>=5.8.0",
# ]
# ///

import os
import subprocess
import json
import logging
import sys
import urllib.request
import hashlib
import tarfile
import tempfile
import shutil
import time
import threading
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from internetarchive import get_files, get_session, modify_metadata, upload
except ImportError:
    get_files = None
    get_session = None
    modify_metadata = None
    upload = None

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

PACKAGES_URL = "https://raw.githubusercontent.com/nim-lang/packages/master/packages.json"
BASE_DIR = os.getcwd()
ARCHIVE_ROOT = os.path.join(BASE_DIR, "archive")
PACKAGES_DIR = os.path.join(ARCHIVE_ROOT, "packages")
SYNC_BATCH_SIZE = 128
DEFAULT_GITHUB_PAGES_BRANCH = "gh-pages"

def ensure_dir(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def get_json(path, default=None):
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            return default if default is not None else {}
    return default if default is not None else {}

def save_json(path, data):
    ensure_dir(os.path.dirname(path))
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)

def get_next_id(directory):
    if not os.path.exists(directory):
        return "0"
    try:
        subdirs = [d for d in os.listdir(directory) if os.path.isdir(os.path.join(directory, d)) and d.isdigit()]
        if not subdirs:
            return "0"
        return str(max(int(d) for d in subdirs) + 1)
    except Exception:
        return "0"

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
    # "full source code with git, very compressed"
    # To have files at toplevel, we add the contents of the directory
    try:
        with tarfile.open(target_path, "w:gz", compresslevel=9) as tar:
            for item in os.listdir(source_path):
                item_path = os.path.join(source_path, item)
                tar.add(item_path, arcname=item)
        return True
    except Exception as e:
        logging.error(f"Compression failed: {e}")
        return False

def require_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value

def build_archive_org_metadata():
    identifier = require_env("ARCHIVE_ORG_IDENTIFIER")
    metadata = {
        "title": os.environ.get("ARCHIVE_ORG_TITLE", "Nim Packages Archive"),
        "description": os.environ.get(
            "ARCHIVE_ORG_DESCRIPTION",
            "Automated archive of Nim package source snapshots, metadata, README files, and licenses.",
        ),
        "collection": os.environ.get("ARCHIVE_ORG_COLLECTION", "opensource"),
        "mediatype": os.environ.get("ARCHIVE_ORG_MEDIATYPE", "data"),
        "creator": os.environ.get("ARCHIVE_ORG_CREATOR", "NimArchive"),
        "subject": ["nim", "package archive", "software preservation"],
    }
    if os.environ.get("ARCHIVE_ORG_LICENSEURL"):
        metadata["licenseurl"] = os.environ["ARCHIVE_ORG_LICENSEURL"]
    return identifier, metadata

def collect_archive_files(root_path):
    files = {}
    for current_root, _, file_names in os.walk(root_path):
        for file_name in sorted(file_names):
            path = os.path.join(current_root, file_name)
            relative_path = os.path.relpath(path, root_path).replace(os.sep, "/")
            files[relative_path] = path
    return files

def chunk_items(items, size):
    return [items[index:index + size] for index in range(0, len(items), size)]

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
        with open(os.path.join(worktree_dir, "README.md"), "w") as f:
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

def should_sync_archive_org():
    required = ("ARCHIVE_ORG_IDENTIFIER", "ARCHIVE_ORG_ACCESS_KEY", "ARCHIVE_ORG_SECRET_KEY")
    return all(os.environ.get(name, "").strip() for name in required)

def sync_archive_org(archive_root):
    if not should_sync_archive_org():
        logging.info("Archive.org sync skipped: missing credentials or identifier.")
        return
    if upload is None or get_session is None or get_files is None or modify_metadata is None:
        raise RuntimeError("internetarchive is not installed; cannot sync to Archive.org")
    if not os.path.exists(archive_root):
        raise RuntimeError(f"Archive root does not exist: {archive_root}")

    access_key = require_env("ARCHIVE_ORG_ACCESS_KEY")
    secret_key = require_env("ARCHIVE_ORG_SECRET_KEY")
    identifier, metadata = build_archive_org_metadata()
    local_files = collect_archive_files(archive_root)
    if not local_files:
        logging.info("Archive.org sync skipped: no archive files found.")
        return

    session = get_session(config={"s3": {"access": access_key, "secret": secret_key}})
    logging.info("Fetching current Archive.org file state for %s...", identifier)
    remote_md5_by_name = {}
    try:
        for remote_file in get_files(identifier, archive_session=session):
            name = getattr(remote_file, "name", None)
            if not name:
                continue
            remote_md5_by_name[name] = getattr(remote_file, "md5", None)
    except Exception as e:
        logging.warning("Could not read current Archive.org file list for %s: %s", identifier, e)

    changed_items = []
    for remote_name, local_path in local_files.items():
        local_md5 = calculate_md5(local_path)
        if remote_md5_by_name.get(remote_name) != local_md5:
            changed_items.append((remote_name, local_path))

    if not changed_items:
        logging.info("Archive.org sync: no changed files to upload.")
    else:
        logging.info("Archive.org sync: uploading %s changed files...", len(changed_items))
        responses = []
        for index, batch in enumerate(chunk_items(changed_items, SYNC_BATCH_SIZE)):
            with ExitStack() as stack:
                upload_files = {
                    remote_name: stack.enter_context(open(local_path, "rb"))
                    for remote_name, local_path in batch
                }
                batch_responses = upload(
                    identifier,
                    upload_files,
                    metadata=metadata if index == 0 and not remote_md5_by_name else None,
                    access_key=access_key,
                    secret_key=secret_key,
                    checksum=True,
                    verify=True,
                    retries=5,
                    retries_sleep=10,
                    verbose=True,
                    archive_session=session,
                )
                responses.extend(batch_responses)

        failed = [response for response in responses if not response.ok]
        if failed:
            raise RuntimeError(f"{len(failed)} Archive.org upload requests failed")

    metadata_response = modify_metadata(
        identifier,
        metadata=metadata,
        access_key=access_key,
        secret_key=secret_key,
        archive_session=session,
    )
    if not metadata_response.ok:
        raise RuntimeError(f"Archive.org metadata update failed: {metadata_response.status_code}")
    logging.info("Archive.org sync completed for %s.", identifier)

class Archiver:
    def __init__(self):
        ensure_dir(ARCHIVE_ROOT)
        ensure_dir(PACKAGES_DIR)
        self.index_path = os.path.join(ARCHIVE_ROOT, "index.json")
        self.index = get_json(self.index_path, {})
        self.index_lock = threading.Lock()

    def get_package_id(self, name, pkg_type, url, license_name):
        with self.index_lock:
            if name in self.index:
                return self.index[name]["id"]
            
            existing_ids = {p["id"] for p in self.index.values() if "id" in p}
            
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
                "added_at": int(time.time())
            }
            save_json(self.index_path, self.index)
            return proposed_id

    def archive_git_repo(self, name, url, license_name):
        pkg_id = self.get_package_id(name, "git", url, license_name)
        pkg_base_dir = os.path.join(PACKAGES_DIR, pkg_id)
        
        with tempfile.TemporaryDirectory(prefix=f"archiver_{name}_") as temp_dir:
            repo_path = os.path.join(temp_dir, "repo")
            
            # 1. Sync Repo (Clone into temp)
            logging.info(f"Cloning {name}...")
            try:
                subprocess.run(['git', 'clone', '--mirror', url, repo_path], check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                logging.error(f"Clone failed for {name}: {e.stderr.decode()}")
                return False

            # 2. Process HEAD (code/)
            self._process_branch(repo_path, pkg_base_dir, "HEAD", temp_dir)

            # 3. Process Tags (versions/)
            self._process_tags(repo_path, pkg_base_dir, temp_dir)
        return True

    def _process_branch(self, repo_path, pkg_base_dir, branch, temp_dir):
        code_dir = os.path.join(pkg_base_dir, "code")
        ensure_dir(code_dir)
        
        try:
            commit = subprocess.run(['git', '-C', repo_path, 'rev-parse', branch], 
                                   capture_output=True, text=True, check=True).stdout.strip()
        except subprocess.CalledProcessError:
            return

        latest_json_path = os.path.join(code_dir, "latest.json")
        all_json_path = os.path.join(code_dir, "all.json")
        
        latest_data = get_json(latest_json_path)
        latest_code_id = latest_data.get("code")
        
        should_archive = True
        if latest_code_id:
            meta = get_json(os.path.join(code_dir, latest_code_id, "metadata.json"))
            if meta.get("commit") == commit:
                should_archive = False

        if should_archive:
            new_code_id = get_next_id(code_dir)
            logging.info(f"Archiving new code state for {branch} (ID: {new_code_id})")
            self._do_archive(repo_path, os.path.join(code_dir, new_code_id), commit, temp_dir)
            
            # Update latest/all
            save_json(latest_json_path, {"code": new_code_id})
            all_data = get_json(all_json_path, {"codes": []})
            if new_code_id not in all_data["codes"]:
                all_data["codes"].append(new_code_id)
            save_json(all_json_path, all_data)

    def _process_tags(self, repo_path, pkg_base_dir, temp_dir):
        versions_dir = os.path.join(pkg_base_dir, "versions")
        ensure_dir(versions_dir)
        
        try:
            tags_output = subprocess.run(['git', '-C', repo_path, 'tag'], 
                                        capture_output=True, text=True, check=True).stdout.strip()
            tags = tags_output.split('\n') if tags_output else []
        except subprocess.CalledProcessError:
            tags = []

        v_all_json_path = os.path.join(versions_dir, "all.json")
        v_latest_json_path = os.path.join(versions_dir, "latest.json")
        
        existing_versions = get_json(v_all_json_path, {"versions": []})
        
        latest_tag = None
        for tag in tags:
            if not tag: continue
            latest_tag = tag
            
            tag_dir = os.path.join(versions_dir, tag)
            ensure_dir(tag_dir)
            
            try:
                commit = subprocess.run(['git', '-C', repo_path, 'rev-parse', f"{tag}^{{commit}}"], 
                                       capture_output=True, text=True, check=True).stdout.strip()
            except subprocess.CalledProcessError:
                continue

            t_latest_json_path = os.path.join(tag_dir, "latest.json")
            t_all_json_path = os.path.join(tag_dir, "all.json")
            
            t_latest_data = get_json(t_latest_json_path)
            t_latest_id = t_latest_data.get("version_id")
            
            should_archive = True
            if t_latest_id:
                meta = get_json(os.path.join(tag_dir, t_latest_id, "metadata.json"))
                if meta.get("commit") == commit:
                    should_archive = False
            
            if should_archive:
                new_v_id = get_next_id(tag_dir)
                logging.info(f"Archiving tag {tag} (ID: {new_v_id})")
                self._do_archive(repo_path, os.path.join(tag_dir, new_v_id), commit, temp_dir)
                
                save_json(t_latest_json_path, {"version_id": new_v_id})
                t_all_data = get_json(t_all_json_path, {"versions": []})
                if new_v_id not in t_all_data["versions"]:
                    t_all_data["versions"].append(new_v_id)
                save_json(t_all_json_path, t_all_data)

            if tag not in existing_versions["versions"]:
                existing_versions["versions"].append(tag)

        save_json(v_all_json_path, existing_versions)
        if latest_tag:
            save_json(v_latest_json_path, {"version": latest_tag})

    def _do_archive(self, repo_path, target_dir, commit, temp_dir):
        ensure_dir(target_dir)
        archive_file = os.path.join(target_dir, "source.tar.gz")
        
        temp_export = os.path.join(temp_dir, f"export_{hashlib.md5(target_dir.encode()).hexdigest()}")
        try:
            # Clone from the mirror in temp to another local dir in temp
            subprocess.run(['git', 'clone', repo_path, temp_export], check=True, capture_output=True)
            subprocess.run(['git', '-C', temp_export, 'checkout', commit], check=True, capture_output=True)
            
            # Identify README and LICENSE
            readme_file = None
            license_file = None
            for f in os.listdir(temp_export):
                lf = f.lower()
                f_path = os.path.join(temp_export, f)
                if not os.path.isfile(f_path):
                    continue
                if not readme_file and lf.startswith("readme"):
                    readme_file = f
                if not license_file and lf.startswith("license"):
                    license_file = f

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
        finally:
            if os.path.exists(temp_export):
                shutil.rmtree(temp_export)

def get_worker_count(task_count):
    workers_raw = os.environ.get("ARCHIVER_WORKERS", "").strip()
    if workers_raw:
        return max(1, min(task_count, int(workers_raw)))
    cpu_count = os.cpu_count() or 4
    return max(1, min(task_count, cpu_count * 4))

def process_package(archiver, package_info):
    index, total, pkg = package_info
    name = pkg.get('name')
    url = pkg.get('url')
    method = pkg.get('method')

    if not name or not url:
        return {"name": name or "<missing>", "status": "skipped", "reason": "missing_name_or_url"}

    logging.info(f"[{index}/{total}] Processing {name}...")

    if method != 'git':
        logging.warning(f"Method {method} not supported for {name}")
        return {"name": name, "status": "skipped", "reason": f"unsupported_method:{method}"}

    try:
        success = archiver.archive_git_repo(name, url, pkg.get('license'))
        return {"name": name, "status": "ok" if success else "failed"}
    except Exception as e:
        logging.exception(f"Unexpected failure while processing {name}")
        return {"name": name, "status": "failed", "reason": str(e)}

def main():
    update_github_pages_branch()
    archiver = Archiver()
    
    logging.info(f"Fetching package list from {PACKAGES_URL}...")
    try:
        with urllib.request.urlopen(PACKAGES_URL) as response:
            packages = json.loads(response.read().decode())
    except Exception as e:
        logging.error(f"Failed to fetch package list: {e}")
        return

    total = len(packages)
    max_pkgs_raw = os.environ.get("MAX_PACKAGES", "").strip()
    max_pkgs = int(max_pkgs_raw) if max_pkgs_raw else total
    selected_packages = packages[:max_pkgs]
    if not selected_packages:
        logging.info("No packages selected for processing.")
        return

    worker_count = get_worker_count(len(selected_packages))
    logging.info(f"Processing {len(selected_packages)} packages with {worker_count} workers...")

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
    sync_archive_org(ARCHIVE_ROOT)

if __name__ == '__main__':
    main()
