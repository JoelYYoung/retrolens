# Publishing Guide — Quick Reference

## 🎯 Overview

RetroLens can be published to two places:

1. **PyPI** (Python Package Index) — `pip install retrolens`
2. **Claude Skill Hub** — Downloadable skill package for Claude agents

Both are automated via GitHub Actions.

---

## 🚀 Quick Publish (After First-Time Setup)

```bash
# 1. Ensure everything is committed and pushed
git status  # Should be clean
git pull origin master

# 2. Update CHANGELOG.md (move [Unreleased] items to new version)

# 3. Run release script
bash scripts/release.sh 0.6.0

# 4. Push tag to trigger CI
git push origin master v0.6.0
```

**That's it!** GitHub Actions will:
- ✅ Run tests
- ✅ Build wheel + sdist
- ✅ Publish to PyPI
- ✅ Create GitHub Release with skill package

---

## 🔧 First-Time Setup

### 1. PyPI Trusted Publishing (No Token Needed!)

**Best practice** — uses GitHub's OIDC for secure publishing.

1. Go to https://pypi.org/manage/account/publishing/
2. Click "Add a new pending publisher"
3. Fill in:
   - **PyPI Project Name**: `retrolens`
   - **Owner**: `JoelYYoung`
   - **Repository name**: `retrolens`
   - **Workflow name**: `release.yml`
   - **Environment name**: `release`
4. Click "Add"

### 2. GitHub Environment (Optional but Recommended)

1. Go to https://github.com/JoelYYoung/retrolens/settings/environments
2. Click "New environment"
3. Name: `release`
4. (Optional) Add protection rules:
   - Required reviewers
   - Wait timer
   - Deployment branches

### 3. Test the Setup

```bash
# Dry run (don't actually push)
bash scripts/release.sh 0.5.2
git log -1  # Review the commit
git tag -d v0.5.2  # Delete tag
git reset --soft HEAD~1  # Undo commit
```

---

## 📦 What Gets Published

### PyPI Package

- **Wheel**: `retrolens-X.Y.Z-py3-none-any.whl`
- **Source**: `retrolens-X.Y.Z.tar.gz`

Contents:
- All Python code in `src/retrolens/`
- Skill directory as `retrolens/skill/` (for pip install access)
- Metadata, license, README

### Claude Skill Hub Package

- **Zip**: `retrolens-skill-vX.Y.Z.zip`

Contents (from `skill/` directory):
```
skill/
├── SKILL.md                 # Main skill instruction
├── scripts/
│   ├── setup.sh            # Install retrolens
│   ├── find_logs.sh        # Discover log files
│   ├── sample_log.py       # Sample and detect format
│   └── validate_reader.py  # Validate reader output
└── references/
    └── READER-API.md       # BaseReader interface
```

---

## 📋 Release Workflow Details

Triggered by: `git push origin vX.Y.Z`

### Job 1: `build`
- Checkout code
- Install uv
- Build wheel + sdist
- Upload artifacts

### Job 2: `test-install`
- Download artifacts
- Install wheel in fresh venv
- Run smoke tests (`retrolens --version`, `--help`)

### Job 3: `publish-pypi`
- Download artifacts
- Publish to PyPI using trusted publishing
- **Requires**: environment `release`

### Job 4: `create-release`
- Create skill package zip
- Extract changelog for this version
- Create GitHub Release with:
  - Wheel
  - Source tarball
  - Skill package
  - Changelog notes

---

## 🐛 Troubleshooting

### "Invalid or expired credentials" (PyPI)

**Check**:
1. Trusted publishing configured? (See setup step 1)
2. Environment name is `release` in workflow and PyPI config
3. Repository name matches exactly

**Fix**: Double-check all fields match in PyPI trusted publishing settings.

### Workflow runs but PyPI publish skips

**Check**: Environment protection rules might require approval.

**Fix**: Go to Actions → Release workflow → Review and approve deployment.

### Tag already exists

```bash
# Delete local tag
git tag -d v0.6.0

# Delete remote tag
git push origin :refs/tags/v0.6.0
```

### Need to rebuild without new tag

```bash
# Trigger manually
gh workflow run release.yml
```

---

## 📚 Files Reference

| File | Purpose |
|------|---------|
| `.github/workflows/release.yml` | Release CI workflow |
| `.github/workflows/ci.yml` | Test CI (runs on every push) |
| `.github/skills/retrolens/SKILL.md` | Symlink for VS Code Copilot discovery |
| `scripts/release.sh` | Version bump + tag automation |
| `CHANGELOG.md` | Version history |
| `RELEASE.md` | Detailed release guide |
| `RELEASE_CHECKLIST.md` | Pre-release checklist |
| `skill/` | Claude Skill Hub package source |

---

## 🎓 Learn More

- **PyPI Trusted Publishing**: https://docs.pypi.org/trusted-publishers/
- **GitHub Actions**: https://docs.github.com/en/actions
- **Agent Skills Spec**: https://agentskills.io/specification
- **Keep a Changelog**: https://keepachangelog.com/
