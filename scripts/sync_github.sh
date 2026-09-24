#!/usr/bin/env bash
# Mirror the private WAR working tree into its existing public checkout.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash scripts/sync_github.sh [--dry-run]

Sync this repository's working files to github/ beside this script's parent.
Copies tracked files (including uncommitted edits) and non-ignored new files.
Removes destination files that are absent from the source selection.
Preserves .git metadata and never commits, pushes, builds, or updates catalogs.

  -n, --dry-run  Preview changes without modifying the public checkout.
  -h, --help     Show this help.

Ignored, untracked files are not published. Tracked files are included even
if an ignore rule matches them. The nested github/ checkout is always excluded.
EOF
}

dry_run=false
case "${1:-}" in
  '') ;;
  -n|--dry-run) dry_run=true ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac
if (( $# > 1 )); then
  usage >&2
  exit 2
fi

fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
for tool in git rsync mktemp; do
  command -v "$tool" >/dev/null 2>&1 || fail "Required command not found: $tool"
done

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
destination_dir="$source_dir/github"
source_root="$(git -C "$source_dir" rev-parse --show-toplevel)" || fail 'Source is not a Git checkout.'
[[ "$(cd "$source_root" && pwd -P)" == "$source_dir" ]] || fail 'Source must be its own Git checkout.'
[[ -d "$destination_dir" && ! -L "$destination_dir" ]] || fail 'github/ must be an existing directory, not a symlink.'
[[ -e "$destination_dir/.git" && ! -L "$destination_dir/.git" ]] || fail 'github/ must have its own .git metadata.'
destination_root="$(git -C "$destination_dir" rev-parse --show-toplevel)" || fail 'github/ is not a Git checkout.'
[[ "$(cd "$destination_root" && pwd -P)" == "$destination_dir" ]] || fail 'github/ must be a separate Git checkout.'

# Stage the selected files so rsync --delete can also remove deleted sources.
# NUL-separated paths support spaces and newlines; Git applies ignore semantics.
sync_tmp="$(mktemp -d "${TMPDIR:-/tmp}/warrunner-sync.XXXXXXXX")"
trap 'rm -rf -- "$sync_tmp"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir "$sync_tmp/tree"
git -C "$source_dir" ls-files --cached --others --exclude-standard -z > "$sync_tmp/candidates"
: > "$sync_tmp/files"
while IFS= read -r -d '' path; do
  case "$path" in
    .git|.git/*|*/.git|*/.git/*|github|github/*) continue ;;
  esac
  if [[ -f "$source_dir/$path" || -L "$source_dir/$path" ]]; then
    printf '%s\0' "$path" >> "$sync_tmp/files"
  elif [[ -e "$source_dir/$path" ]]; then
    fail "Unsupported source entry (for example, a submodule): $path"
  fi
done < "$sync_tmp/candidates"
[[ -s "$sync_tmp/files" ]] || fail 'No source files selected; refusing to empty the public checkout.'

rsync -a --from0 --files-from="$sync_tmp/files" \
  --exclude='.git' --exclude='/github/' \
  "$source_dir/" "$sync_tmp/tree/"

options=(-a --checksum --delete --omit-dir-times --itemize-changes --exclude='.git')
if "$dry_run"; then options+=(--dry-run); fi
printf 'Syncing %s/ -> %s/\n' "$source_dir" "$destination_dir"
rsync "${options[@]}" "$sync_tmp/tree/" "$destination_dir/"
if "$dry_run"; then
  printf 'Dry run complete; public checkout unchanged.\n'
else
  printf 'Sync complete. Review with: git -C "%s" diff\n' "$destination_dir"
  printf 'Check new/deleted files with: git -C "%s" status --short\n' "$destination_dir"
fi
