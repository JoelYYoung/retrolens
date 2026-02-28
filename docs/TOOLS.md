# Rev-Agent MCP Tools Reference

Rev-Agent provides an MCP (Model Context Protocol) server that enables AI assistants to analyze recorded Agent session data.

## Tool List

### 1. `set_logs_path`

Set the path to the logs directory. Use this if auto-detection fails or you want to analyze logs from a different location.

**Parameters**:
| Parameter | Type | Required | Description |
|------|------|------|------|
| `path` | string | ✓ | Absolute path to the logs directory (should contain a 'sessions' subdirectory) |

**Return Example**:
```json
{
  "success": true,
  "logs_path": "/Users/joel/Projects/rev-agent/logs",
  "sessions_count": 4
}
```

---

### 2. `get_logs_path`

Get the current logs directory path being used for analysis.

**Parameters**: None

**Return Example**:
```json
{
  "logs_path": "/Users/joel/Projects/rev-agent/logs",
  "status": "configured",
  "hint": "Use set_logs_path to configure if needed"
}
```

---

### 3. `list_sessions`

List all recorded Agent sessions.

**Parameters**: None

**Return Example**:
```json
[
  {
    "session_id": "1194af85",
    "start_time": "2026-02-28T10:00:00",
    "client": "claude-code",
    "model": "claude-sonnet-4-20250514"
  }
]
```

---

### 4. `get_session_summary`

Get summary information for a specified session, including number of rounds, tool call statistics, etc.

**Parameters**:
| Parameter | Type | Required | Description |
|------|------|------|------|
| `session_id` | string | ✓ | Session ID |

**Return Example**:
```json
{
  "session_id": "1194af85",
  "total_rounds": 15,
  "total_requests": 30,
  "tool_calls_count": 45,
  "unique_tools": ["read_file", "grep_search", "run_in_terminal"]
}
```

---

### 5. `list_rounds`

List all rounds in a session along with their summaries. Each "round" represents a complete user question → Agent response cycle.

**Parameters**:
| Parameter | Type | Required | Description |
|------|------|------|------|
| `session_id` | string | ✓ | Session ID |

**Return Example**:
```json
[
  {
    "round": 1,
    "sequences": [1, 2],
    "user_message": "Help me analyze the structure of this project...",
    "tool_calls": ["read_file", "list_dir"],
    "time_range": "2026-02-28T10:00:00 - 2026-02-28T10:01:30"
  }
]
```

---

### 6. `get_round_detail`

Get complete details of a specific round, including all tool calls and responses.

**Parameters**:
| Parameter | Type | Required | Description |
|------|------|------|------|
| `session_id` | string | ✓ | Session ID |
| `round_number` | integer | ✓ | Round number (starting from 1) |

**Return Example**:
```json
{
  "round_number": 1,
  "user_message": "Help me analyze this project",
  "tool_calls": [
    {"name": "read_file", "input": {"path": "README.md"}}
  ],
  "final_response": "This project is..."
}
```

---

### 7. `get_round_new_info`

Get new information in a round, including user messages, tool calls, file operations, etc. Used to quickly understand what happened in each round.

**Parameters**:
| Parameter | Type | Required | Description |
|------|------|------|------|
| `session_id` | string | ✓ | Session ID |
| `round_number` | integer | ✓ | Round number |

---

### 8. `get_round_response`

Get the final response text of a round.

**Parameters**:
| Parameter | Type | Required | Description |
|------|------|------|------|
| `session_id` | string | ✓ | Session ID |
| `round_number` | integer | ✓ | Round number |

---

### 9. `get_request_detail`

Get detailed content of a raw request (for in-depth analysis).

**Parameters**:
| Parameter | Type | Required | Description |
|------|------|------|------|
| `session_id` | string | ✓ | Session ID |
| `sequence` | integer | ✓ | Request sequence number |

---

### 10. `get_response_detail`

Get detailed content of a raw response (for in-depth analysis).

**Parameters**:
| Parameter | Type | Required | Description |
|------|------|------|------|
| `session_id` | string | ✓ | Session ID |
| `sequence` | integer | ✓ | Response sequence number |

---

### 11. `compare_rounds`

Compare differences between two rounds to help understand changes in Agent behavior.

**Parameters**:
| Parameter | Type | Required | Description |
|------|------|------|------|
| `session_id` | string | ✓ | Session ID |
| `round1` | integer | ✓ | First round number |
| `round2` | integer | ✓ | Second round number |
