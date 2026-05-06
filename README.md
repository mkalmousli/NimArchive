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
scripts/
nimarchive/
```

The Python package code lives in [`nimarchive/`](/mnt/MKSpace/Dev/NimArchive/nimarchive).
The browser UI lives in [`site/`](/mnt/MKSpace/Dev/NimArchive/site).

## Run Once

```bash
python3 -m nimarchive.archiver --archive-root archive --once
```

## Run Periodically

```bash
python3 -m nimarchive.archiver --archive-root archive --interval-hours 2
```

## Use A Local Packages File

```bash
python3 -m nimarchive.archiver --packages-file packages.json --archive-root archive --once
```

## Site

Run the local server with:

```bash
python3 -m nimarchive.server
```

The GitHub Pages helper script is in
[`scripts/update_github_pages_branch.sh`](/mnt/MKSpace/Dev/NimArchive/scripts/update_github_pages_branch.sh).
