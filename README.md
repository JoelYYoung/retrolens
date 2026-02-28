# AgentInspector

A transparent proxy and MCP-based analysis tool for inspecting AI coding agent LLM session records.

> **Currently Supported**: Claude Code

## Features

- **API Proxy**: Intercept Anthropic/OpenAI API requests and responses
- **Session Recording**: Persist all communication data for analysis
- **MCP Server**: Analyze sessions via Model Context Protocol
- **Round-based Analysis**: Understand agent behavior round by round

## Quick Start

### 1. Install

```bash
# Clone the repo
git clone https://github.com/yourname/agent-inspector.git
cd agent-inspector

# Install dependencies
pip install -r requirements.txt

# Or with uv
uv sync
```

### 2. Configure Listener

```bash
# Copy example config and edit
cp .env.example .env
vim .env
```

**`.env` file settings** (for the proxy server):
| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_BASE_URL` | Backend API endpoint (OpenAI-compatible) | `https://api.deepseek.com/v1` |
| `REV_AGENT_PORT` | Proxy server port | `8080` |
| `HTTP_PROXY` | Optional HTTP proxy | `http://127.0.0.1:7890` |

### 3. Start Listener

```bash
# Start the proxy server
python -m tools.listener.adapter

# Or with uv
uv run python -m tools.listener.adapter
```

The proxy will start at `http://localhost:8080`.

### 4. Configure Your Agent

Point your AI coding agent to use the proxy. The API key from Claude Code will be passed through to the backend.

```bash
# For Claude Code - set both the proxy URL and your API key
export ANTHROPIC_BASE_URL=http://localhost:8080
export ANTHROPIC_API_KEY=sk-ant-your-key-here  # Your actual Anthropic API key
```

> **How it works**: Claude Code sends requests with your `ANTHROPIC_API_KEY` in the headers. 
> The proxy intercepts the request, logs it, converts to OpenAI format, and forwards to 
> `OPENAI_BASE_URL` with the same API key.

## Using the MCP Server

Add to your Claude Desktop `settings.json`:

```json
{
  "mcpServers": {
    "agent-session": {
      "command": "python",
      "args": ["-m", "tools.analyzer.mcp_server"],
      "cwd": "/path/to/rev-agent"
    }
  }
}
```

Then ask Claude to analyze your recorded sessions:

```
> List all recorded sessions
> Show me round 3 of session abc123
> What tools did the agent use in round 5?
```

### 🎯 Advanced Analysis Prompts

Try these sophisticated prompts to unlock deeper insights:

```
> Analyze the cognitive workflow of session abc123: How did the agent decompose
  the problem? What was its exploration strategy vs exploitation strategy?

> Compare rounds 5 and 12 of session abc123. What new information did the agent
  discover that changed its approach? Show me the "aha moment".

> Trace the agent's hypothesis evolution: What assumptions did it make initially,
  and how did tool results challenge or confirm these assumptions?

> Visualize the agent's tool dependency graph for this session. Which tools
  were used as "scouts" (gathering info) vs "executors" (making changes)?

> Find the "dead ends" - rounds where the agent backtracked or abandoned an
  approach. What triggered these pivots?
```

See [docs/TOOLS.md](docs/TOOLS.md) for complete MCP tool reference.

## CLI Usage

```bash
# List sessions
python -m tools.analyzer.cli list

# Show session details
python -m tools.analyzer.cli show <session_id>

# Analyze session
python -m tools.analyzer.cli analyze <session_id>
```

## Project Structure

```
agent-inspector/
├── tools/
│   ├── listener/      # API proxy server
│   │   ├── adapter.py # FastAPI proxy
│   │   └── storage.py # Session storage
│   └── analyzer/      # Analysis tools
│       ├── cli.py     # CLI interface
│       ├── engine.py  # Analysis engine
│       └── mcp_server.py  # MCP server
├── docs/
│   └── TOOLS.md       # MCP tools reference
├── .env.example       # Configuration template
└── README.md
```

## License

MIT - See [LICENSE](LICENSE) for details.
