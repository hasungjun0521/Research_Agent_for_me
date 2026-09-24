#!/usr/bin/env bash
# Install this workspace's agent skills into the Codex global skills home.
#
# The canonical skill files live in `.claude/skills/<name>/SKILL.md` (tracked in
# this repo and read directly by Claude Code). Prefer the cross-platform
# automation_setup CLI for repository-local .agents/skills discovery. This legacy
# script optionally links skills into the older global skills home.
# Symlinks keep a single source of truth: editing `.claude/skills/...` updates
# both agents at once.
#
# Usage:
#   tools/install_codex_skills.sh            # symlink (default)
#   tools/install_codex_skills.sh --copy     # copy instead of symlink
#   tools/install_codex_skills.sh --uninstall
#
# Restart Codex after install/update so it re-scans the skills home.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$REPO_ROOT/.claude/skills"
CODEX_SKILLS="${CODEX_HOME:-$HOME/.codex}/skills"
MODE="symlink"

case "${1:-}" in
  --copy) MODE="copy" ;;
  --uninstall) MODE="uninstall" ;;
  "" ) ;;
  *) echo "unknown option: $1" >&2; exit 2 ;;
esac

if [ ! -d "$SRC_DIR" ]; then
  echo "no skills found at $SRC_DIR" >&2
  exit 1
fi
mkdir -p "$CODEX_SKILLS"

for skill_path in "$SRC_DIR"/*/; do
  [ -f "${skill_path}SKILL.md" ] || continue
  name="$(basename "$skill_path")"
  dest="$CODEX_SKILLS/$name"

  # Only ever remove a destination we own: a symlink, or a copy we previously
  # made (marked by .workspace-managed). Never clobber an unrelated real dir.
  if { [ -L "$dest" ] && [ "$(readlink "$dest")" = "${skill_path%/}" ]; } || { [ ! -L "$dest" ] && [ -f "$dest/.workspace-managed" ]; }; then
    rm -rf "$dest"
  elif [ -e "$dest" ] || [ -L "$dest" ]; then
    echo "skip $name: $dest exists and is not workspace-managed" >&2
    continue
  fi

  case "$MODE" in
    symlink) ln -s "${skill_path%/}" "$dest"; echo "linked  $name -> ${skill_path%/}" ;;
    copy)    cp -r "${skill_path%/}" "$dest"; touch "$dest/.workspace-managed"; echo "copied  $name" ;;
    uninstall) echo "removed $name" ;;
  esac
done

echo "done ($MODE) -> $CODEX_SKILLS"
echo "Restart Codex so it re-scans the skills home."
