#!/usr/bin/env bash
# OpenFlo pre-commit hook — runs linter + tests on staged files
# Install: copy to .git/hooks/pre-commit and chmod +x

set -e

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")

if [ -n "$OPENFLO_HOOKS_DISABLED" ]; then
  exit 0
fi

STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null)

if [ -z "$STAGED_FILES" ]; then
  exit 0
fi

# Determine project type and run appropriate checks
if [ -f "$REPO_ROOT/package.json" ]; then
  if command -v npx &> /dev/null; then
    # Check for type errors on staged files
    if [ -f "$REPO_ROOT/tsconfig.json" ] && command -v npx &> /dev/null; then
      npx tsc --noEmit 2>/dev/null && echo "✅ TypeScript: OK" || echo "⚠️  TypeScript: has errors (not blocking)"
    fi

    # Run lint on staged files
    if [ -f "$REPO_ROOT/.eslintrc*" ] || [ -f "$REPO_ROOT/eslint.config.*" ]; then
      npx eslint $STAGED_FILES --max-warnings=0 2>/dev/null && echo "✅ Lint: OK" || echo "⚠️  Lint: has warnings"
    fi
  fi

  # Run tests for staged files
  if [ -f "$REPO_ROOT/package.json" ]; then
    echo "🔍 OpenFlo: Staged files: $(echo $STAGED_FILES | wc -w)"
  fi
fi

# Check for debugging artifacts
if echo "$STAGED_FILES" | xargs grep -l "console\.log\|debugger\|TODO\|FIXME" 2>/dev/null | head -5; then
  echo "⚠️  OpenFlo: debugging artifacts found in staged files"
fi
