# Technology Stack

## Runtime

- **MCP Framework**: FastMCP (`mcp[cli]`) — Model Context Protocol server over stdio
- **Database**: SQLAlchemy ORM with SQLite (OAuth tokens only)
- **HTTP Client**: `requests` for Kroger API calls
- **Config**: YAML (`pyyaml`) with `${ENV_VAR}` substitution via `python-dotenv`
- **Python**: 3.11+ (managed by pyenv, specified in `.python-version`)
- **Package Manager**: uv

### Dependencies

```
mcp[cli]>=1.0.0
sqlalchemy>=2.0.0
requests>=2.32.0
python-dotenv>=1.0.0
pyyaml>=6.0.0
```

### Dev Dependencies

```
pytest>=8.0.0
black>=24.0.0
ruff>=0.6.0
mypy>=1.11.0
```

## Setup

```bash
# Install Python 3.11 via pyenv
pyenv install 3.11.9
pyenv local 3.11.9

# Create venv and install
uv venv
uv pip install -e ".[dev]"

# Copy .env.example to .env and fill in Kroger credentials
cp .env.example .env
```

## Running

The MCP server is launched by Claude Desktop as a stdio process. Configure it in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agent-grocery": {
      "command": "path/to/.venv/Scripts/python.exe",
      "args": ["-m", "src.server"]
    }
  }
}
```

See `claude_desktop_config.example.json` for a full example.

## Testing

```bash
# Run all tests
pytest tests/

# Run a specific test file
pytest tests/test_auth_tools.py -v
```

## Code Quality

- **Formatting**: `black` (line length 100)
- **Linting**: `ruff`
- **Type checking**: `mypy`

## Important Notes

- The server runs over stdio — no HTTP endpoints, no ports (except the temporary OAuth callback on 127.0.0.1:8400-8410)
- `.env` holds secrets (KROGER_CLIENT_ID, KROGER_CLIENT_SECRET, etc.) — never commit it
- `config/app.yaml` holds non-secret configuration (API URLs, DB path, etc.)
- The SQLite DB at `data/grocery.db` only stores OAuth tokens
- All grocery data (profile, history, receipts) lives as markdown in `data/memory/`
