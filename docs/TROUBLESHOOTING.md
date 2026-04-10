# Troubleshooting Guide

## CI/CD Issues

### ❌ Test Failure: Version Mismatch

**Problem**: `test_imports.py::test_import_main_package` fails after version bump.

**Symptom**:
```
AssertionError: assert '0.6.0' == '0.5.1'
```

**Root Cause**: Test had hardcoded version check:
```python
assert retrolens.__version__ == "0.5.1"  # ❌ Breaks on version bump
```

**Solution** (✅ Fixed in f89cfe1):
```python
# Dynamic version validation (checks format, not exact version)
parts = retrolens.__version__.split(".")
assert len(parts) == 3
assert all(p.isdigit() for p in parts)
```

**Prevention**: Never hardcode version numbers in tests.

---

### ❌ Release Workflow Failed After Tag Push

**Scenario**: You pushed `v0.5.1` but CI failed due to test issue.

**Recovery Steps**:

1. **Check CI status**:
   ```
   https://github.com/JoelYYoung/retrolens/actions
   ```

2. **If release workflow failed**:
   
   a. Delete the failed GitHub Release (if created):
      - Go to: https://github.com/JoelYYoung/retrolens/releases
      - Find the failed release → Delete
   
   b. Delete the remote tag:
      ```bash
      git push origin :refs/tags/v0.5.1
      ```
   
   c. Delete the local tag:
      ```bash
      git tag -d v0.5.1
      ```

3. **Fix the issue** (e.g., fix tests, update code)

4. **Re-release**:
   ```bash
   # Re-run release script (will recreate commit and tag)
   bash scripts/release.sh 0.5.1
   git push origin master v0.5.1
   ```

---

### ❌ PyPI Upload Failed: File Already Exists

**Problem**: Trying to upload version that already exists on PyPI.

**Root Cause**: PyPI doesn't allow overwriting published versions.

**Solution**: Bump to next version.

```bash
# Cannot re-upload 0.5.1 if already on PyPI
# Instead, use 0.5.2:
bash scripts/release.sh 0.5.2
git push origin master v0.5.2
```

**Prevention**: Always check PyPI before releasing:
```
https://pypi.org/project/retrolens/#history
```

---

### ❌ Trusted Publishing Not Working

**Problem**: `publish-pypi` job fails with authentication error.

**Symptoms**:
- "Invalid or expired credentials"
- "Trusted publishing not configured"

**Solution**:

1. **Verify PyPI configuration**:
   - Go to: https://pypi.org/manage/account/publishing/
   - Check pending publisher exists for `retrolens`
   - Verify fields match **exactly**:
     ```
     Project: retrolens
     Owner: JoelYYoung
     Repo: retrolens
     Workflow: release.yml
     Environment: release
     ```

2. **Verify GitHub environment**:
   - Settings → Environments
   - Ensure `release` environment exists
   - Check workflow file uses: `environment: release`

3. **Alternative**: Use API token
   ```yaml
   # In .github/workflows/release.yml
   - name: Publish to PyPI
     uses: pypa/gh-action-pypi-publish@release/v1
     with:
       password: ${{ secrets.PYPI_API_TOKEN }}
   ```
   Then add token to GitHub Secrets.

---

## Build Issues

### ❌ Wheel Build Fails: Missing Files

**Problem**: `uv build` fails or wheel missing expected files.

**Check**:
```bash
# Build locally
uv build

# Inspect wheel contents
python -c "
import zipfile
with zipfile.ZipFile('dist/retrolens-*.whl') as z:
    for name in sorted(z.namelist()):
        print(name)
"
```

**Common causes**:
- Missing `py.typed` marker
- `skill/` not included (check `pyproject.toml` force-include)
- `.gitignore` excluding necessary files

---

### ❌ Import Error After pip install

**Problem**: `pip install retrolens` succeeds but `import retrolens` fails.

**Debug**:
```bash
# Check where package is installed
pip show retrolens

# Try importing
python -c "import retrolens; print(retrolens.__file__)"

# Check package structure
python -c "import retrolens; import os; print(os.listdir(os.path.dirname(retrolens.__file__)))"
```

**Common causes**:
- Wrong package structure in `pyproject.toml`
- Relative imports broken
- Missing `__init__.py`

---

## Test Issues

### ❌ Tests Pass Locally But Fail in CI

**Common causes**:

1. **Path dependencies**:
   ```python
   # ❌ Assumes running from project root
   with open("data/file.txt") as f:
   
   # ✅ Use pathlib relative to test file
   from pathlib import Path
   fixtures = Path(__file__).parent / "fixtures"
   ```

2. **Environment differences**:
   - CI runs on Ubuntu, you test on macOS
   - Different Python versions
   - Clean environment (no ~/.config state)

3. **Hardcoded values**:
   - Version numbers
   - Absolute paths
   - Timestamps

**Solution**: Use fixtures, relative paths, mock time-dependent code.

---

### ❌ Lint Errors Only in CI

**Reproduce locally**:
```bash
# Use same ruff version as CI
uv pip install ruff==0.1.0

# Run same command as CI
ruff check src/
```

**Common issues**:
- Unused imports
- Import sorting (fixed by `ruff check --fix`)
- Ambiguous variable names (`l`, `I`, `O`)

---

## Release Workflow Debugging

### Check Release Workflow Status

```bash
# View workflow runs
gh run list --workflow=release.yml

# View specific run logs
gh run view <run-id> --log

# Re-run failed workflow
gh run rerun <run-id>
```

### Manual Release (Emergency)

If CI completely broken:

```bash
# 1. Build locally
uv build

# 2. Test install
uv venv /tmp/test && uv pip install dist/*.whl
/tmp/test/bin/retrolens --version

# 3. Upload to PyPI
uv publish
# OR: twine upload dist/*

# 4. Create GitHub Release manually
gh release create v0.6.0 dist/* \
  --title "v0.6.0" \
  --notes "$(sed -n '/## \[0.6.0\]/,/## \[/p' CHANGELOG.md | sed '$d')"
```

---

## Getting Help

1. **Check CI logs**: https://github.com/JoelYYoung/retrolens/actions
2. **Review docs**:
   - `docs/RELEASE_FLOW.md` — Release process explanation
   - `PUBLISHING.md` — Quick reference
   - `RELEASE.md` — Detailed guide
3. **Run tests locally**: `python -m pytest tests/ -v`
4. **Check package build**: `uv build && unzip -l dist/*.whl`
