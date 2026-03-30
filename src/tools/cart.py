"""
Cart management tools.

Provides tools to add items to the user's Kroger cart.
Validates UPCs, checks auth, and calls the Kroger Cart API.
"""

import logging
from datetime import datetime

import requests

from src.mcp_instance import mcp
from src.config import get_db_session, get_kroger_config

from src.kroger.oauth_handler import OAuthHandler
from src.exceptions import KrogerAPIError

logger = logging.getLogger(__name__)

VALID_MODALITIES = {"PICKUP", "DELIVERY"}
KROGER_CART_ENDPOINT = "/v1/cart/add"
KROGER_CHECKOUT_URL = "https://www.kroger.com/cart"


def _validate_items(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Validate cart items and partition into valid/invalid.

    Returns:
        Tuple of (valid_items, failed_items) where failed_items have error info.
    """
    valid = []
    failed = []

    for i, item in enumerate(items):
        upc = item.get("upc")
        quantity = item.get("quantity", 1)
        modality = item.get("modality", "PICKUP")

        # UPC must be exactly 13 characters
        if not isinstance(upc, str) or len(upc) != 13:
            failed.append({
                "index": i,
                "upc": upc,
                "reason": "UPC must be exactly 13 characters",
                "error_code": "VALIDATION_ERROR",
            })
            continue

        # Quantity must be >= 1
        if not isinstance(quantity, int) or quantity < 1:
            failed.append({
                "index": i,
                "upc": upc,
                "reason": "Quantity must be an integer >= 1",
                "error_code": "VALIDATION_ERROR",
            })
            continue

        # Modality must be PICKUP or DELIVERY
        if modality not in VALID_MODALITIES:
            failed.append({
                "index": i,
                "upc": upc,
                "reason": f"Modality must be one of: {', '.join(sorted(VALID_MODALITIES))}",
                "error_code": "VALIDATION_ERROR",
            })
            continue

        valid.append({"upc": upc, "quantity": quantity, "modality": modality})

    return valid, failed


@mcp.tool()
def add_to_cart(user_id: str, items: list[dict]) -> dict:
    """Add items to the user's Kroger cart.

    Validates each item's UPC (13 chars), quantity (>= 1), and modality
    (PICKUP/DELIVERY), then sends valid items to the Kroger Cart API.

    Args:
        user_id: The user ID whose Kroger cart to add items to.
        items: List of dicts, each with 'upc' (str), 'quantity' (int),
               and 'modality' ('PICKUP' or 'DELIVERY').

    Returns:
        A dict with success status, items_added/items_failed counts,
        failed_items list, and checkout_url on success.
    """
    logger.info(
        "Tool invoked: add_to_cart | timestamp=%s | user_id=%s | item_count=%d",
        datetime.utcnow().isoformat(),
        user_id,
        len(items) if items else 0,
    )

    db = None
    try:
        # Validate items list is not empty
        if not items:
            return {
                "error_code": "VALIDATION_ERROR",
                "message": "Items list cannot be empty.",
            }

        # Validate individual items
        valid_items, failed_items = _validate_items(items)

        # If ALL items failed validation, return early
        if not valid_items:
            return {
                "success": False,
                "items_added": 0,
                "items_failed": len(failed_items),
                "failed_items": failed_items,
                "checkout_url": None,
            }

        # Get a valid OAuth token for the user
        db = get_db_session()
        oauth_handler = OAuthHandler(db)
        try:
            access_token = oauth_handler.get_valid_token(user_id)
        except KrogerAPIError:
            logger.warning("No valid OAuth token for user %s", user_id)
            return {
                "error_code": "AUTH_REQUIRED",
                "message": "No valid Kroger authentication. Please connect your Kroger account first.",
            }

        # Call Kroger Cart API
        kroger_cfg = get_kroger_config()
        base_url = kroger_cfg.get("api_base_url", "https://api.kroger.com")
        url = f"{base_url}{KROGER_CART_ENDPOINT}"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {"items": valid_items}

        resp = requests.put(url, json=payload, headers=headers, timeout=30)

        # Handle API response
        if resp.status_code == 204:
            # Success — all valid items added
            return {
                "success": True,
                "items_added": len(valid_items),
                "items_failed": len(failed_items),
                "failed_items": failed_items,
                "checkout_url": KROGER_CHECKOUT_URL,
            }

        if resp.status_code == 401:
            return {
                "error_code": "AUTH_EXPIRED",
                "message": "Kroger authentication expired. Please reconnect your Kroger account.",
            }

        if resp.status_code == 403:
            return {
                "error_code": "AUTH_REQUIRED",
                "message": "Missing required scope cart.basic:write. Please reconnect your Kroger account.",
            }

        if resp.status_code == 429:
            return {
                "error_code": "RATE_LIMIT_EXCEEDED",
                "message": "Kroger Cart API rate limit exceeded. Please try again later.",
            }

        # Any other error — all valid items failed
        error_body = ""
        try:
            error_body = resp.text
        except Exception:
            pass

        # Mark all valid items as failed since the API is all-or-nothing
        api_failed = [
            {
                "index": i,
                "upc": item["upc"],
                "reason": f"Kroger API error {resp.status_code}: {error_body}",
                "error_code": "KROGER_API_ERROR",
            }
            for i, item in enumerate(valid_items)
        ]
        all_failed = failed_items + api_failed

        return {
            "success": False,
            "items_added": 0,
            "items_failed": len(all_failed),
            "failed_items": all_failed,
            "checkout_url": None,
        }

    except requests.RequestException as exc:
        logger.error("Network error calling Kroger Cart API: %s", exc)
        return {
            "error_code": "KROGER_API_ERROR",
            "message": f"Network error calling Kroger Cart API: {exc}",
        }
    except Exception as exc:
        logger.error("Unexpected error in add_to_cart: %s", exc, exc_info=True)
        return {
            "error_code": "INTERNAL_ERROR",
            "message": f"An unexpected error occurred: {exc}",
        }
    finally:
        if db is not None:
            db.close()
