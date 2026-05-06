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

## Run Once

```bash
uv run archive.py
```

## Run Periodically

```bash
uv run archive.py
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
[`archive.py`](/mnt/MKSpace/Dev/NimArchive/archive.py) before archive processing runs.
