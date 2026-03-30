"""
Agent Grocery V1 — MCP Tool Server

FastMCP server that exposes grocery shopping capabilities as MCP tools.
Wraps existing v0/ Kroger services and runs as a local stdio process
launched by Claude Desktop (or any MCP-compatible client).
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

# Ensure logs directory exists
_log_dir = Path(__file__).resolve().parent.parent / "logs"
_log_dir.mkdir(exist_ok=True)

# Configure logging to logs/mcp_server.log
logging.basicConfig(
    filename=str(_log_dir / "mcp_server.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Import the shared MCP instance (avoids circular imports with tool modules)
from src.mcp_instance import mcp  # noqa: E402

# Import tool modules to trigger @mcp.tool() registration
import src.tools.auth  # noqa: F401, E402
import src.tools.cart  # noqa: F401, E402
import src.tools.location  # noqa: F401, E402
import src.tools.memory  # noqa: F401, E402
import src.tools.products  # noqa: F401, E402

logger.info("Agent Grocery MCP server initialized with all tool modules")

# Capture startup timestamp for diagnostics
_SERVER_STARTED_AT = datetime.now(timezone.utc)
logger.info("Server startup timestamp: %s", _SERVER_STARTED_AT.isoformat())


@mcp.tool()
def server_status() -> dict:
    """Return MCP server diagnostic info including startup time.

    Useful for confirming the server restarted and is running the latest code.

    Returns:
        A dict with started_at (ISO timestamp) and uptime_seconds.
    """
    now = datetime.now(timezone.utc)
    uptime = (now - _SERVER_STARTED_AT).total_seconds()
    return {
        "started_at": _SERVER_STARTED_AT.isoformat(),
        "uptime_seconds": round(uptime, 1),
        "current_time": now.isoformat(),
    }


mcp.run(transport="stdio")
