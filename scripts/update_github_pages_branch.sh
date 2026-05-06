#!/usr/bin/env bash

set -euo pipefail

BRANCH="${1:-gh-pages}"
WORKTREE_DIR="$(mktemp -d)"
cleanup() {
  git worktree remove --force "$WORKTREE_DIR" >/dev/null 2>&1 || true
  rm -rf "$WORKTREE_DIR"
}
trap cleanup EXIT

git rev-parse --is-inside-work-tree >/dev/null

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git worktree add --force "$WORKTREE_DIR" "$BRANCH" >/dev/null
elif git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  git worktree add --track -b "$BRANCH" "$WORKTREE_DIR" "origin/$BRANCH" >/dev/null
else
  git worktree add --detach "$WORKTREE_DIR" HEAD >/dev/null
  git -C "$WORKTREE_DIR" checkout --orphan "$BRANCH" >/dev/null
fi

find "$WORKTREE_DIR" -mindepth 1 -maxdepth 1 ! -name ".git" -exec rm -rf {} +

cp site/index.html "$WORKTREE_DIR/index.html"
mkdir -p "$WORKTREE_DIR/site"
cp -R site/. "$WORKTREE_DIR/site/"
touch "$WORKTREE_DIR/.nojekyll"

cat > "$WORKTREE_DIR/README.md" <<'EOF'
# Nim Packages Archive Site

This branch contains the static site build for GitHub Pages.
EOF

git -C "$WORKTREE_DIR" add .
if git -C "$WORKTREE_DIR" diff --cached --quiet; then
  echo "No GitHub Pages changes to commit."
  exit 0
fi

git -C "$WORKTREE_DIR" commit -m "chore: update GitHub Pages site"
if git remote get-url origin >/dev/null 2>&1; then
  git -C "$WORKTREE_DIR" push -u origin "$BRANCH"
fi
echo "Updated branch: $BRANCH"
