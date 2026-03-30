"""
Shared MCP server instance.

This module exists to break circular imports between server.py and tool modules.
Tool modules import `mcp` from here instead of from server.py.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("agent-grocery")
