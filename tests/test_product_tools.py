"""
Unit tests for search_kroger_products and get_product_details tools.

Tests product search, product details, error handling, and edge cases
using mocked Kroger API responses.
"""

from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Sample Kroger Products API response data
# ---------------------------------------------------------------------------

SAMPLE_PRODUCTS_RESPONSE = {
    "data": [
        {
            "productId": "0001111060903",
            "description": "Kroger Vitamin D Whole Milk",
            "brand": "Kroger",
            "items": [
                {
                    "upc": "0001111060903",
                    "price": {"regular": 3.49, "promo": 2.99},
                    "size": "1 gal",
                    "fulfillment": {"inStore": True, "shiptohome": False, "delivery": True, "curbside": True},
                    "inventory": {"stockLevel": "HIGH"},
                }
            ],
        },
        {
            "productId": "0001111041700",
            "description": "Kroger 2% Reduced Fat Milk",
            "brand": "Kroger",
            "items": [
                {
                    "upc": "0001111041700",
                    "price": {"regular": 3.29, "promo": 0},
                    "size": "1 gal",
                    "fulfillment": {"inStore": True},
                    "inventory": {"stockLevel": "LOW"},
                }
            ],
        },
    ]
}

SAMPLE_PRODUCT_DETAIL_RESPONSE = {
    "data": {
        "productId": "0001111060903",
        "description": "Kroger Vitamin D Whole Milk",
        "brand": "Kroger",
        "images": [
            {
                "perspective": "front",
                "sizes": [
                    {"size": "large", "url": "https://example.com/milk_large.jpg"},
                    {"size": "thumbnail", "url": "https://example.com/milk_thumb.jpg"},
                ],
            }
        ],
        "aisleLocations": [{"description": "Dairy", "number": "3"}],
        "items": [
            {
                "upc": "0001111060903",
                "price": {"regular": 3.49, "promo": 2.99},
                "size": "1 gal",
                "fulfillment": {"inStore": True, "shiptohome": False, "delivery": True, "curbside": True},
                "inventory": {"stockLevel": "HIGH"},
            }
        ],
    }
}

SAMPLE_PRODUCT_NO_LOCATION = {
    "data": {
        "productId": "0001111060903",
        "description": "Kroger Vitamin D Whole Milk",
        "brand": "Kroger",
        "images": [],
        "aisleLocations": [],
        "items": [
            {
                "upc": "0001111060903",
                "size": "1 gal",
                "fulfillment": {},
            }
        ],
    }
}


# ---------------------------------------------------------------------------
# Helper to build a mock requests.Response
# ---------------------------------------------------------------------------

