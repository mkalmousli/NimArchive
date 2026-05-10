import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

import archive as archiver


class ArchiverTests(unittest.TestCase):
    def test_existing_package_name_is_locked_to_original_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(Path(tmp) / "repo")

            pkg_id, is_new = store.reserve_package_id("humanize", "git", "https://example.invalid/one", "MIT")
            self.assertEqual(pkg_id, "humanize")
            self.assertTrue(is_new)

            pkg_id, is_new = store.reserve_package_id("humanize", "git", "https://example.invalid/one", "MIT")
            self.assertEqual(pkg_id, "humanize")
            self.assertFalse(is_new)

            before = json.loads(json.dumps(store.index))
            with self.assertRaises(archiver.PackageNameLockedError):
                store.reserve_package_id("humanize", "git", "https://example.invalid/two", "MIT")
            self.assertEqual(store.index, before)

    def test_upload_tree_fetches_known_remote_file_and_skips_same_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = self.make_store(root / "repo")
            remote = root / "remote"
            upload = root / "upload"
            remote.mkdir()
            upload.mkdir()
            (remote / "index.json").write_text('{"humanize": {"id": "humanize"}}\n', encoding="utf-8")
            (upload / "index.json").write_text('{"humanize": {"id": "humanize"}}\n', encoding="utf-8")

            fetched = []
            pushed = []
            store.remote_paths = {"index.json"}

            def fetch(remote_name):
                fetched.append(remote_name)
                target = Path(store.repo_dir) / remote_name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(remote / remote_name, target)
                return True

            def push(changed_files, message):
                pushed.extend(changed_files)
                return True

            store._fetch_remote_file = fetch
            store._push_changed_files = push

            self.assertEqual(store.upload_tree(str(upload), "humanize"), 0)
            self.assertEqual(fetched, ["index.json"])
            self.assertEqual(pushed, [])

    def test_snapshot_selection_reuses_same_source_hash(self) -> None:
        class FakeStore:
            def load_snapshot_metadata(self, remote_snapshot_dir):
                if remote_snapshot_dir == "packages/humanize/code/0":
                    return {
                        "commit": "old-commit",
                        "source_hash": "same-tree",
                        "archive_name": "humanize-latest.tar.gz",
                    }
                return {}

            def snapshot_is_complete(self, remote_snapshot_dir, metadata):
                return True

            def load_json(self, remote_name, default=None):
                return {"codes": ["0"]}

            def get_next_id(self, remote_name, key):
                return "1"

        archive = archiver.Archiver(FakeStore())
        snapshot_id, needs_archive = archive._select_snapshot_id(
            "packages/humanize/code",
            "codes",
            "0",
            "new-commit",
            "same-tree",
        )
        self.assertEqual(snapshot_id, "0")
        self.assertFalse(needs_archive)

    @staticmethod
    def make_store(repo_dir: Path):
        store = object.__new__(archiver.GitRepoStore)
        store.repo_slug = "example/archive"
        store.repo_dir = str(repo_dir)
        store.lock = threading.RLock()
        store.remote_paths = set()
        store.remote_paths_complete = True
        store.index = {}
        os.makedirs(store.repo_dir, exist_ok=True)
        return store


if __name__ == "__main__":
    unittest.main()
