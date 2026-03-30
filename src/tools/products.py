"""
Product search and details tools.

Provides tools to search Kroger products and retrieve detailed product info.
Uses the Kroger Products API with client credentials (product.compact scope).
"""

import base64
import logging
from datetime import datetime

import requests

from src.mcp_instance import mcp
from src.config import get_kroger_config

logger = logging.getLogger(__name__)


def _get_client_credentials_token() -> str:
    """Obtain a client credentials token from the Kroger OAuth2 endpoint.

    Returns:
        Access token string.

    Raises:
        requests.HTTPError: On HTTP errors from the token endpoint.
        requests.RequestException: On network errors.
    """
    kroger_cfg = get_kroger_config()
    client_id = kroger_cfg.get("client_id", "")
    client_secret = kroger_cfg.get("client_secret", "")
    token_url = kroger_cfg.get("token_url", "https://api.kroger.com/v1/connect/oauth2/token")

    auth_b64 = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    resp = requests.post(
        token_url,
        headers={
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "client_credentials", "scope": "product.compact"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _format_product(product: dict) -> dict:
    """Extract clean product fields from a Kroger Products API response object."""
    items = product.get("items", [])
    first_item = items[0] if items else {}

    price_info = first_item.get("price", {})
    fulfillment = first_item.get("fulfillment", {})
    inventory = first_item.get("inventory", {})

    return {
        "product_id": product.get("productId", ""),
        "name": product.get("description", ""),
        "brand": product.get("brand", ""),
        "upc": first_item.get("upc", ""),
        "price": {
            "regular": price_info.get("regular", 0),
            "promo": price_info.get("promo", 0),
        },
        "size": first_item.get("size", ""),
        "in_stock": fulfillment.get("inStore", False),
        "stock_level": inventory.get("stockLevel", "UNKNOWN"),
    }


def _format_product_details(product: dict) -> dict:
    """Extract full product details from a Kroger Products API response object."""
    items = product.get("items", [])
    first_item = items[0] if items else {}

    price_info = first_item.get("price", {})
    fulfillment = first_item.get("fulfillment", {})
    inventory = first_item.get("inventory", {})

    # Collect all images across sizes
    images = []
    for img_group in product.get("images", []):
        for size_entry in img_group.get("sizes", []):
            images.append({
                "perspective": img_group.get("perspective", ""),
                "size": size_entry.get("size", ""),
                "url": size_entry.get("url", ""),
            })

    # Aisle locations
    aisles = []
    for aisle in product.get("aisleLocations", []):
        aisles.append({
            "description": aisle.get("description", ""),
            "number": aisle.get("number", ""),
        })

    return {
        "product_id": product.get("productId", ""),
        "name": product.get("description", ""),
        "brand": product.get("brand", ""),
        "upc": first_item.get("upc", ""),
        "price": {
            "regular": price_info.get("regular", 0),
            "promo": price_info.get("promo", 0),
        },
        "size": first_item.get("size", ""),
        "in_stock": fulfillment.get("inStore", False),
        "stock_level": inventory.get("stockLevel", "UNKNOWN"),
        "fulfillment": {
            "in_store": fulfillment.get("inStore", False),
            "ship_to_home": fulfillment.get("shiptohome", False),
            "delivery": fulfillment.get("delivery", False),
            "curbside": fulfillment.get("curbside", False),
        },
        "images": images,
        "aisle_locations": aisles,
    }


@mcp.tool()
def search_kroger_products(term: str, location_id: str, limit: int = 10) -> dict:
    """Search Kroger products by term with location-specific pricing.

    Queries the Kroger Products API for products matching the search term
    at the specified store location.

    Args:
        term: Search term (e.g. "milk", "bread", "organic eggs").
        location_id: 8-digit Kroger store location ID for pricing/availability.
        limit: Maximum number of products to return (default 10).

    Returns:
        A dict with a 'products' list, or a structured error.
    """
    logger.info(
        "Tool invoked: search_kroger_products | timestamp=%s | term=%s | location_id=%s | limit=%d",
        datetime.utcnow().isoformat(),
        term,
        location_id,
        limit,
    )

    # Obtain client credentials token
    try:
        token = _get_client_credentials_token()
    except requests.HTTPError as exc:
        logger.error("Failed to obtain client credentials token: %s", exc)
        return {"error_code": "AUTH_EXPIRED", "message": f"Failed to obtain Kroger API token: {exc}"}
    except Exception as exc:
        logger.error("Unexpected error obtaining token: %s", exc, exc_info=True)
        return {"error_code": "INTERNAL_ERROR", "message": f"Failed to obtain Kroger API token: {exc}"}

    # Call Kroger Products API
    kroger_cfg = get_kroger_config()
    base_url = kroger_cfg.get("api_base_url", "https://api.kroger.com")
    url = f"{base_url}/v1/products"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    params = {
        "filter.term": term,
        "filter.locationId": location_id,
        "filter.limit": limit,
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)

        if resp.status_code == 401:
            return {"error_code": "AUTH_EXPIRED", "message": "Kroger API token expired or invalid."}
        if resp.status_code == 429:
            return {
                "error_code": "RATE_LIMIT_EXCEEDED",
                "message": "Kroger Products API rate limit exceeded. Please try again later.",
            }

        resp.raise_for_status()
        data = resp.json()
        products_raw = data.get("data", [])

        if not products_raw:
            return {"products": [], "message": f"No products found for '{term}' at location {location_id}."}

        products = [_format_product(p) for p in products_raw]
        return {"products": products}

    except requests.HTTPError as exc:
        logger.error("Kroger Products API error: %s", exc)
        return {"error_code": "KROGER_API_ERROR", "message": f"Kroger Products API error: {exc}"}
    except requests.RequestException as exc:
        logger.error("Network error querying Kroger Products API: %s", exc)
        return {"error_code": "KROGER_API_ERROR", "message": f"Network error: {exc}"}
    except Exception as exc:
        logger.error("Unexpected error in product search: %s", exc, exc_info=True)
        return {"error_code": "INTERNAL_ERROR", "message": f"An unexpected error occurred: {exc}"}


@mcp.tool()
def get_product_details(product_id: str, location_id: str = None) -> dict:
    """Get detailed information for a specific Kroger product.

    Retrieves full product details including pricing, availability,
    images, and aisle location when a store location is provided.

    Args:
        product_id: The Kroger product ID (13-digit string).
        location_id: Optional 8-digit Kroger store location ID for pricing/availability.

    Returns:
        A dict with full product details, or a structured error.
    """
    logger.info(
        "Tool invoked: get_product_details | timestamp=%s | product_id=%s | location_id=%s",
        datetime.utcnow().isoformat(),
        product_id,
        location_id,
    )

    # Obtain client credentials token
    try:
        token = _get_client_credentials_token()
    except requests.HTTPError as exc:
        logger.error("Failed to obtain client credentials token: %s", exc)
        return {"error_code": "AUTH_EXPIRED", "message": f"Failed to obtain Kroger API token: {exc}"}
    except Exception as exc:
        logger.error("Unexpected error obtaining token: %s", exc, exc_info=True)
        return {"error_code": "INTERNAL_ERROR", "message": f"Failed to obtain Kroger API token: {exc}"}

    # Call Kroger Products API for specific product
    kroger_cfg = get_kroger_config()
    base_url = kroger_cfg.get("api_base_url", "https://api.kroger.com")
    url = f"{base_url}/v1/products/{product_id}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    params = {}
    if location_id:
        params["filter.locationId"] = location_id

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)

        if resp.status_code == 401:
            return {"error_code": "AUTH_EXPIRED", "message": "Kroger API token expired or invalid."}
        if resp.status_code == 404:
            return {
                "error_code": "PRODUCT_NOT_FOUND",
                "message": f"Product '{product_id}' not found in Kroger catalog.",
            }
        if resp.status_code == 429:
            return {
                "error_code": "RATE_LIMIT_EXCEEDED",
                "message": "Kroger Products API rate limit exceeded. Please try again later.",
            }

        resp.raise_for_status()
        data = resp.json()
        product_raw = data.get("data", {})

        if not product_raw:
            return {
                "error_code": "PRODUCT_NOT_FOUND",
                "message": f"Product '{product_id}' returned empty data.",
            }

        product = _format_product_details(product_raw)
        return {"product": product}

    except requests.HTTPError as exc:
        logger.error("Kroger Products API error: %s", exc)
        return {"error_code": "KROGER_API_ERROR", "message": f"Kroger Products API error: {exc}"}
    except requests.RequestException as exc:
        logger.error("Network error querying Kroger Products API: %s", exc)
        return {"error_code": "KROGER_API_ERROR", "message": f"Network error: {exc}"}
    except Exception as exc:
        logger.error("Unexpected error in product details: %s", exc, exc_info=True)
        return {"error_code": "INTERNAL_ERROR", "message": f"An unexpected error occurred: {exc}"}
