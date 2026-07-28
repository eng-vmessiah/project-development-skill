#!/bin/bash

# Focused shell-level regression test for scripts/validate.sh discovery.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

mkdir -p \
    "$TMP_DIR/scripts" \
    "$TMP_DIR/skills/top-level" \
    "$TMP_DIR/skills/engineering/codebase-design"
cp "$REPO_DIR/scripts/validate.sh" "$TMP_DIR/scripts/validate.sh"

cat > "$TMP_DIR/skills/top-level/SKILL.md" <<'EOF'
---
name: top-level
description: A top-level fixture skill.
version: 1.0.0
---

# Top-level fixture

```bash
printf 'fixture\n'
```
EOF

cat > "$TMP_DIR/skills/engineering/codebase-design/SKILL.md" <<'EOF'
---
name: codebase-design
description: A nested fixture skill.
---

# Nested fixture

```bash
printf 'fixture\n'
```
EOF

output=$(bash "$TMP_DIR/scripts/validate.sh")
printf '%s\n' "$output"

grep -Fq '📋 top-level:' <<< "$output"
grep -Fq '📋 engineering/codebase-design:' <<< "$output"
grep -Fq '⚠️  1 warning(s) found' <<< "$output"
if grep -Fq 'engineering: ' <<< "$output"; then
    printf 'unexpected category-container validation\n' >&2
    exit 1
fi

# An invalid nested skill must still be validated and fail closed.
sed -i '/^description:/d' "$TMP_DIR/skills/engineering/codebase-design/SKILL.md"
if invalid_output=$(bash "$TMP_DIR/scripts/validate.sh" 2>&1); then
    printf 'validator unexpectedly accepted invalid nested skill\n' >&2
    exit 1
fi
printf '%s\n' "$invalid_output"
grep -Fq "📋 engineering/codebase-design:" <<< "$invalid_output"
grep -Fq "Missing 'description' field" <<< "$invalid_output"
grep -Fq '❌ 1 error(s) found' <<< "$invalid_output"

printf 'validate.sh recursive discovery test: PASS\n'