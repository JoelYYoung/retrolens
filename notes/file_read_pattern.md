# Claude Code Context 管理模式分析

**分析 Session**: `8114f45d`  
**模型**: anthropic/claude-opus-4.5  
**分析日期**: 2026-03-12

---

## 概述

本分析基于一个包含 6 个 rounds、18 个请求的 Claude Code 会话，重点观察：
1. `CLAUDE.md` 文件在多轮对话中的维护方式
2. `read_file` 工具调用后文件内容是否会在 context 中重复

---

## 一、CLAUDE.md 的维护模式

### 1.1 初始加载方式

`CLAUDE.md` 的内容通过 `<system-reminder>` 标签在**第一条 user 消息**中注入：

```
<system-reminder>
As you answer the user's questions, you can use the following context:
# claudeMd
Codebase and user instructions are shown below...

Contents of /Users/joel/Projects/tmp/CLAUDE.md (project instructions, checked into the codebase):

Your name is Kiwi.

IMPORTANT: this context may or may not be relevant to your tasks...
</system-reminder>
```

### 1.2 文件修改时的更新策略

当 `CLAUDE.md` 被用户修改后（从 "Your name is Kiwi" 改为 "Your name is Xavier"），系统**不会替换**原有的 context，而是通过**增量更新**的方式追加一个新的 `<system-reminder>`：

```
<system-reminder>
Note: /Users/joel/Projects/tmp/CLAUDE.md was modified, either by the user or by a linter. 
This change was intentional, so make sure to take it into account as you proceed 
(ie. don't revert it unless the user asks you to). Don't tell the user this, since they are already aware.
Here are the relevant changes (shown with line numbers):
     1→Your name is Xavier.
</system-reminder>
```

### 1.3 重复情况分析

| Round | Messages Count | CLAUDE.md 出现次数 | 说明 |
|-------|----------------|-------------------|------|
| 2 (seq 4) | 1 | 1 (初始加载) | 首次加载，内容为 "Kiwi" |
| 3 (seq 6) | 3 | 2 (初始 + 修改通知) | **存在冗余**：旧版本 "Kiwi" 仍在 context 中，新增 diff 显示 "Xavier" |
| 4 (seq 9) | 5 | 2 | 同上，两个版本同时存在 |
| 5 (seq 12) | 7 | 2 | 同上 |
| 6 (seq 16) | 11 | 2 | 同上 |

**结论**：`CLAUDE.md` 的更新采用**增量追加**策略，原始内容**不会被替换**，导致 context 中存在**语义冲突的重复**：
- 第一条消息中仍说 "Your name is Kiwi"
- 后续消息中追加修改通知说 "Your name is Xavier"

这种设计依赖模型理解"后来的修改覆盖先前内容"的语义，而非直接替换旧内容。

---

## 二、read_file 工具调用后的文件处理

### 2.1 文件读取场景

| Round | 操作 | 文件 | 内容 |
|-------|------|------|------|
| 5 | Read test.md | /Users/joel/Projects/tmp/test.md | "I call f finger." |
| 6 | Read test.md (再次) | /Users/joel/Projects/tmp/test.md | "I call f flower." (已修改) |

### 2.2 重复情况分析

在 Round 6 的请求 (seq 17) 中，**两次读取的内容都保留在 context 中**：

**第一次读取结果** (Round 5)：
```json
{
  "tool_use_id": "toolu_bdrk_014QmhQrWk4oWH4KN6khnDr8",
  "type": "tool_result",
  "content": "     1→I call f finger.\n..."
}
```

**第二次读取结果** (Round 6)：
```json
{
  "tool_use_id": "toolu_bdrk_018XWppV6CCeDedsX6ogN8vr",
  "type": "tool_result",
  "content": "     1→I call f flower.\n..."
}
```

### 2.3 结论

**read_file 读取同一文件的内容会在 context 中累积**，不会去重或替换。这意味着：
- 如果用户多次要求读取同一文件（尤其是文件被修改后重新读取），context 中会保留**所有历史版本**
- 模型需要从 context 中识别出**最新的工具调用结果**来回答问题
- 这种设计保留了完整的对话历史，但会**增加 token 消耗**

---

## 三、Context 管理模式总结

### 3.1 设计特点

| 方面 | 行为 | 优点 | 缺点 |
|------|------|------|------|
| CLAUDE.md 更新 | 增量追加 diff | 保留修改历史 | 存在语义冲突 |
| read_file 结果 | 全部保留 | 完整对话历史 | Token 累积 |
| 消息历史 | 完整保留 | 上下文连续性 | 长对话成本高 |

### 3.2 Token 增长趋势

```
Round 2: ~151 tokens (messages)
Round 3: ~261 tokens
Round 4: ~269 tokens
Round 5: ~371 tokens (第一次 read_file)
Round 6: ~485 tokens (第二次 read_file，包含两份文件内容)
```

### 3.3 优化建议

1. **CLAUDE.md 更新策略**：考虑在检测到修改后**替换**首条消息中的内容，而非追加 diff
2. **文件读取去重**：对于同一文件的多次读取，可考虑：
   - 只保留最新版本
   - 或使用 diff 格式显示变更
3. **context 窗口管理**：对于长对话，需要考虑 summarization 或 context 压缩机制

---

## 四、原始数据参考

### 用户请求时间线

| Round | 时间 | 用户消息 | 工具调用 |
|-------|------|----------|----------|
| 1 | 15:10:17 | "count" | - |
| 2 | 15:11:13 | "What is your name?" | - |
| 3 | 15:12:03 | "What's your name again?" | - |
| 4 | 15:12:19 | "What do I call f?" | - |
| 5 | 15:12:35 | "Read test.md and tell me." | Read |
| 6 | 15:13:18 | "What do I call f again? read the file again since it's changed." | Read |

### 关键发现

1. **CLAUDE.md 在 Round 3 后存在双重版本**：初始版本 ("Kiwi") + 修改通知 ("Xavier")
2. **test.md 在 Round 6 存在双重版本**：第一次读取 ("finger") + 第二次读取 ("flower")
3. **System prompt 保持稳定**：System prompt hash 随消息变化而变化，但长度保持 ~10643 字符
