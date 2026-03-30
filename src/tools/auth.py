"""
Authentication tools for Kroger OAuth2.

Provides tools to check Kroger auth status and initiate the OAuth flow.
Split into two steps so the MCP client can show the auth URL to the user
before we block waiting for the callback.

Delegates to v0/src/kroger_mvp/oauth_handler.py for token management.
"""

import logging
import uuid
from datetime import datetime

from src.mcp_instance import mcp
from src.config import get_db_session
from src.oauth_callback import OAuthCallbackServer

from src.models import KrogerOAuthToken
from src.kroger.oauth_handler import OAuthHandler
from src.exceptions import KrogerAPIError

logger = logging.getLogger(__name__)

# Module-level state for the pending OAuth flow.
# Only one flow can be active at a time (single-user MVP).
_pending_oauth: dict | None = None


@mcp.tool()
def get_kroger_auth_status(user_id: str) -> dict:
    """Check the current Kroger authentication status for a user.

    Returns whether the user has a valid, expired, or missing Kroger OAuth token.

    Args:
        user_id: The user ID to check authentication status for.

    Returns:
        A dict with 'status' key: 'connected', 'expired', or 'not_connected'.
    """
    logger.info(
        "Tool invoked: get_kroger_auth_status | timestamp=%s | user_id=%s",
        datetime.utcnow().isoformat(),
        user_id,
    )

    db = None
    try:
        db = get_db_session()
        token = (
            db.query(KrogerOAuthToken)
            .filter(KrogerOAuthToken.user_id == user_id)
            .order_by(KrogerOAuthToken.updated_at.desc())
            .first()
        )

        if not token:
            logger.info("No OAuth token found for user %s", user_id)
            return {"status": "not_connected"}

        now = datetime.utcnow()

        if token.expires_at > now:
            logger.info("Valid token found for user %s, expires_at=%s", user_id, token.expires_at.isoformat())
            return {
                "status": "connected",
                "expires_at": token.expires_at.isoformat(),
            }

        # Token is expired — attempt refresh
        logger.info("Token expired for user %s, attempting refresh", user_id)
        try:
            oauth_handler = OAuthHandler(db)
            oauth_handler.refresh_access_token(token.refresh_token, user_id)
            refreshed_token = (
                db.query(KrogerOAuthToken)
                .filter(KrogerOAuthToken.user_id == user_id)
                .order_by(KrogerOAuthToken.updated_at.desc())
                .first()
            )
            logger.info("Token refreshed for user %s", user_id)
            return {
                "status": "connected",
                "expires_at": refreshed_token.expires_at.isoformat(),
            }
        except KrogerAPIError as e:
            logger.warning("Token refresh failed for user %s: %s", user_id, str(e))
            return {
                "status": "expired",
                "message": "Token expired. Please reconnect.",
            }

    except KrogerAPIError as e:
        logger.error("Kroger API error in get_kroger_auth_status: %s", str(e))
        return {"error_code": "KROGER_API_ERROR", "message": str(e)}
    except Exception as e:
        logger.error("Unexpected error in get_kroger_auth_status: %s", str(e), exc_info=True)
        return {"error_code": "INTERNAL_ERROR", "message": f"An unexpected error occurred: {str(e)}"}
    finally:
        if db is not None:
            db.close()


