"""
Memory tools for persistent grocery knowledge.

Provides tools to read and write markdown files that serve as the agent's
long-term memory: grocery profile, receipt history, and shopping notes.
The DB is only used for OAuth tokens — everything else lives in markdown.
"""

import logging
from datetime import datetime
from pathlib import Path

from src.mcp_instance import mcp

logger = logging.getLogger(__name__)

# Memory files live in data/memory/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_MEMORY_DIR = _PROJECT_ROOT / "data" / "memory"
_PROFILE_FILE = _MEMORY_DIR / "grocery_profile.md"
_HISTORY_FILE = _MEMORY_DIR / "shopping_history.md"
_RECEIPTS_DIR = _MEMORY_DIR / "receipts"


def _ensure_dirs():
    """Create memory directories if they don't exist."""
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    _RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)


@mcp.tool()
def read_grocery_profile() -> dict:
    """Read the user's grocery profile.

    The grocery profile contains the user's typical shopping patterns,
    preferences, usual items, brand preferences, and any notes about
    their grocery habits. Returns empty content if no profile exists yet.

    Returns:
        A dict with 'content' (the markdown text) and 'exists' (bool).
    """
    logger.info("Tool invoked: read_grocery_profile | timestamp=%s", datetime.utcnow().isoformat())

    try:
        _ensure_dirs()
        if _PROFILE_FILE.exists():
            content = _PROFILE_FILE.read_text(encoding="utf-8")
            return {"content": content, "exists": True}
        return {
            "content": "",
            "exists": False,
            "message": "No grocery profile yet. Create one after learning about the user's shopping habits.",
        }
    except Exception as exc:
        logger.error("Error reading grocery profile: %s", exc, exc_info=True)
        return {"error_code": "INTERNAL_ERROR", "message": str(exc)}


@mcp.tool()
def update_grocery_profile(content: str) -> dict:
    """Update the user's grocery profile.

    Write or overwrite the grocery profile markdown file. This should contain
    a summary of the user's shopping patterns, typical items, preferences,
    brand choices, and any notes. Update this after each shopping session
    to keep it current.

    The profile should be written in a natural, readable format. Example:

    ```
    # Grocery Profile

    ## Typical Weekly Items
    - Milk (Kroger brand, 1 gal) — every week
    - Bananas (6 count) — every week
    - Chicken nuggets (Tyson) — every 2 weeks
    - Dave's Killer Bread — every week

    ## Preferences
    - Prefers organic dairy
    - Store brand OK for snacks and basics
    - Likes to try new cereals

    ## Notes
    - Allergic to shellfish
    - Kids prefer Tyson nuggets over store brand
    ```

    Args:
        content: The full markdown content for the grocery profile.

    Returns:
        A dict confirming the update.
    """
    logger.info("Tool invoked: update_grocery_profile | timestamp=%s", datetime.utcnow().isoformat())

    try:
        _ensure_dirs()
        _PROFILE_FILE.write_text(content, encoding="utf-8")
        logger.info("Grocery profile updated (%d chars)", len(content))
        return {"status": "updated", "message": "Grocery profile saved."}
    except Exception as exc:
        logger.error("Error updating grocery profile: %s", exc, exc_info=True)
        return {"error_code": "INTERNAL_ERROR", "message": str(exc)}


@mcp.tool()
def read_shopping_history() -> dict:
    """Read the shopping history log.

    The shopping history tracks past shopping sessions: what was ordered,
    when, any substitutions made, and outcomes. Returns empty if no
    history exists yet.

    Returns:
        A dict with 'content' (the markdown text) and 'exists' (bool).
    """
    logger.info("Tool invoked: read_shopping_history | timestamp=%s", datetime.utcnow().isoformat())

    try:
        _ensure_dirs()
        if _HISTORY_FILE.exists():
            content = _HISTORY_FILE.read_text(encoding="utf-8")
            return {"content": content, "exists": True}
        return {
            "content": "",
            "exists": False,
            "message": "No shopping history yet.",
        }
    except Exception as exc:
        logger.error("Error reading shopping history: %s", exc, exc_info=True)
        return {"error_code": "INTERNAL_ERROR", "message": str(exc)}


