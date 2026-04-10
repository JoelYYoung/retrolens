---
name: retrolens
description: Navigate AI conversation logs like a debugger — extract workflows, generate LangGraph agents, and distill lessons learned
version: 0.4.0
tools: [retrolens]
---

# RetroLens — AI Conversation Log Navigator & Workflow Extractor

Extract **reusable workflows**, **LangGraph agents**, and **lessons learned** from AI agent conversation logs. This skill guides you through debugger-style exploration, workflow identification, and experience distillation.

## Quick Start

```bash
pip install retrolens  # or: uv pip install retrolens
```

Get the SKILL.md path for agent discovery:
```bash
retrolens --skill-path
```

---

## Commands

### `cfg` — Set Working State (Do This First) ⭐

```bash
retrolens cfg set --path /path/to/logs   # Set log directory (persistent)
retrolens cfg set --source vscode        # Set default source type
retrolens cfg show                       # View current config
retrolens cfg clear                      # Reset to defaults
```

Once set, all other commands (`ls`, `read`, `extract`, `reflect`) use this path
and source automatically.

### `ls` — List Sessions

```bash
retrolens ls                          # List sessions from configured path
retrolens ls --limit 10 --json        # JSON output (for agents)
```

> **Prerequisite**: Run `retrolens cfg set --path <dir>` first. If you don't
> know where logs are, consult the **Discovery Skill** (`DISCOVERY.md` bundled
> with retrolens) for exploration strategies.

### `read` — Navigate Session (Debugger ⭐)

```bash
retrolens read <ID>               # Session overview
retrolens read <ID> --turn 1      # Turn detail
retrolens read <ID> -t 1 --tool 0 # Tool call detail
retrolens read <ID> --turns 1-5   # Turn range summaries
retrolens read <ID> --diff 1,3    # Compare turns
retrolens read <ID> --raw -t 1    # Raw JSON data
```

### `extract` — Workflow Extraction ⭐⭐

```bash
retrolens extract <ID> --json           # Session digest for workflow analysis
retrolens extract <ID> --max-turns 10   # Limit to first 10 turns
retrolens extract --from-yaml <file>     # Parse existing workflow YAML
retrolens extract --from-yaml <file> --langgraph  # Generate LangGraph code
```

### `reflect` — Lesson Extraction ⭐⭐

```bash
retrolens reflect <ID> --json            # Session digest with reflection hints
retrolens reflect <ID> --focus errors     # Focus on errors & fixes
retrolens reflect <ID> --focus practices  # Focus on effective practices
retrolens reflect <ID> --focus traps      # Focus on environment traps
```

### `show` — View Existing Artifacts

```bash
retrolens show                    # All artifacts in .retrolens/
retrolens show --type workflow    # Only workflow files
retrolens show --type lessons     # Only lesson files
```

---

## Workflow A: Extract Workflow & Generate Agent ⭐⭐⭐

**Goal**: Analyze a past session, identify the hidden workflow, write it as a YAML DSL, and optionally generate a LangGraph-based agent.

### Step-by-Step

1. **Find the target session**:
   ```bash
   retrolens ls --json
   ```
   Pick a session that accomplished a meaningful goal (look for sessions with >3 turns).

2. **Get the session digest**:
   ```bash
   retrolens extract <ID> --json
   ```
   This returns a structured digest with per-turn info: user messages, tools used, files touched, commands run.

3. **Identify the goal**: Read the first user message. What was the overall objective? This becomes the workflow's `goal` field.

4. **Map phases**: Analyze the turn sequence and identify distinct phases:

   | Phase Pattern | Indicators |
   |------|------|
   | **Research/Exploration** | `read_file`, `semantic_search`, `grep_search`, `list_dir` dominant |
   | **Planning** | User discussing approach, agent proposing structure, `vscode_askQuestions` |
   | **Implementation** | `create_file`, `replace_string_in_file`, `insert_edit_into_file` dominant |
   | **Testing/Validation** | `run_in_terminal` with test commands, error checking |
   | **Iteration/Fix** | Repeated edits after errors, user corrections |
   | **Documentation** | `create_file` on .md files, `memory` tool usage |

   Look for natural boundaries: topic shifts in user messages, tool usage pattern changes, or explicit phase transitions.

5. **For each phase, extract**:
   - **Entry condition**: What triggered this phase? (user request, previous phase output, error)
   - **Steps**: Ordered list of actions with tools used
   - **Decision points**: Where the approach branched (e.g., "if tests fail → go back to implementation")
   - **Exit condition**: What signals this phase is complete?
   - **Source turns**: Which turn numbers map to this phase

