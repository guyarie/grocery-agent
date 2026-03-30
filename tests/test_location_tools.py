"""
Unit tests for set_store_location tool.

Tests zip code search, location ID persistence, validation errors,
and structured error handling using mocked Kroger API responses.
"""

import json
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Sample Kroger API response data
# ---------------------------------------------------------------------------

SAMPLE_LOCATIONS_RESPONSE = {
    "data": [
        {
            "locationId": "70500826",
            "name": "Kroger Marketplace",
            "address": {
                "addressLine1": "123 Main St",
                "city": "Cincinnati",
                "state": "OH",
                "zipCode": "45202",
            },
            "phone": "513-555-0100",
        },
        {
            "locationId": "70500999",
            "name": "Kroger Fresh Fare",
            "address": {
                "addressLine1": "456 Oak Ave",
                "city": "Cincinnati",
                "state": "OH",
                "zipCode": "45203",
            },
            "phone": "513-555-0200",
        },
    ]
}

SAMPLE_LOCATION_DETAIL = {
    "data": {
        "locationId": "70500826",
        "name": "Kroger Marketplace",
        "address": {
            "addressLine1": "123 Main St",
            "city": "Cincinnati",
            "state": "OH",
            "zipCode": "45202",
        },
        "phone": "513-555-0100",
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
# Tests
# ---------------------------------------------------------------------------

class TestSearchByZipCode:
    """Tests for set_store_location with zip_code parameter."""

    @patch("src.tools.location._get_client_credentials_token", return_value="fake-token")
    @patch("src.tools.location.requests.get")
    def test_search_returns_stores(self, mock_get, mock_token):
        """Searching by zip code returns formatted store list."""
        mock_get.return_value = _mock_response(200, SAMPLE_LOCATIONS_RESPONSE)

        from src.tools.location import set_store_location

        result = set_store_location(user_id="user1", zip_code="45202")

        assert "stores" in result
        assert len(result["stores"]) == 2
        store = result["stores"][0]
        assert store["location_id"] == "70500826"
        assert store["name"] == "Kroger Marketplace"
        assert store["address"]["city"] == "Cincinnati"
        assert store["phone"] == "513-555-0100"

    @patch("src.tools.location._get_client_credentials_token", return_value="fake-token")
    @patch("src.tools.location.requests.get")
    def test_search_no_results_returns_empty_list(self, mock_get, mock_token):
        """Searching a zip with no nearby stores returns empty list with message."""
        mock_get.return_value = _mock_response(200, {"data": []})

        from src.tools.location import set_store_location

        result = set_store_location(user_id="user1", zip_code="00000")

        assert result["stores"] == []
        assert "message" in result
        assert "00000" in result["message"]


class TestSetByLocationId:
    """Tests for set_store_location with location_id parameter."""

    @patch("src.tools.location._save_preferences")
    @patch("src.tools.location._load_preferences", return_value={})
    @patch("src.tools.location._get_client_credentials_token", return_value="fake-token")
    @patch("src.tools.location.requests.get")
    def test_set_location_persists(self, mock_get, mock_token, mock_load, mock_save):
        """Setting a valid location ID persists it and returns confirmation."""
        mock_get.return_value = _mock_response(200, SAMPLE_LOCATION_DETAIL)

        from src.tools.location import set_store_location

        result = set_store_location(user_id="user1", location_id="70500826")

        assert result["status"] == "location_set"
        assert "store" in result
        assert result["store"]["location_id"] == "70500826"

        # Verify preferences were saved
        mock_save.assert_called_once()
        saved_prefs = mock_save.call_args[0][0]
        assert saved_prefs["user1"]["location_id"] == "70500826"

    @patch("src.tools.location._get_client_credentials_token", return_value="fake-token")
    @patch("src.tools.location.requests.get")
    def test_invalid_location_returns_error(self, mock_get, mock_token):
        """An invalid location ID returns LOCATION_NOT_FOUND error."""
        mock_get.return_value = _mock_response(404, {})

        from src.tools.location import set_store_location

        result = set_store_location(user_id="user1", location_id="99999999")

        assert result["error_code"] == "LOCATION_NOT_FOUND"
        assert "message" in result


class TestValidationErrors:
    """Tests for input validation."""

    def test_missing_both_params_returns_error(self):
        """Calling with neither zip_code nor location_id returns VALIDATION_ERROR."""
        from src.tools.location import set_store_location

        result = set_store_location(user_id="user1")

        assert result["error_code"] == "VALIDATION_ERROR"
        assert "message" in result


class TestApiErrors:
    """Tests for Kroger API error handling."""

    @patch("src.tools.location._get_client_credentials_token", return_value="fake-token")
    @patch("src.tools.location.requests.get")
    def test_rate_limit_returns_error(self, mock_get, mock_token):
        """A 429 response returns RATE_LIMIT_EXCEEDED."""
        mock_get.return_value = _mock_response(429, {})

        from src.tools.location import set_store_location

        result = set_store_location(user_id="user1", zip_code="45202")

        assert result["error_code"] == "RATE_LIMIT_EXCEEDED"
