#!/usr/bin/env bash
# Release script for RetroLens
#
# Usage:
#   bash scripts/release.sh 0.6.0
#
# This script:
# 1. Updates version in pyproject.toml
# 2. Updates __version__ in __init__.py
# 3. Commits the changes
# 4. Creates a git tag
# 5. Pushes to trigger CI release workflow

set -euo pipefail

if [ $# -ne 1 ]; then
    echo "Usage: bash scripts/release.sh <version>"
    echo "Example: bash scripts/release.sh 0.6.0"
    exit 1
fi

NEW_VERSION="$1"
TAG="v${NEW_VERSION}"

# Validate version format (semantic versioning)
if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Error: Version must be in format X.Y.Z (e.g., 0.6.0)"
    exit 1
fi

echo "🚀 Preparing release ${TAG}"
echo ""

# Check git status is clean
if [ -n "$(git status --porcelain)" ]; then
    echo "❌ Error: Working directory not clean. Commit or stash changes first."
    git status --short
    exit 1
fi

# Check we're on master
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "master" ]; then
    echo "⚠️  Warning: Not on master branch (currently on: $BRANCH)"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update pyproject.toml
echo "📝 Updating pyproject.toml..."
sed -i '' "s/^version = .*/version = \"${NEW_VERSION}\"/" pyproject.toml

# Update __init__.py
echo "📝 Updating src/retrolens/__init__.py..."
sed -i '' "s/__version__ = .*/__version__ = \"${NEW_VERSION}\"/" src/retrolens/__init__.py

# Update skill/SKILL.md frontmatter
echo "📝 Updating skill/SKILL.md metadata..."
sed -i '' "s/version: .*/version: \"${NEW_VERSION}\"/" skill/SKILL.md

# Verify changes
echo ""
echo "=== Changes ==="
git diff pyproject.toml src/retrolens/__init__.py skill/SKILL.md

# Confirm
echo ""
read -p "Commit and tag as ${TAG}? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted. Reverting changes..."
    git checkout -- pyproject.toml src/retrolens/__init__.py skill/SKILL.md
    exit 1
fi

# Commit
git add pyproject.toml src/retrolens/__init__.py skill/SKILL.md
git commit -m "chore: bump version to ${NEW_VERSION}"

# Create tag
git tag -a "${TAG}" -m "Release ${TAG}"

echo ""
echo "✅ Tagged as ${TAG}"
echo ""
echo "Next steps:"
echo "  1. Review CHANGELOG.md and update for this release"
echo "  2. Push: git push origin master ${TAG}"
echo "  3. GitHub Actions will automatically:"
echo "     - Build wheel + sdist"
echo "     - Run tests"
echo "     - Publish to PyPI"
echo "     - Create GitHub Release with skill package"
