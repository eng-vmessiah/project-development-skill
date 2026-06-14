#!/bin/bash
# Validate all skills in the repository

set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_DIR="$REPO_DIR/skills"

echo "🔍 Validating Project Development Skills..."
echo ""

ERRORS=0
WARNINGS=0

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Check each skill
for skill_dir in "$SKILLS_DIR"/*/; do
    skill_name=$(basename "$skill_dir")
    skill_file="$skill_dir/SKILL.md"
    
    echo -n "📋 $skill_name: "
    
    # Check if SKILL.md exists
    if [ ! -f "$skill_file" ]; then
        echo -e "${RED}FAIL${NC} - SKILL.md not found"
        ERRORS=$((ERRORS + 1))
        continue
    fi
    
    # Check file size
    SIZE=$(wc -c < "$skill_file")
    if [ $SIZE -gt 35000 ]; then
        echo -e "${YELLOW}WARN${NC} - Size $SIZE chars (max 35k)"
        WARNINGS=$((WARNINGS + 1))
    fi
    
    # Check frontmatter
    if ! head -1 "$skill_file" | grep -q "^---"; then
        echo -e "${RED}FAIL${NC} - Missing frontmatter"
        ERRORS=$((ERRORS + 1))
        continue
    fi
    
    # Check required fields
    if ! grep -q "^name:" "$skill_file"; then
        echo -e "${RED}FAIL${NC} - Missing 'name' field"
        ERRORS=$((ERRORS + 1))
        continue
    fi
    
    if ! grep -q "^description:" "$skill_file"; then
        echo -e "${RED}FAIL${NC} - Missing 'description' field"
        ERRORS=$((ERRORS + 1))
        continue
    fi
    
    if ! grep -q "^version:" "$skill_file"; then
        echo -e "${YELLOW}WARN${NC} - Missing 'version' field"
        WARNINGS=$((WARNINGS + 1))
    fi
    
    # Check for content after frontmatter
    CONTENT_LINES=$(sed -n '/^---$/,/^---$/p' "$skill_file" | wc -l)
    TOTAL_LINES=$(wc -l < "$skill_file")
    
    if [ $CONTENT_LINES -ge $TOTAL_LINES ]; then
        echo -e "${RED}FAIL${NC} - No content after frontmatter"
        ERRORS=$((ERRORS + 1))
        continue
    fi
    
    # Check for code examples
    if ! grep -q '```' "$skill_file"; then
        echo -e "${YELLOW}WARN${NC} - No code examples found"
        WARNINGS=$((WARNINGS + 1))
    fi
    
    echo -e "${GREEN}OK${NC} ($SIZE chars)"
done

echo ""
echo "========================================"
echo "Validation complete!"
echo ""

if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}❌ $ERRORS error(s) found${NC}"
    exit 1
fi

if [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}⚠️  $WARNINGS warning(s) found${NC}"
else
    echo -e "${GREEN}✅ All skills valid!${NC}"
fi
