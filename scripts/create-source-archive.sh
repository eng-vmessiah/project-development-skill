#!/bin/bash
# Create the reproducible source archive for a checked-out Git ref.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VERSION=$(tr -d '[:space:]' < "$REPO_DIR/VERSION")
REF="${1:-v$VERSION}"
OUTPUT_DIR="${2:-$REPO_DIR/dist}"

[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
    printf 'ERROR: VERSION is not a SemVer release: %s\n' "$VERSION" >&2
    exit 1
}
git -C "$REPO_DIR" rev-parse --verify --quiet "$REF^{commit}" >/dev/null || {
    printf 'ERROR: Git ref does not resolve to a commit: %s\n' "$REF" >&2
    exit 1
}

mkdir -p "$OUTPUT_DIR"
archive="$OUTPUT_DIR/project-development-skill-$VERSION.tar.gz"
checksum="$archive.sha256"
prefix="project-development-skill-$VERSION/"

# git-archive uses the commit metadata for file mtimes; gzip -n removes the
# remaining producer timestamp, making this byte-for-byte reproducible.
git -C "$REPO_DIR" archive --format=tar --prefix="$prefix" "$REF" | gzip -n > "$archive"
(cd "$OUTPUT_DIR" && sha256sum "$(basename "$archive")" > "$(basename "$checksum")")

printf 'Created %s\n' "$archive"
printf 'Created %s\n' "$checksum"