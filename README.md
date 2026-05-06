# Nim Packages Archive

NimArchive preserves source repositories listed in
[`nim-lang/packages`](https://github.com/nim-lang/packages) so packages do not
disappear when upstream repositories are deleted, renamed, or rewritten.

It keeps plain files on disk so package history stays inspectable, mirrorable,
and publishable.

## Layout

```text
archive/
  index.json
  packages/
    humanize/
      code/
      versions/
site/
```

The archiver entrypoint is [`archive.py`](/mnt/MKSpace/Dev/NimArchive/archive.py).
The browser UI lives in [`site/`](/mnt/MKSpace/Dev/NimArchive/site).
Package snapshots are written into the separate git repository `mkalmousli/NimArchiveData` as each package finishes processing.

## Run Once

```bash
uv run archive.py
```

## Run Periodically

```bash
uv run archive.py archive
```

## Use A Local Packages File

```bash
uv run archive.py
```

## Site

Run the local server with:

```bash
uv run python -m http.server 8000
```

GitHub Pages publishing is handled directly by
[`archive.py site`](/mnt/MKSpace/Dev/NimArchive/archive.py) as a separate fast subcommand.

## Commands

- `uv run archive.py archive`: run the package archiver
- `uv run archive.py site`: publish the static site only

## Data Repo

The archiver expects a writable data repository.

- Default repo: `mkalmousli/NimArchiveData`
- Default branch: `main`
- Workflow secret for pushes: `DATA_REPO_PUSH_TOKEN`
