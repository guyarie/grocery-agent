"""
Store location tools.

Provides tools to search for nearby Kroger stores and set the user's
preferred store location for pricing and availability data.

Uses the Kroger Locations API with client credentials (not user-scoped)
for store search and validation.
"""

import base64
import json
import logging
from datetime import datetime
from pathlib import Path

import requests

from src.mcp_instance import mcp
from src.config import get_kroger_config

logger = logging.getLogger(__name__)

# Path for persisting user preferences (V1 simple file-based storage)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_PREFERENCES_FILE = _PROJECT_ROOT / "data" / "user_preferences.json"


def _get_client_credentials_token() -> str:
    """Obtain a client credentials token from the Kroger OAuth2 endpoint.

    This token is NOT user-scoped — it's used for public APIs like Locations.

    Returns:
        Access token string.

    Raises:
        requests.RequestException: On network errors.
        KeyError: If the token response is malformed.
    """
    kroger_cfg = get_kroger_config()
    client_id = kroger_cfg.get("client_id", "")
    client_secret = kroger_cfg.get("client_secret", "")
    token_url = kroger_cfg.get("token_url", "https://api.kroger.com/v1/connect/oauth2/token")

    auth_string = f"{client_id}:{client_secret}"
    auth_b64 = base64.b64encode(auth_string.encode()).decode()

    headers = {
        "Authorization": f"Basic {auth_b64}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {"grant_type": "client_credentials", "scope": "product.compact"}

    response = requests.post(token_url, headers=headers, data=data, timeout=30)
    response.raise_for_status()
    return response.json()["access_token"]


def _load_preferences() -> dict:
    """Load user preferences from the JSON file."""
    if _PREFERENCES_FILE.exists():
        try:
            return json.loads(_PREFERENCES_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_preferences(prefs: dict) -> None:
    """Save user preferences to the JSON file."""
    _PREFERENCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PREFERENCES_FILE.write_text(json.dumps(prefs, indent=2), encoding="utf-8")


def _format_store(location: dict) -> dict:
    """Extract relevant fields from a Kroger location API response object."""
    address = location.get("address", {})
    phone = location.get("phone", "")
    return {
        "location_id": location.get("locationId", ""),
        "name": location.get("name", ""),
        "address": {
            "street": address.get("addressLine1", ""),
            "city": address.get("city", ""),
            "state": address.get("state", ""),
            "zip": address.get("zipCode", ""),
        },
        "phone": phone,
    }


@mcp.tool()
def set_store_location(
    user_id: str,
    zip_code: str = None,
    location_id: str = None,
) -> dict:
    """Search for nearby Kroger stores or set a preferred store location.

    Provide a zip_code to search for nearby stores, or a location_id to set
    the user's preferred store for pricing and availability.

    Args:
        user_id: The user ID to associate the store preference with.
        zip_code: ZIP code to search for nearby Kroger stores.
        location_id: An 8-digit Kroger location ID to set as preferred store.

    Returns:
        A dict with a list of nearby stores (zip search) or a confirmation
        that the preferred store was set (location_id).
    """
    logger.info(
        "Tool invoked: set_store_location | timestamp=%s | user_id=%s | zip_code=%s | location_id=%s",
        datetime.utcnow().isoformat(),
        user_id,
        zip_code,
        location_id,
    )

    # --- Validate that at least one parameter is provided ---
    if not zip_code and not location_id:
        return {
            "error_code": "VALIDATION_ERROR",
            "message": "Either zip_code or location_id must be provided.",
        }

    try:
        token = _get_client_credentials_token()
    except requests.HTTPError as exc:
        logger.error("Failed to obtain client credentials token: %s", exc)
        return {
            "error_code": "AUTH_EXPIRED",
            "message": f"Failed to obtain Kroger API token: {exc}",
        }
    except Exception as exc:
        logger.error("Unexpected error obtaining token: %s", exc, exc_info=True)
        return {
            "error_code": "INTERNAL_ERROR",
            "message": f"Failed to obtain Kroger API token: {exc}",
        }

    api_headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    # --- Search by zip code ---
    if zip_code:
        return _search_by_zip(zip_code, api_headers)

    # --- Set by location ID ---
    return _set_by_location_id(user_id, location_id, api_headers)


def _search_by_zip(zip_code: str, headers: dict) -> dict:
    """Query the Kroger Locations API for stores near a zip code."""
    kroger_cfg = get_kroger_config()
    base_url = kroger_cfg.get("api_base_url", "https://api.kroger.com")
    url = f"{base_url}/v1/locations"

    params = {
        "filter.zipCode.near": zip_code,
        "filter.limit": 5,
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)

        if resp.status_code == 429:
            return {
                "error_code": "RATE_LIMIT_EXCEEDED",
                "message": "Kroger Locations API rate limit exceeded. Please try again later.",
            }

        resp.raise_for_status()
        data = resp.json()
        locations = data.get("data", [])

        if not locations:
            return {
                "stores": [],
                "message": f"No Kroger stores found near zip code {zip_code}. Try a different zip code or wider search area.",
            }

        stores = [_format_store(loc) for loc in locations]
        return {"stores": stores}

    except requests.HTTPError as exc:
        logger.error("Kroger Locations API error: %s", exc)
        return {
            "error_code": "KROGER_API_ERROR",
            "message": f"Kroger Locations API error: {exc}",
        }
    except requests.RequestException as exc:
        logger.error("Network error querying Kroger Locations API: %s", exc)
        return {
            "error_code": "KROGER_API_ERROR",
            "message": f"Network error querying Kroger Locations API: {exc}",
        }
    except Exception as exc:
        logger.error("Unexpected error in zip search: %s", exc, exc_info=True)
        return {
            "error_code": "INTERNAL_ERROR",
            "message": f"An unexpected error occurred: {exc}",
        }


def _set_by_location_id(user_id: str, location_id: str, headers: dict) -> dict:
    """Validate a location ID via the Kroger API and persist it."""
    kroger_cfg = get_kroger_config()
    base_url = kroger_cfg.get("api_base_url", "https://api.kroger.com")
    url = f"{base_url}/v1/locations/{location_id}"

    try:
        resp = requests.get(url, headers=headers, timeout=30)

        if resp.status_code == 404:
            return {
                "error_code": "LOCATION_NOT_FOUND",
                "message": f"Location ID '{location_id}' not found. Search by zip code to find valid stores.",
            }

        if resp.status_code == 429:
            return {
                "error_code": "RATE_LIMIT_EXCEEDED",
                "message": "Kroger Locations API rate limit exceeded. Please try again later.",
            }

        resp.raise_for_status()
        location_data = resp.json().get("data", {})

        # Persist the location preference
        prefs = _load_preferences()
        prefs[user_id] = {"location_id": location_id}
        _save_preferences(prefs)

        store = _format_store(location_data)
        return {
            "status": "location_set",
            "message": f"Preferred store set to {store['name']} ({location_id}).",
            "store": store,
        }

    except requests.HTTPError as exc:
        logger.error("Kroger Locations API error validating location: %s", exc)
        return {
            "error_code": "KROGER_API_ERROR",
            "message": f"Kroger Locations API error: {exc}",
        }
    except requests.RequestException as exc:
        logger.error("Network error validating location: %s", exc)
        return {
            "error_code": "KROGER_API_ERROR",
            "message": f"Network error validating location: {exc}",
        }
    except Exception as exc:
        logger.error("Unexpected error setting location: %s", exc, exc_info=True)
        return {
            "error_code": "INTERNAL_ERROR",
            "message": f"An unexpected error occurred: {exc}",
        }