def _mock_response(status_code=200, json_data=None):
    """Create a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        from requests.exceptions import HTTPError
        resp.raise_for_status.side_effect = HTTPError(
            f"{status_code} Error", response=resp
        )
    return resp


# ---------------------------------------------------------------------------
# Tests: search_kroger_products
# ---------------------------------------------------------------------------

class TestSearchKrogerProducts:
    """Tests for the search_kroger_products tool."""

    @patch("src.tools.products._get_client_credentials_token", return_value="fake-token")
    @patch("src.tools.products.requests.get")
    def test_search_returns_formatted_products(self, mock_get, mock_token):
        """Search returns a list of formatted product dicts."""
        mock_get.return_value = _mock_response(200, SAMPLE_PRODUCTS_RESPONSE)

        from src.tools.products import search_kroger_products

        result = search_kroger_products(term="milk", location_id="70500826")

        assert "products" in result
        assert len(result["products"]) == 2

        product = result["products"][0]
        assert product["product_id"] == "0001111060903"
        assert product["name"] == "Kroger Vitamin D Whole Milk"
        assert product["brand"] == "Kroger"
        assert product["upc"] == "0001111060903"
        assert product["price"]["regular"] == 3.49
        assert product["price"]["promo"] == 2.99
        assert product["size"] == "1 gal"
        assert product["in_stock"] is True
        assert product["stock_level"] == "HIGH"

    @patch("src.tools.products._get_client_credentials_token", return_value="fake-token")
    @patch("src.tools.products.requests.get")
    def test_search_no_results_returns_empty_list(self, mock_get, mock_token):
        """Search with no results returns empty products list with message."""
        mock_get.return_value = _mock_response(200, {"data": []})

        from src.tools.products import search_kroger_products

        result = search_kroger_products(term="xyznonexistent", location_id="70500826")

        assert result["products"] == []
        assert "message" in result

    @patch("src.tools.products._get_client_credentials_token", return_value="fake-token")
    @patch("src.tools.products.requests.get")
    def test_search_rate_limit_returns_error(self, mock_get, mock_token):
        """A 429 response returns RATE_LIMIT_EXCEEDED error."""
        mock_get.return_value = _mock_response(429, {})

        from src.tools.products import search_kroger_products

        result = search_kroger_products(term="milk", location_id="70500826")

        assert result["error_code"] == "RATE_LIMIT_EXCEEDED"
        assert "message" in result

    @patch("src.tools.products._get_client_credentials_token", return_value="fake-token")
    @patch("src.tools.products.requests.get")
    def test_search_auth_expired_returns_error(self, mock_get, mock_token):
        """A 401 response returns AUTH_EXPIRED error."""
        mock_get.return_value = _mock_response(401, {})

        from src.tools.products import search_kroger_products

        result = search_kroger_products(term="milk", location_id="70500826")

        assert result["error_code"] == "AUTH_EXPIRED"

    @patch("src.tools.products._get_client_credentials_token")
    def test_search_token_failure_returns_error(self, mock_token):
        """When token acquisition fails, return AUTH_EXPIRED error."""
        from requests.exceptions import HTTPError
        mock_token.side_effect = HTTPError("401 Unauthorized")

        from src.tools.products import search_kroger_products

        result = search_kroger_products(term="milk", location_id="70500826")

        assert result["error_code"] == "AUTH_EXPIRED"
        assert "message" in result

    @patch("src.tools.products._get_client_credentials_token", return_value="fake-token")
    @patch("src.tools.products.requests.get")
    def test_search_passes_correct_params(self, mock_get, mock_token):
        """Verify the correct query params are sent to the Kroger API."""
        mock_get.return_value = _mock_response(200, {"data": []})

        from src.tools.products import search_kroger_products

        search_kroger_products(term="organic eggs", location_id="01400943", limit=5)

        call_kwargs = mock_get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["filter.term"] == "organic eggs"
        assert params["filter.locationId"] == "01400943"
        assert params["filter.limit"] == 5


# ---------------------------------------------------------------------------
# Tests: get_product_details
# ---------------------------------------------------------------------------

class TestGetProductDetails:
    """Tests for the get_product_details tool."""

    @patch("src.tools.products._get_client_credentials_token", return_value="fake-token")
    @patch("src.tools.products.requests.get")
    def test_details_returns_full_info(self, mock_get, mock_token):
        """Product details returns full formatted product info."""
        mock_get.return_value = _mock_response(200, SAMPLE_PRODUCT_DETAIL_RESPONSE)

        from src.tools.products import get_product_details

        result = get_product_details(product_id="0001111060903", location_id="70500826")

        assert "product" in result
        product = result["product"]
        assert product["product_id"] == "0001111060903"
        assert product["name"] == "Kroger Vitamin D Whole Milk"
        assert product["brand"] == "Kroger"
        assert product["upc"] == "0001111060903"
        assert product["price"]["regular"] == 3.49
        assert product["price"]["promo"] == 2.99
        assert product["size"] == "1 gal"
        assert product["in_stock"] is True
        assert product["stock_level"] == "HIGH"
        assert product["fulfillment"]["in_store"] is True
        assert product["fulfillment"]["delivery"] is True
        assert len(product["images"]) == 2
        assert product["images"][0]["perspective"] == "front"
        assert len(product["aisle_locations"]) == 1
        assert product["aisle_locations"][0]["description"] == "Dairy"

    @patch("src.tools.products._get_client_credentials_token", return_value="fake-token")
    @patch("src.tools.products.requests.get")
    def test_details_invalid_id_returns_not_found(self, mock_get, mock_token):
        """An invalid product ID returns PRODUCT_NOT_FOUND error."""
        mock_get.return_value = _mock_response(404, {})

        from src.tools.products import get_product_details

        result = get_product_details(product_id="0000000000000")

        assert result["error_code"] == "PRODUCT_NOT_FOUND"
        assert "message" in result

    @patch("src.tools.products._get_client_credentials_token", return_value="fake-token")
    @patch("src.tools.products.requests.get")
    def test_details_without_location_omits_pricing(self, mock_get, mock_token):
        """When no location_id is provided, pricing/availability data is absent."""
        mock_get.return_value = _mock_response(200, SAMPLE_PRODUCT_NO_LOCATION)

        from src.tools.products import get_product_details

        result = get_product_details(product_id="0001111060903")

        assert "product" in result
        product = result["product"]
        # Price fields default to 0 when not provided by API
        assert product["price"]["regular"] == 0
        assert product["price"]["promo"] == 0
        # Fulfillment defaults to False when not provided
        assert product["in_stock"] is False

        # Verify location_id was NOT sent as a query param
        call_kwargs = mock_get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert "filter.locationId" not in params

    @patch("src.tools.products._get_client_credentials_token", return_value="fake-token")
    @patch("src.tools.products.requests.get")
    def test_details_rate_limit_returns_error(self, mock_get, mock_token):
        """A 429 response returns RATE_LIMIT_EXCEEDED error."""
        mock_get.return_value = _mock_response(429, {})

        from src.tools.products import get_product_details

        result = get_product_details(product_id="0001111060903", location_id="70500826")

        assert result["error_code"] == "RATE_LIMIT_EXCEEDED"

    @patch("src.tools.products._get_client_credentials_token", return_value="fake-token")
    @patch("src.tools.products.requests.get")
    def test_details_auth_expired_returns_error(self, mock_get, mock_token):
        """A 401 response returns AUTH_EXPIRED error."""
        mock_get.return_value = _mock_response(401, {})

        from src.tools.products import get_product_details

        result = get_product_details(product_id="0001111060903", location_id="70500826")

        assert result["error_code"] == "AUTH_EXPIRED"

    @patch("src.tools.products._get_client_credentials_token", return_value="fake-token")
    @patch("src.tools.products.requests.get")
    def test_details_sends_location_id_when_provided(self, mock_get, mock_token):
        """When location_id is provided, it's included in the API request."""
        mock_get.return_value = _mock_response(200, SAMPLE_PRODUCT_DETAIL_RESPONSE)

        from src.tools.products import get_product_details

        get_product_details(product_id="0001111060903", location_id="70500826")

        call_kwargs = mock_get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["filter.locationId"] == "70500826"
