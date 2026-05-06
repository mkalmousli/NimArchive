import json
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from nimarchive import archiver


class ArchiverTests(unittest.TestCase):
    def test_package_folder_base_is_simple_and_url_safe(self) -> None:
        self.assertEqual(archiver.package_folder_base("humanize"), "humanize")
        self.assertEqual(archiver.package_folder_base("bad name!"), "bad_name")

    def test_first_package_keeps_name_and_duplicates_get_suffixes(self) -> None:
        index: dict[str, object] = {}
        first = archiver.PackageEntry("humanize", "https://example.invalid/one", "git", {})
        second = archiver.PackageEntry("humanize", "https://example.invalid/two", "git", {})

        self.assertEqual(archiver.ensure_index_entry(index, first), "humanize")
        self.assertEqual(archiver.ensure_index_entry(index, second), "humanize1")

    def test_git_snapshot_uses_unix_names_and_package_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            self.run_git(["init"], repo)
            self.run_git(["config", "user.email", "test@example.invalid"], repo)
            self.run_git(["config", "user.name", "Test"], repo)
            (repo / "testpkg.nimble").write_text('version = "0.1.0"\n', encoding="utf-8")
            self.run_git(["add", "testpkg.nimble"], repo)
            self.run_git(["commit", "-m", "initial"], repo)
            self.run_git(["tag", "v0.1.0"], repo)
            (repo / "testpkg.nimble").write_text('version = "0.2.0"\n', encoding="utf-8")
            self.run_git(["add", "testpkg.nimble"], repo)
            self.run_git(["commit", "-m", "second"], repo)

            packages_file = root / "packages.json"
            packages_file.write_text(
                json.dumps(
                    [
                        {
                            "name": "testpkg",
                            "url": str(repo),
                            "method": "git",
                            "tags": [],
                            "description": "test",
                            "license": "MIT",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            args = Namespace(
                archive_root=str(root / "archive"),
                packages_file=str(packages_file),
                packages_url=archiver.DEFAULT_PACKAGES_URL,
                http_timeout=30.0,
                package=None,
                limit=None,
                force=False,
            )

            self.assertEqual(archiver.run_once(args), 0)

            package_dir = root / "archive" / "packages" / "testpkg"
            code_dir = package_dir / "code"
            versions_dir = package_dir / "versions"
            self.assertTrue(code_dir.exists())
            self.assertTrue(versions_dir.exists())
            self.assertFalse((package_dir / "snapshots").exists())
            self.assertFalse((package_dir / "package.json").exists())
            self.assertFalse((package_dir / "index.json").exists())

            index = json.loads((root / "archive" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(
                index,
                {
                    "schema_version": 1,
                    "testpkg": {"type": "git", "url": str(repo)},
                },
            )

            code_history = json.loads((code_dir / "all.json").read_text(encoding="utf-8"))
            self.assertEqual(code_history["schema_version"], 1)
            self.assertEqual(len(code_history["snapshots"]), 1)
            code_stamp = code_history["snapshots"][0]
            self.assertEqual(code_stamp, "0")
            self.assertEqual(
                (code_dir / code_stamp / "code.tar.gz").exists(),
                True,
            )
            self.assertTrue((code_dir / code_stamp / "metadata.json").exists())
            code_latest = json.loads((code_dir / "latest.json").read_text(encoding="utf-8"))
            self.assertEqual(code_latest["snapshot"], code_stamp)

            versions_json = json.loads((versions_dir / "all.json").read_text(encoding="utf-8"))
            self.assertEqual(versions_json["schema_version"], 1)
            self.assertEqual(versions_json["latest"], "0.1.0")
            self.assertEqual(set(versions_json["versions"]), {"0.1.0"})

            for version in ("0.1.0",):
                version_dir = versions_dir / version
                self.assertTrue(version_dir.exists())
                archives = list(version_dir.glob("*.tar.gz"))
                self.assertEqual(len(archives), 1)
                # The ID for v0.1.0 should be "1" because HEAD (v0.2.0) was archived first as "0"
                v_id = archives[0].name.removesuffix(".tar.gz")
                self.assertEqual(v_id, "1")
                
                metadata_files = list(version_dir.glob("*.metadata.json"))
                self.assertEqual(len(metadata_files), 1)
                
                # Check latest.json inside version directory
                v_latest = json.loads((version_dir / "latest.json").read_text(encoding="utf-8"))
                self.assertEqual(v_latest["snapshot"], v_id)
                
                # Verify metadata fields
                v_meta = json.loads(metadata_files[0].read_text(encoding="utf-8"))
                self.assertEqual(v_meta["code"], v_id)
                self.assertIn("stamp", v_meta)
                self.assertNotEqual(v_meta["stamp"], v_meta["code"])

    @staticmethod
    def run_git(args: list[str], cwd: Path) -> None:
        subprocess.run(["git", *args], cwd=cwd, check=True, stdout=subprocess.PIPE)


if __name__ == "__main__":
    unittest.main()
