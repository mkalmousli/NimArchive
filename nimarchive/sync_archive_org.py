import os
from contextlib import ExitStack
from pathlib import Path

from internetarchive import get_session, modify_metadata, upload


BATCH_SIZE = 128


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def build_metadata() -> dict:
    identifier = require_env("ARCHIVE_ORG_IDENTIFIER")
    metadata = {
        "title": os.environ.get("ARCHIVE_ORG_TITLE", "Nim Package Archive"),
        "description": os.environ.get(
            "ARCHIVE_ORG_DESCRIPTION",
            "Automated archive of Nim package source snapshots, metadata, README files, and licenses.",
        ),
        "collection": os.environ.get("ARCHIVE_ORG_COLLECTION", "opensource"),
        "mediatype": os.environ.get("ARCHIVE_ORG_MEDIATYPE", "data"),
        "creator": os.environ.get("ARCHIVE_ORG_CREATOR", "NimArchive"),
        "subject": [
            "nim",
            "package archive",
            "software preservation",
        ],
    }
    if os.environ.get("ARCHIVE_ORG_LICENSEURL"):
        metadata["licenseurl"] = os.environ["ARCHIVE_ORG_LICENSEURL"]
    return identifier, metadata


def collect_files(root: Path) -> dict[str, Path]:
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files[str(path.relative_to(root))] = path
    return files


def chunk_items(items: list[tuple[str, Path]], size: int) -> list[list[tuple[str, Path]]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def main() -> None:
    archive_root = Path(os.environ.get("ARCHIVE_ROOT", "archive")).resolve()
    if not archive_root.exists():
        raise RuntimeError(f"Archive root does not exist: {archive_root}")

    access_key = require_env("ARCHIVE_ORG_ACCESS_KEY")
    secret_key = require_env("ARCHIVE_ORG_SECRET_KEY")
    identifier, metadata = build_metadata()
    files = collect_files(archive_root)

    if not files:
        raise RuntimeError(f"No files found under {archive_root}")

    session = get_session(config={"s3": {"access": access_key, "secret": secret_key}})

    responses = []
    file_items = list(files.items())

    for index, batch in enumerate(chunk_items(file_items, BATCH_SIZE)):
        with ExitStack() as stack:
            upload_files = {
                remote_name: stack.enter_context(local_path.open("rb"))
                for remote_name, local_path in batch
            }

            batch_responses = upload(
                identifier,
                upload_files,
                metadata=metadata if index == 0 else None,
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
        raise RuntimeError(f"{len(failed)} archive.org upload requests failed")

    metadata_response = modify_metadata(
        identifier,
        metadata=metadata,
        access_key=access_key,
        secret_key=secret_key,
        archive_session=session,
    )
    if not metadata_response.ok:
        raise RuntimeError(f"Metadata update failed: {metadata_response.status_code}")


if __name__ == "__main__":
    main()
