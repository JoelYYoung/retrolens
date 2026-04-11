# Release Checklist

Use this before publishing a new release.

## Pre-Release

- [ ] All tests pass: `python -m pytest tests/ -v`
- [ ] Lint clean: `ruff check src/`
- [ ] Version bumped in 3 places:
  - [ ] `pyproject.toml`
  - [ ] `src/retrolens/__init__.py`
  - [ ] `skill/SKILL.md` frontmatter
- [ ] CHANGELOG.md updated:
  - [ ] Move items from `[Unreleased]` to new version section
  - [ ] Add release date
  - [ ] Update comparison links at bottom
- [ ] README.md examples still work
- [ ] skill/ package complete:
  - [ ] `SKILL.md`
  - [ ] `scripts/` (setup.sh, sample_log.py, validate_reader.py)
  - [ ] `references/READER-API.md`

## PyPI Setup (First Time Only)

- [ ] PyPI trusted publishing configured:
  - Go to https://pypi.org/manage/account/publishing/
  - Add pending publisher:
    - Project: `retrolens`
    - Owner: `JoelYYoung`
    - Repo: `retrolens`
    - Workflow: `release.yml`
    - Environment: `release`

- [ ] GitHub environment created:
  - Settings → Environments → `release`
  - (Optional) Protection rules

## Release

- [ ] Run: `bash scripts/release.sh X.Y.Z`
- [ ] Review changes: `git show vX.Y.Z`
- [ ] Push: `git push origin master vX.Y.Z`
- [ ] Monitor CI: https://github.com/JoelYYoung/retrolens/actions
- [ ] Verify PyPI: https://pypi.org/project/retrolens/
- [ ] Test install: `pip install retrolens==X.Y.Z && retrolens --version`

## Post-Release

- [ ] Check GitHub Release created with attachments:
  - [ ] `.whl` file
  - [ ] `.tar.gz` file
  - [ ] `retrolens-skill-vX.Y.Z.zip`
  - [ ] Changelog excerpt
  
- [ ] (Optional) Upload skill to Claude Skill Hub:
  - Download `retrolens-skill-vX.Y.Z.zip` from release
  - Upload to https://claude.ai/skills

- [ ] Update CHANGELOG.md for next dev cycle
- [ ] Celebrate 🎉
