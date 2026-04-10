# 发布脚本 vs GitHub Actions 对比

## 快速回答你的问题

### ❓ 我是在本地运行这个发布脚本吗？

**是的**。`scripts/release.sh` 在**你的电脑（macOS）**上运行。

### ❓ GitHub 里面的 release.yml 是做什么的？

**自动发布到 PyPI 和创建 GitHub Release**。在 **GitHub 服务器（Ubuntu 虚拟机）**上运行。

---

## 📊 详细对比表

| 维度 | `scripts/release.sh`<br/>(本地脚本) | `.github/workflows/release.yml`<br/>(GitHub Actions) |
|------|-----------------------------------|---------------------------------------------------|
| **运行位置** | 👨‍💻 你的电脑 (macOS) | 🤖 GitHub 服务器 (Ubuntu) |
| **触发方式** | ✋ 手动：`bash scripts/release.sh 0.6.0` | 🏷️ 自动：检测到 tag push |
| **需要网络** | ❌ 不需要（只操作本地文件） | ✅ 需要（下载依赖、上传包） |
| **执行时间** | ⚡ 几秒钟 | ⏱️ 5-10 分钟 |
| **主要作用** | 📝 更新版本号<br/>💾 创建 commit<br/>🏷️ 创建 git tag | 🔨 构建 wheel<br/>🧪 测试安装<br/>📦 发布 PyPI<br/>📋 创建 Release |
| **输出** | Git commit + tag（存在本地） | PyPI 包 + GitHub Release（在云端） |
| **失败影响** | 本地 git 状态（可轻易回滚） | 发布失败（需要调试 CI） |
| **是否必需** | ✅ 必需（版本管理） | ✅ 必需（自动化发布） |

---

## 🔄 完整流程时序

```
时刻 T0 (你的电脑)
├─ bash scripts/release.sh 0.6.0
│  ├─ 修改 pyproject.toml
│  ├─ 修改 __init__.py
│  ├─ 修改 skill/SKILL.md
│  ├─ git commit
│  └─ git tag v0.6.0
│
时刻 T1 (你的电脑)
├─ git push origin master v0.6.0
│  └─ Tag 上传到 GitHub ✈️
│
时刻 T2 (GitHub 服务器)
├─ release.yml 被触发 🚀
│  ├─ [0-2min] Job 1: build
│  ├─ [2-3min] Job 2: test-install
│  ├─ [3-4min] Job 3: publish-pypi ──> PyPI ✅
│  └─ [4-5min] Job 4: create-release ──> GitHub Release ✅
│
时刻 T3 (全世界)
└─ 用户可以: pip install retrolens==0.6.0 🎉
```

---

## 🎯 为什么需要两者配合？

### 方案 A：只用本地脚本 ❌

```bash
bash scripts/release.sh 0.6.0
uv build
uv publish  # 需要 PyPI token
gh release create v0.6.0 dist/*  # 需要 GitHub token
```

**问题**：
- ⚠️ 需要在本地保存敏感 token
- ⚠️ 构建环境不一致（你的 macOS vs 用户的 Linux）
- ⚠️ 每次手动执行多个命令，容易出错
- ⚠️ 没有测试步骤

### 方案 B：只用 GitHub Actions ❌

在 CI 中修改代码和创建 tag？

**问题**：
- ⚠️ CI 不应该修改源代码（反模式）
- ⚠️ 你失去对版本号的直接控制
- ⚠️ 难以回滚（CI 已经跑完了）

### 方案 C：两者配合 ✅（当前方案）

```
你（本地）: 版本决策 + tag 创建
     ↓
GitHub Actions: 自动化构建 + 测试 + 发布
```

**优势**：
- ✅ 你保持控制（版本号、发布时机）
- ✅ CI 负责重复工作（构建、测试、上传）
- ✅ 安全（trusted publishing，无需本地 token）
- ✅ 一致性（总是在相同环境构建）
- ✅ 可追溯（CI 日志永久保存）

---

## 💡 类比理解

想象发布软件像发射火箭：

| 组件 | 类比 | 实际 |
|------|------|------|
| `release.sh` | 🎛️ 发射控制台<br/>（操作员按下按钮） | 你在本地创建 tag |
| GitHub Actions | 🚀 自动发射系统<br/>（检查、点火、飞行） | CI 自动构建和发布 |
| PyPI | 🌍 目标轨道<br/>（包到达用户） | 用户 pip install |

你**不能**直接用遥控器（本地）让火箭到达轨道，需要发射系统（CI）。
但你**必须**按下按钮（创建 tag），否则系统不会启动。

---

## 📝 实际命令示例

### 你在本地做的事：

```bash
# === 阶段 1: 准备 ===
cd /Users/joel/Projects/retrolens
git status  # 确保干净

# === 阶段 2: 发布 ===
bash scripts/release.sh 0.6.0
# 👀 仔细检查 diff
# ✅ 确认无误后按 y

# === 阶段 3: 触发 CI ===
git push origin master v0.6.0

# === 阶段 4: 等待（喝咖啡） ===
# 打开浏览器:
# https://github.com/JoelYYoung/retrolens/actions

# === 阶段 5: 验证 ===
# 5-10 分钟后，检查:
# - https://pypi.org/project/retrolens/
# - https://github.com/JoelYYoung/retrolens/releases

# 本地测试安装:
pip install retrolens==0.6.0
retrolens --version
```

### GitHub Actions 做的事（你不用管）：

```yaml
# .github/workflows/release.yml 内容（自动执行）

on:
  push:
    tags:
      - 'v*.*.*'  # <-- 你 push v0.6.0 时触发

jobs:
  build:        # 构建包
  test-install: # 测试安装
  publish-pypi: # 发布到 PyPI
  create-release: # 创建 GitHub Release
```

---

## ❓ 常见误解澄清

### ❌ "release.sh 会上传到 PyPI"
**错误**。它只更新版本号和创建 tag，不做任何上传。

### ❌ "release.yml 会修改代码"
**错误**。它只读取代码、构建、发布，不会 commit。

### ❌ "我需要在 GitHub Actions 里配置版本号"
**错误**。版本号由你在本地通过 `release.sh` 设置。

### ✅ "release.sh + release.yml 是配合工作"
**正确**。本地准备，CI 执行。

---

## 🎓 学习资源

- **GitHub Actions 入门**: https://docs.github.com/en/actions
- **PyPI Trusted Publishing**: https://docs.pypi.org/trusted-publishers/
- **语义化版本**: https://semver.org/lang/zh-CN/

---

## 🆘 需要帮助？

查看这些文件：
- `docs/RELEASE_FLOW.md` — 本文档（流程详解）
- `PUBLISHING.md` — 快速参考
- `RELEASE.md` — 完整步骤
- `.github/RELEASE_CHECKLIST.md` — 检查清单
