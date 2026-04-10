# Release Guide

## Prerequisites

### 1. PyPI Account Setup

**Trusted Publishing (Recommended)**:
1. Go to https://pypi.org/manage/account/publishing/
2. Add a new pending publisher:
   - PyPI Project Name: `retrolens`
   - Owner: `JoelYYoung`
   - Repository: `retrolens`
   - Workflow: `release.yml`
   - Environment: `release`

**Alternative - API Token**:
1. Generate token at https://pypi.org/manage/account/token/
2. Add to GitHub Secrets as `PYPI_API_TOKEN`
3. Update `release.yml` to use: `password: ${{ secrets.PYPI_API_TOKEN }}`

### 2. GitHub Settings

1. **Create release environment**:
   - Go to Settings → Environments → New environment
   - Name: `release`
   - Add protection rules (optional): require approval

2. **Enable workflow permissions**:
   - Settings → Actions → General → Workflow permissions
   - Enable "Read and write permissions"

### 3. Claude Skill Hub (Optional)

To publish to Claude Skill Hub:
1. Download `retrolens-skill-vX.X.X.zip` from GitHub Release
2. Go to https://claude.ai/skills (or wherever Claude hosts skill uploads)
3. Upload the zip file
4. Fill in metadata (same as `skill/SKILL.md` frontmatter)

---

## Release Process

### Step 1: Prepare Release

1. **Ensure clean state**:
   ```bash
   git status  # Should be clean
   git checkout master
   git pull origin master
   ```

2. **Update CHANGELOG.md**:
   - Move items from `[Unreleased]` to new version section
   - Add release date
   - Update comparison links at bottom

3. **Run tests locally**:
   ```bash
   python -m pytest tests/ -v
   ruff check src/
   ```

### Step 2: Create Release

```bash
bash scripts/release.sh 0.6.0
```

This script will:
- Update version in `pyproject.toml`, `__init__.py`, `skill/SKILL.md`
- Commit changes
- Create git tag `v0.6.0`
- Show next steps

### Step 3: Push and Trigger CI

```bash
# Review the changes one more time
git log -1 --stat
git show v0.6.0

# Push
git push origin master v0.6.0
```

**What happens automatically**:
1. ✅ GitHub Actions `release.yml` triggered
2. ✅ Build wheel + sdist
3. ✅ Run test install
4. ✅ Publish to PyPI (if trusted publishing configured)
5. ✅ Create GitHub Release with:
   - Wheel (`.whl`)
   - Source distribution (`.tar.gz`)
   - Skill package (`retrolens-skill-vX.X.X.zip`)
   - Changelog excerpt

### Step 4: Verify Release

1. **Check GitHub Actions**: https://github.com/JoelYYoung/retrolens/actions
2. **Check PyPI**: https://pypi.org/project/retrolens/
3. **Test install**:
   ```bash
   pip install retrolens==0.6.0
   retrolens --version
   ```
4. **Check GitHub Release**: https://github.com/JoelYYoung/retrolens/releases

---

## Post-Release

1. **Announce** (optional):
   - Update README badges if needed
   - Post on social media / community channels
   - Update documentation sites

2. **Start next development cycle**:
   ```bash
   # Update CHANGELOG.md
   echo "## [Unreleased]\n\n### Added\n\n### Changed\n\n### Fixed\n" | cat - CHANGELOG.md > temp && mv temp CHANGELOG.md
   ```

---

## Troubleshooting

### PyPI Upload Fails

**Error: Invalid or expired credentials**
- If using trusted publishing: ensure GitHub environment name matches (`release`)
- If using token: regenerate token and update secret

**Error: File already exists**
- Version already published (cannot overwrite)
- Bump version and retry

### Skill Package Issues

**Zip file too large**
- Current package ~20KB (well under limits)
- If needed, exclude `__pycache__` or compiled files

**Missing files in zip**
- Check `skill/` directory structure
- Verify `git ls-files skill/` includes all needed files

---

## Manual Release (Emergency)

If CI fails, you can release manually:

```bash
# Build
uv build

# Test install
uv pip install dist/retrolens-*.whl
retrolens --version

# Upload to PyPI
uv publish
# Or: twine upload dist/*

# Create skill package
cd skill
zip -r ../retrolens-skill-v0.6.0.zip .
cd ..

# Create GitHub release manually
gh release create v0.6.0 \
  dist/* \
  retrolens-skill-v0.6.0.zip \
  --title "v0.6.0" \
  --notes "See CHANGELOG.md"
```