@mcp.tool()
def connect_kroger(user_id: str, port: int = 8400) -> dict:
    """Start the Kroger OAuth2 connection flow (step 1 of 2).

    Starts a temporary local HTTP server for the OAuth callback and returns
    an authorization URL. The user MUST open this URL in their browser and
    complete the Kroger login. After that, call ``complete_kroger_connection``
    to finish the flow.

    This tool returns immediately so the MCP client can display the URL.

    Args:
        user_id: The user ID to associate the Kroger tokens with.
        port: Preferred port for the OAuth callback server (default 8400).

    Returns:
        A dict with 'auth_url' to open in a browser and 'port' of the
        callback server, or a structured error.
    """
    global _pending_oauth

    logger.info(
        "Tool invoked: connect_kroger | timestamp=%s | user_id=%s | port=%d",
        datetime.utcnow().isoformat(),
        user_id,
        port,
    )

    # Clean up any previous pending flow
    if _pending_oauth is not None:
        old_server = _pending_oauth.get("callback_server")
        if old_server is not None:
            try:
                old_server.stop()
            except Exception:
                pass
        _pending_oauth = None

    try:
        db = get_db_session()
        oauth_handler = OAuthHandler(db)

        state = uuid.uuid4().hex

        callback_server = OAuthCallbackServer(expected_state=state, port=port)
        try:
            actual_port = callback_server.start()
        except OSError as exc:
            logger.error("Failed to start OAuth callback server: %s", exc)
            db.close()
            return {
                "error_code": "PORT_CONFLICT",
                "message": f"Could not start OAuth callback server: {exc}",
            }

        callback_redirect_uri = f"http://127.0.0.1:{actual_port}/callback"
        oauth_handler.redirect_uri = callback_redirect_uri
        oauth_handler.scope = "product.compact cart.basic:write profile.compact"

        auth_url = oauth_handler.get_authorization_url(state=state)

        # Stash everything needed for step 2
        _pending_oauth = {
            "user_id": user_id,
            "state": state,
            "callback_server": callback_server,
            "redirect_uri": callback_redirect_uri,
            "db": db,
            "port": actual_port,
        }

        logger.info(
            "OAuth flow started — callback server on port %d, awaiting browser login",
            actual_port,
        )

        return {
            "status": "awaiting_browser_login",
            "auth_url": auth_url,
            "port": actual_port,
            "message": (
                "Please open the auth_url in your browser and log in to Kroger. "
                "After you complete the login, call complete_kroger_connection to finish."
            ),
        }

    except KrogerAPIError as exc:
        logger.error("Kroger API error in connect_kroger: %s", exc)
        return {"error_code": "KROGER_API_ERROR", "message": str(exc)}
    except Exception as exc:
        logger.error("Unexpected error in connect_kroger: %s", exc, exc_info=True)
        return {"error_code": "INTERNAL_ERROR", "message": f"An unexpected error occurred: {exc}"}


@mcp.tool()
def complete_kroger_connection(timeout: int = 300) -> dict:
    """Finish the Kroger OAuth2 connection flow (step 2 of 2).

    Waits for the user to complete the browser-based Kroger login (started
    by ``connect_kroger``), then exchanges the authorization code for tokens.

    Call this AFTER the user has opened the auth URL in their browser.

    Args:
        timeout: Maximum seconds to wait for the callback (default 300).

    Returns:
        A dict with 'status': 'connected' on success, or a structured error.
    """
    global _pending_oauth

    logger.info(
        "Tool invoked: complete_kroger_connection | timestamp=%s | timeout=%d",
        datetime.utcnow().isoformat(),
        timeout,
    )

    if _pending_oauth is None:
        return {
            "error_code": "NO_PENDING_FLOW",
            "message": "No pending OAuth flow. Call connect_kroger first.",
        }

    callback_server = _pending_oauth["callback_server"]
    user_id = _pending_oauth["user_id"]
    redirect_uri = _pending_oauth["redirect_uri"]
    db = _pending_oauth["db"]

    try:
        code = callback_server.wait_for_code(timeout=timeout)

        if code is None:
            logger.warning("OAuth callback timed out for user %s", user_id)
            return {
                "error_code": "AUTH_TIMEOUT",
                "message": f"OAuth callback timed out after {timeout} seconds. Please try again with connect_kroger.",
            }

        # Exchange the code for tokens
        oauth_handler = OAuthHandler(db)
        oauth_handler.redirect_uri = redirect_uri
        oauth_handler.scope = "product.compact cart.basic:write profile.compact"
        oauth_handler.exchange_code_for_token(code, user_id)

        logger.info("Successfully connected Kroger account for user %s", user_id)
        return {"status": "connected"}

    except KrogerAPIError as exc:
        logger.error("Kroger API error in complete_kroger_connection: %s", exc)
        return {"error_code": "KROGER_API_ERROR", "message": str(exc)}
    except Exception as exc:
        logger.error("Unexpected error in complete_kroger_connection: %s", exc, exc_info=True)
        return {"error_code": "INTERNAL_ERROR", "message": f"An unexpected error occurred: {exc}"}
    finally:
        # Always clean up
        try:
            callback_server.stop()
        except Exception:
            pass
        try:
            db.close()
        except Exception:
            pass
        _pending_oauth = None
