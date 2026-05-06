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

class Archiver:
    def __init__(self):
        ensure_dir(ARCHIVE_ROOT)
        ensure_dir(PACKAGES_DIR)
        self.index_path = os.path.join(ARCHIVE_ROOT, "index.json")
        self.index = get_json(self.index_path, {})

    def get_package_id(self, name, pkg_type, url, license_name):
        if name in self.index:
            return self.index[name]["id"]
        
        # Check if name is already taken by another package entry
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
                return

            # 2. Process HEAD (code/)
            self._process_branch(repo_path, pkg_base_dir, "HEAD", temp_dir)

            # 3. Process Tags (versions/)
            self._process_tags(repo_path, pkg_base_dir, temp_dir)

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

def main():
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
    
    for i, pkg in enumerate(packages):
        if i >= max_pkgs: break
        name = pkg.get('name')
        url = pkg.get('url')
        method = pkg.get('method')
        
        if not name or not url: continue
        logging.info(f"[{i+1}/{total}] Processing {name}...")
        
        if method == 'git':
            archiver.archive_git_repo(name, url, pkg.get('license'))
        else:
            logging.warning(f"Method {method} not supported for {name}")

if __name__ == '__main__':
    main()
