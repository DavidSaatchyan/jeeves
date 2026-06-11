#!/usr/bin/env bash
# OpenFlo post-commit hook — runs review on the latest commit
# Install: copy to .git/hooks/post-commit and chmod +x

set -e

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
COMMIT_HASH=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
COMMIT_MSG=$(git log -1 --pretty=%B 2>/dev/null | head -5)

# Skip if OPENFLO_REVIEW_DISABLED is set
if [ -n "$OPENFLO_REVIEW_DISABLED" ]; then
  exit 0
fi

# Skip merge commits and housekeeping
if echo "$COMMIT_MSG" | grep -qiE '^(merge|chore\(release|wip|fixup!|squash!)'; then
  exit 0
fi

# Get changed files
CHANGED_FILES=$(git diff-tree --no-commit-id -r --name-only HEAD 2>/dev/null | tr '\n' ' ')
CHANGED_COUNT=$(echo "$CHANGED_FILES" | wc -w)

echo ""
echo "🔍 OpenFlo: Reviewing commit $COMMIT_HASH ($CHANGED_COUNT files)..."

# Run review via OpenCode CLI
if command -v opencode &> /dev/null; then
  # Run in non-interactive mode if supported
  opencode --execute \
    "Review the latest commit ($COMMIT_HASH). Changed files: $CHANGED_FILES. " \
    "Check for bugs, security issues, and style problems. " \
    "Keep the response under 200 words. Use agent: reviewer" 2>/dev/null || true
fi

echo "✅ OpenFlo: Review complete"
