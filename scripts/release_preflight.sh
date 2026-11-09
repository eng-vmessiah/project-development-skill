#!/usr/bin/env bash
# Local release preflight: run the same gates as the CI/release workflows.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

usage() {
    printf 'usage: %s [--release]\n' "$(basename "$0")"
}

release=0
case "${1:-}" in
    "")
        ;;
    --release)
        release=1
        ;;
    -h|--help)
        usage
        exit 0
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac

if [[ -z "${PYTHON_BIN:-}" ]]; then
    if [[ -x /usr/bin/python3 ]]; then
        PYTHON_BIN=/usr/bin/python3
    else
        PYTHON_BIN=python3
    fi
fi

step() {
    printf '\n==> %s\n' "$1"
}

fail() {
    printf 'release preflight: FAIL: %s\n' "$1" >&2
    exit 1
}

version="$(tr -d '[:space:]' < VERSION)"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "VERSION is not SemVer: $version"
grep -Fq "## [$version]" CHANGELOG.md || fail "CHANGELOG.md has no '## [$version]' section"

if [[ -n "$(git status --porcelain)" ]]; then
    if [[ "$release" -eq 1 ]]; then
        fail "working tree is not clean"
    fi
    printf 'warning: working tree is not clean; commit before tagging.\n' >&2
fi

if [[ "$release" -eq 1 ]]; then
    if grep -Fq '## [Unreleased]' CHANGELOG.md; then
        fail "CHANGELOG.md still has an Unreleased section"
    fi
    git rev-parse -q --verify "refs/tags/v$version" >/dev/null || fail "tag v$version does not exist"
    [[ "$(git rev-parse "refs/tags/v$version^{commit}")" == "$(git rev-parse HEAD)" ]] \
        || fail "tag v$version does not point at HEAD"
fi

step "pytest"
"$PYTHON_BIN" -m pytest tests -q

step "flake8"
if command -v flake8 >/dev/null 2>&1; then
    flake8 scripts/ --config=.flake8
else
    uvx flake8 scripts/ --config=.flake8
fi

step "skill validation"
bash scripts/validate.sh

step "validator regression"
bash tests/test_validate.sh

step "installer regression"
bash tests/test_install.sh

step "release archive"
bash tests/test_release.sh

step "markdown links"
"$PYTHON_BIN" scripts/check_markdown_links.py

step "v2 documentation paths"
"$PYTHON_BIN" scripts/pd_fleet/v2_doc_paths.py .

step "shell syntax"
find scripts tests -type f -name '*.sh' -print0 | xargs -0 -r -n1 bash -n

printf '\nrelease preflight: PASS (%s)\n' "$version"