6. **Identify cross-cutting concerns**:
   - **State variables**: What data flows between phases? (file list, test results, configuration)
   - **Human checkpoints**: Where did the user need to approve/redirect?
   - **Dependencies**: Which phases must complete before others can start?

7. **Write the Workflow DSL** to `.retrolens/<name>.workflow.yaml`:
   Use the template from `retrolens --skill-path` (look in `skills/templates/WORKFLOW_DSL_TEMPLATE.yaml`).

   Key sections:
   ```yaml
   workflow:
     name: "my-workflow"
     goal: "What this workflow achieves"
     inputs: ["what it needs"]
     outputs: ["what it produces"]
     phases:
       - name: "research"
         steps:
           - description: "Read project structure"
             tools: ["read_file", "list_dir"]
   ```

8. **Generate LangGraph code** (optional):
   ```bash
   retrolens extract --from-yaml .retrolens/<name>.workflow.yaml --langgraph
   ```
   This generates a Python file with:
   - TypedDict state class
   - Node functions for each phase
   - Phase transition edges
   - Tool stubs ready to implement

### Workflow Analysis Tips

- **Long sessions (>10 turns)**: Use sub-agents to process in batches. Have sub-agent 1 read turns 1-5, sub-agent 2 read turns 6-10, then synthesize.
- **Repeated patterns**: If the same tool sequence appears 3+ times, that's a step worth extracting.
- **User corrections**: When the user says "no, do X instead" — the correct path is what belongs in the workflow.
- **Error-recovery loops**: If the agent retried something multiple times, the final successful approach is the one to document.
- **Parallel opportunities**: If two steps don't depend on each other, they can run in parallel in the LangGraph graph.

---

## Workflow B: Reflect & Extract Lessons ⭐⭐⭐

**Goal**: Analyze a session from a learning perspective — find errors, inefficiencies, good practices, and environment traps.

### Step-by-Step

1. **Get the reflection digest**:
   ```bash
   retrolens reflect <ID> --json
   ```
   Or focus on a specific area:
   ```bash
   retrolens reflect <ID> --focus errors --json
   ```

2. **Analyze each turn** through these lenses:

   **🔴 Errors & Fixes** — What went wrong?
   - Tool call failures
   - User corrections ("No, that's wrong...")
   - Multiple retries for the same thing
   - Wrong file/path assumptions

   **🟡 Inefficiency Patterns** — What was wasteful?
   - Reading files one by one instead of using grep/search
   - Exploring irrelevant code paths
   - Not using `--json` flag (manual parsing instead)
   - Repeated context gathering that could be cached

   **🟢 Effective Practices** — What worked well?
   - Smart tool selection (right tool for the job)
   - Progressive drilling (overview → detail)
   - Parallel processing (sub-agents)
   - Clean commit/save points

   **⚠️ Environment & Tool Traps**
   - API rate limits or quota exhaustion
   - Network/proxy issues
   - Version incompatibilities
   - Platform-specific paths or behaviors

   **📋 Agent Instructions**
   - Rules the user stated explicitly ("always use X")
   - Conventions discovered during the session
   - Tool preferences that should persist

3. **For each insight, record**:
   - Category (error/inefficiency/practice/trap/instruction)
   - Severity (critical/important/minor/info)
   - Title (concise, searchable)
   - Description (what happened)
   - Evidence (which turns, what tools)
   - Recommendation (what to do differently)

4. **Check existing lessons** to avoid duplicates:
   ```bash
   retrolens show --type lessons
   ```

5. **Write the output** to `.retrolens/LESSONS.md` using the REFLECTION_TEMPLATE.md template.

6. **Extract AGENTS.md instructions**: Any lesson that is an explicit rule or convention should also be added to the project's AGENTS.md or equivalent instruction file.

### Reflection Analysis Tips

- **Compare early vs late turns**: The agent often improves its approach — document what changed and why.
- **Count wasted turns**: If turns 3-7 were all failed attempts at one thing, that's a significant inefficiency.
- **Look for "aha moments"**: When the user provides a key insight that changed the approach — this is valuable domain knowledge.
- **Cross-reference with workflow**: Inefficiencies often reveal missing steps in the ideal workflow.

---

## Workflow C: Session Navigation (read-only)

