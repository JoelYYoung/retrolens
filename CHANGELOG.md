# Changelog

All notable changes to RetroLens will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- GitHub Actions CI workflow (test matrix: Python 3.10/3.11/3.12 × ubuntu/macos)
- GitHub Actions release workflow (PyPI publish + skill package)
- Test suite (128 tests) covering CLI, readers, models, config
- Release script (`scripts/release.sh`) for version management
- Skill package for Claude Skill Hub (packaged in GitHub releases)

### Changed
- Fixed project URLs in `pyproject.toml` (removed placeholder)
- Migrated `tool.uv.dev-dependencies` to `dependency-groups.dev` (PEP 735)
- Added `py.typed` marker for type hint support
- Fixed 11 ruff lint errors (unused imports, import sorting, variable naming)
- Restructured skill directory for Agent Skills specification
- Updated skill frontmatter to be Agent Skills compliant

### Fixed
- Tests were excluded from git (`.git/info/exclude`), now tracked

## [0.5.1] - 2025-04-09

### Added
- Claude Code reader support (JSONL event stream parsing)
- VS Code Copilot reader improvements (tool extraction, file tracking)
- Stateful config system (`retrolens cfg`)
- Session discovery workflow in SKILL.md

### Changed
- Simplified CLI to 3 commands: `cfg`, `ls`, `read`
- Removed `scan`, `extract`, `reflect`, `show` commands (consolidated)
- Removed workflow DSL and dead code

### Removed
- Native reader (unused)
- `--skill-path` flag (simplified)

## [0.5.0] - 2025-04-01

Initial release.

### Added
- CLI for scanning AI conversation logs
- VS Code Copilot reader
- Data models (SessionInfo, TurnDetail, ToolCallDetail)
- SKILL.md guide for AI agents

[Unreleased]: https://github.com/JoelYYoung/retrolens/compare/v0.5.1...HEAD
[0.5.1]: https://github.com/JoelYYoung/retrolens/releases/tag/v0.5.1
[0.5.0]: https://github.com/JoelYYoung/retrolens/releases/tag/v0.5.0
