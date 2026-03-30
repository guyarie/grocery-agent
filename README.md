# Agent Grocery — Kroger MCP Server for Claude Desktop

An [MCP](https://modelcontextprotocol.io/) tool server that turns Claude Desktop into a grocery shopping assistant. Connect your Kroger account, search products, build a cart, and check out — all through natural conversation.

## What It Does

- **Connect to Kroger** — OAuth2 flow opens in your browser, tokens stored locally
- **Search products** — Find items in Kroger's catalog with real-time pricing at your store
- **Add to cart** — Build your Kroger cart by UPC, then check out on kroger.com
- **Remember preferences** — Claude maintains a grocery profile with your usual items, brands, and patterns
- **Track history** — Shopping sessions and receipt notes saved as markdown files

## Prerequisites

- [Python 3.11+](https://www.python.org/) (managed via [pyenv](https://github.com/pyenv/pyenv))
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Claude Desktop](https://claude.ai/download)
- [Kroger Developer Account](https://developer.kroger.com/) (free)

## Setup

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/grocery.git
cd grocery
pyenv install 3.11.9
pyenv local 3.11.9
uv venv
uv pip install -e .
```

### 2. Configure credentials

```bash
cp .env.example .env
```

Edit `.env` and add your Kroger API credentials:

```
KROGER_CLIENT_ID=your_client_id
KROGER_CLIENT_SECRET=your_client_secret
KROGER_TEST_LOCATION_ID=your_store_id
```

Get your credentials at [developer.kroger.com](https://developer.kroger.com/). When registering your app, add this as a redirect URI:

```
http://127.0.0.1:8400/callback
```

### 3. Configure Claude Desktop

Add the MCP server to your Claude Desktop config. On Windows, edit:

```
%LOCALAPPDATA%\Packages\Claude_<id>\LocalCache\Roaming\Claude\claude_desktop_config.json
```

Add the `agent-grocery` server:

```json
{
  "mcpServers": {
    "agent-grocery": {
      "command": "C:\\path\\to\\grocery\\.venv\\Scripts\\python.exe",
      "args": ["-m", "src.server"],
      "cwd": "C:\\path\\to\\grocery",
      "env": {
        "PYTHONPATH": "C:\\path\\to\\grocery"
      }
    }
  }
}
```

Replace `C:\\path\\to\\grocery` with your actual project path. See `claude_desktop_config.example.json` for reference.

### 4. Restart Claude Desktop

Quit and relaunch Claude Desktop. The MCP server starts automatically.

## Usage

In Claude Desktop, just start talking about groceries:

> "Let's do a grocery run this week"

Claude will:
1. Check your Kroger connection (and help you connect if needed)
2. Read your grocery profile to know your usual items
3. Help you build a shopping list
4. Search Kroger for each item with real prices
5. Add everything to your cart
6. Give you a link to check out on kroger.com

## MCP Tools

| Tool | Description |
|------|-------------|
| `server_status` | Check server uptime and startup time |
| `get_kroger_auth_status` | Check if Kroger is connected |
| `connect_kroger` | Start OAuth flow (returns URL to open) |
| `complete_kroger_connection` | Finish OAuth after browser login |
| `set_store_location` | Find/set preferred Kroger store |
| `search_kroger_products` | Search product catalog |
| `get_product_details` | Get full product info |
| `add_to_cart` | Add items to Kroger cart |
| `read_grocery_profile` | Read shopping preferences |
| `update_grocery_profile` | Update shopping preferences |
| `read_shopping_history` | Read past shopping sessions |
| `append_shopping_history` | Log a shopping session |
| `save_receipt_notes` | Save receipt as markdown |
| `list_receipt_files` | List saved receipts |
| `read_receipt_file` | Read a saved receipt |

## Project Structure

```
├── src/
│   ├── server.py              # MCP server entry point (stdio)
│   ├── config.py              # YAML config + env var loading
│   ├── database.py            # SQLAlchemy (SQLite, OAuth tokens only)
│   ├── models.py              # User + KrogerOAuthToken models
│   ├── oauth_callback.py      # Temp HTTP server for OAuth redirect
│   ├── kroger/
│   │   └── oauth_handler.py   # Kroger OAuth2 token management
│   └── tools/                 # MCP tool definitions
│       ├── auth.py            # Authentication tools
│       ├── cart.py            # Cart management
│       ├── products.py        # Product search
│       ├── location.py        # Store location
│       └── memory.py          # Agent memory (profile, history, receipts)
├── config/app.yaml            # App configuration
├── data/                      # Local data (DB, preferences, memory)
├── tests/                     # Unit tests
└── docs/                      # Claude Desktop instructions
```

## Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest tests/

# Format
black src/ tests/

# Lint
ruff check src/ tests/
```

## License

[MIT](LICENSE) © Guy Arie