@mcp.tool()
def append_shopping_history(entry: str) -> dict:
    """Append an entry to the shopping history log.

    Add a new entry after each shopping session. Each entry should include
    the date, what was ordered, any substitutions, and the total cost.

    Example entry:
    ```
    ## 2025-06-15 — Weekly Grocery Run
    - 12 items added to Kroger cart
    - Total: ~$47.50
    - Substituted Dave's bagels for Kroger brand (saved $3.50)
    - Couldn't find organic spinach, skipped
    - Added extra chicken nuggets (running low)
    ```

    Args:
        entry: The markdown entry to append.

    Returns:
        A dict confirming the append.
    """
    logger.info("Tool invoked: append_shopping_history | timestamp=%s", datetime.utcnow().isoformat())

    try:
        _ensure_dirs()
        # Append with a newline separator
        with open(_HISTORY_FILE, "a", encoding="utf-8") as f:
            if _HISTORY_FILE.exists() and _HISTORY_FILE.stat().st_size > 0:
                f.write("\n\n")
            f.write(entry)
        logger.info("Shopping history entry appended (%d chars)", len(entry))
        return {"status": "appended", "message": "Shopping history entry added."}
    except Exception as exc:
        logger.error("Error appending shopping history: %s", exc, exc_info=True)
        return {"error_code": "INTERNAL_ERROR", "message": str(exc)}


@mcp.tool()
def save_receipt_notes(filename: str, content: str) -> dict:
    """Save receipt notes as a markdown file.

    Save extracted receipt data as a readable markdown file. Use a
    descriptive filename like "2025-06-15_amazon_fresh.md".

    Args:
        filename: Filename for the receipt (e.g. "2025-06-15_amazon_fresh.md").
        content: The markdown content with receipt items and details.

    Returns:
        A dict confirming the save.
    """
    logger.info(
        "Tool invoked: save_receipt_notes | timestamp=%s | filename=%s",
        datetime.utcnow().isoformat(),
        filename,
    )

    try:
        _ensure_dirs()
        # Sanitize filename
        safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ").strip()
        if not safe_name.endswith(".md"):
            safe_name += ".md"

        filepath = _RECEIPTS_DIR / safe_name
        filepath.write_text(content, encoding="utf-8")
        logger.info("Receipt notes saved to %s (%d chars)", safe_name, len(content))
        return {
            "status": "saved",
            "filename": safe_name,
            "message": f"Receipt saved as {safe_name}.",
        }
    except Exception as exc:
        logger.error("Error saving receipt notes: %s", exc, exc_info=True)
        return {"error_code": "INTERNAL_ERROR", "message": str(exc)}


@mcp.tool()
def list_receipt_files() -> dict:
    """List all saved receipt markdown files.

    Returns:
        A dict with a 'files' list of receipt filenames.
    """
    logger.info("Tool invoked: list_receipt_files | timestamp=%s", datetime.utcnow().isoformat())

    try:
        _ensure_dirs()
        files = sorted(
            [f.name for f in _RECEIPTS_DIR.glob("*.md")],
            reverse=True,
        )
        return {"files": files, "count": len(files)}
    except Exception as exc:
        logger.error("Error listing receipt files: %s", exc, exc_info=True)
        return {"error_code": "INTERNAL_ERROR", "message": str(exc)}


@mcp.tool()
def read_receipt_file(filename: str) -> dict:
    """Read a specific receipt markdown file.

    Args:
        filename: The receipt filename to read.

    Returns:
        A dict with 'content' (the markdown text).
    """
    logger.info(
        "Tool invoked: read_receipt_file | timestamp=%s | filename=%s",
        datetime.utcnow().isoformat(),
        filename,
    )

    try:
        _ensure_dirs()
        filepath = _RECEIPTS_DIR / filename
        if not filepath.exists():
            return {"error_code": "NOT_FOUND", "message": f"Receipt file '{filename}' not found."}
        content = filepath.read_text(encoding="utf-8")
        return {"content": content, "filename": filename}
    except Exception as exc:
        logger.error("Error reading receipt file: %s", exc, exc_info=True)
        return {"error_code": "INTERNAL_ERROR", "message": str(exc)}
