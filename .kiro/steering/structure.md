# Project Structure

```
grocery/
├── src/                        # MCP server source code
│   ├── server.py               # Entry point — FastMCP stdio server
│   ├── mcp_instance.py         # Shared FastMCP instance
│   ├── config.py               # YAML config loader with ${ENV_VAR} substitution
│   ├── database.py             # SQLAlchemy engine and session (SQLite)
│   ├── models.py               # DB models: User, KrogerOAuthToken
│   ├── exceptions.py           # Custom exception classes
│   ├── oauth_callback.py       # Temporary HTTP server for OAuth redirects
│   ├── kroger/
│   │   └── oauth_handler.py    # Kroger OAuth2 token exchange and refresh
│   ├── tools/                  # MCP tool definitions (one file per domain)
│   │   ├── auth.py             # connect_kroger, complete_kroger_connection, get_kroger_auth_status
│   │   ├── cart.py             # add_to_cart
│   │   ├── products.py         # search_kroger_products, get_product_details
│   │   ├── location.py         # set_store_location
│   │   └── memory.py           # Grocery profile, shopping history, receipt notes
│   └── utils/
│       └── api_logging.py      # Structured API call logging with redaction
├── config/
│   └── app.yaml                # App configuration (Kroger endpoints, DB, etc.)
├── data/
│   ├── grocery.db              # SQLite database (OAuth tokens only)
│   ├── user_preferences.json   # Store location preferences
│   └── memory/                 # Agent long-term memory (markdown files)
│       ├── grocery_profile.md
│       ├── shopping_history.md
│       └── receipts/           # Saved receipt notes
├── tests/                      # Unit tests for MCP tools
├── docs/
│   └── claude_project_instructions.md  # Instructions for Claude Desktop
├── .env                        # Secrets: KROGER_CLIENT_ID, etc. (git-ignored)
├── .env.example                # Template for .env
├── pyproject.toml              # Python dependencies
├── claude_desktop_config.example.json  # Example MCP config for Claude Desktop
└── README.md
```

## Key Principles

- **MCP-first**: This is a tool server, not a web app. No HTTP API, no frontend.
- **Claude is the brain**: All grocery logic lives in Claude. The server is just the Kroger API bridge + storage.
- **File-based memory**: Grocery profile, history, and receipts are markdown files — easy to read, edit, and version.
- **Minimal DB**: SQLite only stores OAuth tokens. Everything else is files.
- **Single-user MVP**: Hardcoded `user_id = "default"`. No multi-user auth.
