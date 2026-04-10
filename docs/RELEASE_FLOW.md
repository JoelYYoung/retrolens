# 发布流程详解

## 🎯 核心概念

发布分为**两个阶段**：

### 阶段 1：本地准备（你手动操作）
运行 `scripts/release.sh` 脚本在**本地**完成版本更新和 tag 创建

### 阶段 2：自动发布（GitHub Actions 自动执行）
推送 tag 后，`release.yml` 工作流在 **GitHub 服务器**上自动完成构建和发布

---

## 📋 详细流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    阶段 1: 本地准备（你）                          │
└─────────────────────────────────────────────────────────────────┘

你的电脑 (macOS)
├─ bash scripts/release.sh 0.6.0
│  ├─ ✅ 检查 git 状态干净
│  ├─ ✅ 检查在 master 分支
│  ├─ 📝 修改 pyproject.toml       → version = "0.6.0"
│  ├─ 📝 修改 src/retrolens/__init__.py → __version__ = "0.6.0"
│  ├─ 📝 修改 skill/SKILL.md       → version: "0.6.0"
│  ├─ 💾 git commit -m "chore: bump version to 0.6.0"
│  └─ 🏷️  git tag -a v0.6.0 -m "Release v0.6.0"
│
├─ 你确认并手动推送:
│  └─ git push origin master v0.6.0
│
└─ Tag v0.6.0 推送到 GitHub ───────────────────────────────────┐
                                                               │
┌──────────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────┐
│              阶段 2: 自动发布（GitHub Actions）                   │
└─────────────────────────────────────────────────────────────────┘