**Goal**: Explore a session in detail using the debugger-style read command.

### Step-by-Step

1. List sessions: `retrolens ls --json`
2. Overview: `retrolens read <ID>`
3. Drill into interesting turns: `retrolens read <ID> --turn N`
4. Inspect specific tool calls: `retrolens read <ID> -t N --tool M`
5. Compare turns: `retrolens read <ID> --diff 1,3`

---

## Workflow D: Cross-Session Pattern Mining

**Goal**: Review multiple sessions to find recurring workflows and consolidate lessons.

### Step-by-Step

1. **List recent sessions**: `retrolens ls --limit 10 --json`
2. **Extract digests for each**: 
   ```bash
   retrolens extract <ID1> --json > /tmp/digest1.json
   retrolens extract <ID2> --json > /tmp/digest2.json
   ```
3. **Compare tool usage patterns** across sessions
4. **Identify recurring phases** that appear in multiple sessions
5. **Create a generalized workflow** that captures the common pattern
6. **Update LESSONS.md** with cross-session insights

---

## Output Templates

Templates are in the `skills/templates/` directory alongside this SKILL.md:

| Template | Purpose |
|------|------|
| `WORKFLOW_DSL_TEMPLATE.yaml` | Workflow DSL structure for `extract` |
| `LANGGRAPH_TEMPLATE.py` | Reference LangGraph code structure |
| `WORKFLOW_TEMPLATE.md` | Human-readable workflow documentation |
| `LESSONS_TEMPLATE.md` | Lessons learned output |
| `REFLECTION_TEMPLATE.md` | Full reflection report |

---

## For AI Agents — Best Practices

### Data Flow

```
cfg set → ls → pick session → extract/reflect → digest (JSON) → agent analysis → output files
```

### Key Rules

1. **Always use `--json`** for structured data processing.

2. **Use prefix matching** — you don't need the full UUID:
   ```bash
   retrolens read 01e7    # matches 01e70526-3d64-...
   ```

3. **Progressive drilling** — don't read everything at once:
   ```
   ls → overview → interesting turns → tool details
   ```

4. **For extract, use `--max-turns`** on very long sessions to avoid overwhelming context.

5. **For reflect, use `--focus`** to narrow the analysis scope.

6. **Workflow DSL → LangGraph is two steps**:
   ```bash
   # Step 1: Agent fills in YAML DSL from digest
   # Step 2: CLI generates code
   retrolens extract --from-yaml .retrolens/my.workflow.yaml --langgraph
   ```

7. **For long sessions (>10 turns)**, use sub-agents to process in parallel:
   - Sub-agent 1: `extract <ID> --max-turns 5 --json` → summarize phases 
   - Sub-agent 2: `read <ID> --turns 6-10` → summarize phases
   - Main agent: Synthesize into unified workflow

8. **Check before writing**: Always `retrolens show` first to read existing artifacts and avoid duplicates.

### Platform Integration

**VS Code Copilot Chat**: Add to AGENTS.md:
```
Use `retrolens` CLI to analyze conversation logs.
Key commands: extract (workflow), reflect (lessons), read (navigation).
Always use --json for structured output.
Run `retrolens --skill-path` for full SKILL.md.
```

**Claude Code**: Add to CLAUDE.md:
```
Use `retrolens` CLI to extract workflows and lessons from conversation logs.
See: retrolens --skill-path
```

**Cursor**: Add to .cursorrules:
```
When reviewing past sessions, use the retrolens CLI.
Commands: cfg, ls, extract, reflect, read, show.
Always use --json flag for structured output.
```

---

## Supported Log Formats

| Source | Format | Built-in Reader |
|------|------|------|
| VS Code Copilot Chat | JSONL incremental state | `vscode` |
| Claude Code | JSONL event stream | `claude_code` |
| RetroLens Native | JSON files per request/response | `retrolens` |

All platforms store sessions **per-project**. Use `retrolens cfg set --path <dir>` to point at a specific log directory.

> **Note**: Log storage paths change across platform versions. If `ls` returns nothing,
> consult the **Discovery Skill** (`DISCOVERY.md` bundled alongside this file) for exploration
> strategies to locate logs on your system.

### Adding New Log Formats

For unsupported platforms, see the **Discovery Skill** (`DISCOVERY.md`). It teaches agents how to:
1. Explore the filesystem to find log files
2. Sample and identify the format
3. Write a custom reader following the `BaseReader` interface
4. Register it with the reader registry
