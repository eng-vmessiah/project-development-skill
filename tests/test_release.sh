#!/bin/bash
# Local release-artifact regression test; does not require a release tag.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

expected_version=$(tr -d '[:space:]' < "$REPO_DIR/VERSION")
[[ "$expected_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
version="$expected_version"

bash "$REPO_DIR/scripts/create-source-archive.sh" HEAD "$TMP_DIR/one" >/dev/null
bash "$REPO_DIR/scripts/create-source-archive.sh" HEAD "$TMP_DIR/two" >/dev/null
cmp "$TMP_DIR/one/project-development-skill-$version.tar.gz" \
    "$TMP_DIR/two/project-development-skill-$version.tar.gz"
(cd "$TMP_DIR/one" && sha256sum -c "project-development-skill-$version.tar.gz.sha256")
tar -tzf "$TMP_DIR/one/project-development-skill-$version.tar.gz" > "$TMP_DIR/archive.list"
grep -Fqx "project-development-skill-$version/LICENSE" "$TMP_DIR/archive.list"

printf 'release archive test: PASS (%s)\n' "$version"