GitHub 服务器 (Ubuntu 虚拟机)
├─ 🚀 release.yml 被触发 (检测到 tag: v0.6.0)
│
├─ Job 1: build
│  ├─ checkout 代码
│  ├─ 安装 Python 3.12
│  ├─ 安装 uv
│  ├─ uv build                    → 生成 wheel + tar.gz
│  └─ 上传 dist/ 目录作为 artifact
│
├─ Job 2: test-install (依赖 build)
│  ├─ 下载 dist/ artifact
│  ├─ 在全新环境安装 wheel
│  ├─ retrolens --version         ✅ 验证安装成功
│  ├─ retrolens cfg show          ✅ 验证命令可用
│  └─ retrolens --help            ✅ 验证帮助正常
│
├─ Job 3: publish-pypi (依赖 test-install)
│  ├─ 下载 dist/ artifact
│  ├─ 使用 PyPI trusted publishing
│  └─ 📦 上传到 https://pypi.org/project/retrolens/
│     → 用户可以: pip install retrolens==0.6.0
│
└─ Job 4: create-release (依赖 test-install)
   ├─ 下载 dist/ artifact
   ├─ 打包 skill/ 目录:
   │  └─ zip -r retrolens-skill-v0.6.0.zip skill/*
   ├─ 从 CHANGELOG.md 提取本版本变更说明
   └─ 📋 创建 GitHub Release:
      ├─ retrolens-0.6.0-py3-none-any.whl
      ├─ retrolens-0.6.0.tar.gz
      ├─ retrolens-skill-v0.6.0.zip
      └─ 变更日志 (从 CHANGELOG.md)
         → 可见于: https://github.com/JoelYYoung/retrolens/releases
```

---

## 🔍 各组件作用对比

| 组件 | 运行位置 | 作用 | 手动/自动 |
|------|---------|------|----------|
| `scripts/release.sh` | **你的电脑** | 更新版本号、创建 git tag | ✋ 手动运行 |
| `.github/workflows/release.yml` | **GitHub 服务器** | 构建、测试、发布到 PyPI、创建 Release | 🤖 tag 触发自动运行 |
| `.github/workflows/ci.yml` | **GitHub 服务器** | 运行测试（每次 push） | 🤖 push 触发自动运行 |

---

## 💡 为什么要分两步？

### 1. `release.sh` 在本地运行的原因：

✅ **你保持控制**：版本号是重要决策，你可以：
   - 检查 diff 确认修改正确
   - 决定是否真的要发布（可以 abort）
   - 在推送前再次测试

✅ **Git 工作流标准**：
   - Tag 应该由人工创建（带有语义）
   - 便于回滚：`git tag -d v0.6.0` 删除 tag

✅ **安全**：不在 CI 中修改代码和提交

### 2. `release.yml` 在 GitHub 运行的原因：

✅ **自动化重复工作**：
   - 构建 wheel（需要干净环境）
   - 测试安装（需要多个隔离环境）
   - 上传 PyPI（需要认证）
   - 创建 Release（需要 GitHub API）

✅ **一致性**：
   - 总是在 Ubuntu 上构建（避免平台差异）
   - 总是用相同的 Python 版本
   - 总是执行相同的测试步骤

✅ **安全**：
   - PyPI trusted publishing（无需本地保存 token）
   - GitHub 提供的安全环境

---

## 🎬 实际操作演示

### 你要做的事（5 分钟）：

```bash
# 1. 更新 CHANGELOG.md（手动编辑）
vim CHANGELOG.md  # 移动 [Unreleased] 条目到 [0.6.0]

# 2. 运行发布脚本
bash scripts/release.sh 0.6.0
# 输出:
# 🚀 Preparing release v0.6.0
# 📝 Updating pyproject.toml...
# 📝 Updating src/retrolens/__init__.py...
# 📝 Updating skill/SKILL.md...
# 
# === Changes ===
# [显示 diff]
# 
# Commit and tag as v0.6.0? (y/N)

y  # 确认

# 输出:
# ✅ Tagged as v0.6.0
# 
# Next steps:
#   1. Review CHANGELOG.md and update for this release
#   2. Push: git push origin master v0.6.0

# 3. 推送（触发自动发布）
git push origin master v0.6.0

# 4. 喝杯咖啡 ☕，等 5-10 分钟
# 去 https://github.com/JoelYYoung/retrolens/actions 看进度
```

### GitHub Actions 自动做的事（5-10 分钟）：

你什么都不用做，去看 Actions 页面就行：

```
https://github.com/JoelYYoung/retrolens/actions
```

你会看到：
- ✅ build（1 分钟）
- ✅ test-install（1 分钟）
- ✅ publish-pypi（30 秒）
- ✅ create-release（30 秒）

完成后：
- PyPI: https://pypi.org/project/retrolens/ → 显示 0.6.0 版本
- Release: https://github.com/JoelYYoung/retrolens/releases → 有 v0.6.0 条目

---

## ❓ 常见问题

### Q1: 我可以跳过 `release.sh`，直接手动改版本号吗？

**可以**，但不推荐：
```bash
# 手动方式（繁琐且容易出错）
sed -i '' 's/version = "0.5.1"/version = "0.6.0"/' pyproject.toml
sed -i '' 's/__version__ = "0.5.1"/__version__ = "0.6.0"/' src/retrolens/__init__.py
sed -i '' 's/version: "0.5.1"/version: "0.6.0"/' skill/SKILL.md
git add pyproject.toml src/retrolens/__init__.py skill/SKILL.md
git commit -m "chore: bump version to 0.6.0"
git tag -a v0.6.0 -m "Release v0.6.0"
git push origin master v0.6.0
```

`release.sh` 就是为了避免这种重复劳动和出错风险。

### Q2: 我可以在本地发布到 PyPI，不用 CI 吗？

**可以**，但不推荐：
```bash
# 本地发布（需要配置 token）
uv build
uv publish  # 或 twine upload dist/*
```

**缺点**：
- 需要在本地保存 PyPI token（安全风险）
- 构建环境不一致（你的 macOS vs 用户的 Linux）
- 没有自动测试步骤
- 没有自动创建 GitHub Release

### Q3: 如果 CI 失败了怎么办？

1. **查看失败原因**：
   ```
   https://github.com/JoelYYoung/retrolens/actions
   ```

2. **修复代码**：
   ```bash
   # 修复问题
   git add .
   git commit -m "fix: ..."
   git push origin master
   ```

3. **删除旧 tag，重新发布**：
   ```bash
   # 删除本地和远程 tag
   git tag -d v0.6.0
   git push origin :refs/tags/v0.6.0
   
   # 重新运行发布脚本
   bash scripts/release.sh 0.6.0
   git push origin master v0.6.0
   ```

---

## 📚 相关文档

- `PUBLISHING.md` — 快速参考指南
- `RELEASE.md` — 完整发布文档
- `.github/RELEASE_CHECKLIST.md` — 发布前检查清单
