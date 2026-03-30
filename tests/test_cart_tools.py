"""
Unit tests for add_to_cart tool.

Tests validation, auth checks, Kroger API success/failure,
and structured error responses using mocked dependencies.
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from v0_src.database import Base
from v0_src.models import KrogerOAuthToken, User
from v0_src.exceptions import KrogerAPIError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session():
    """Create an in-memory SQLite DB with all tables, yield a session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def user(db_session):
    """Insert a test user and return it."""
    u = User(
        id="test-user-cart",
        username="cartuser",
        email="cart@example.com",
        password_hash="fakehash",
    )
    db_session.add(u)
    db_session.commit()
    return u


def _make_token(db_session, user_id, expires_at=None):
    """Helper to insert a valid KrogerOAuthToken."""
    if expires_at is None:
        expires_at = datetime.utcnow() + timedelta(hours=1)
    token = KrogerOAuthToken(
        id=str(uuid.uuid4()),
        user_id=user_id,
        access_token="valid-access-token",
        refresh_token="valid-refresh-token",
        token_type="Bearer",
        expires_at=expires_at,
        scope="product.compact cart.basic:write",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(token)
    db_session.commit()
    return token


def _valid_item(upc="0001111060903", quantity=1, modality="PICKUP"):
    return {"upc": upc, "quantity": quantity, "modality": modality}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAddToCartValidation:
    """Tests for input validation in add_to_cart."""

    @patch("src.tools.cart.get_db_session")
    def test_empty_items_returns_validation_error(self, mock_get_db):
        """Empty items list returns VALIDATION_ERROR."""
        mock_get_db.return_value = MagicMock()

        from src.tools.cart import add_to_cart

        result = add_to_cart("user-1", [])
        assert result["error_code"] == "VALIDATION_ERROR"
        assert "empty" in result["message"].lower()

    @patch("src.tools.cart.OAuthHandler")
    @patch("src.tools.cart.get_db_session")
    def test_upc_not_13_chars_rejected(self, mock_get_db, mock_oauth_cls, db_session, user):
        """UPC that is not exactly 13 characters is rejected with VALIDATION_ERROR."""
        mock_get_db.return_value = db_session
        _make_token(db_session, user.id)

        mock_handler = MagicMock()
        mock_handler.get_valid_token.return_value = "tok"
        mock_oauth_cls.return_value = mock_handler

        from src.tools.cart import add_to_cart

        # Too short
        result = add_to_cart(user.id, [_valid_item(upc="123")])
        assert result["success"] is False
        assert result["items_failed"] == 1
        assert result["failed_items"][0]["error_code"] == "VALIDATION_ERROR"
        assert "13" in result["failed_items"][0]["reason"]

    @patch("src.tools.cart.OAuthHandler")
    @patch("src.tools.cart.get_db_session")
    def test_invalid_modality_rejected(self, mock_get_db, mock_oauth_cls, db_session, user):
        """Invalid modality value is rejected."""
        mock_get_db.return_value = db_session
        _make_token(db_session, user.id)

        mock_handler = MagicMock()
        mock_handler.get_valid_token.return_value = "tok"
        mock_oauth_cls.return_value = mock_handler

        from src.tools.cart import add_to_cart

        result = add_to_cart(user.id, [_valid_item(modality="SHIP")])
        assert result["success"] is False
        assert result["items_failed"] == 1
        assert result["failed_items"][0]["error_code"] == "VALIDATION_ERROR"
        assert "Modality" in result["failed_items"][0]["reason"]


class TestAddToCartAuth:
    """Tests for authentication checks in add_to_cart."""

    @patch("src.tools.cart.OAuthHandler")
    @patch("src.tools.cart.get_db_session")
    def test_no_token_returns_auth_required(self, mock_get_db, mock_oauth_cls, db_session, user):
        """When user has no valid token, return AUTH_REQUIRED."""
        mock_get_db.return_value = db_session

        mock_handler = MagicMock()
        mock_handler.get_valid_token.side_effect = KrogerAPIError("No token")
        mock_oauth_cls.return_value = mock_handler

        from src.tools.cart import add_to_cart

        result = add_to_cart(user.id, [_valid_item()])
        assert result["error_code"] == "AUTH_REQUIRED"
        assert "message" in result


class TestAddToCartAPISuccess:
    """Tests for successful Kroger Cart API calls."""

    @patch("src.tools.cart.requests.put")
    @patch("src.tools.cart.OAuthHandler")
    @patch("src.tools.cart.get_db_session")
    def test_successful_cart_addition(self, mock_get_db, mock_oauth_cls, mock_put, db_session, user):
        """Successful 204 response returns success with items_added count."""
        mock_get_db.return_value = db_session
        _make_token(db_session, user.id)

        mock_handler = MagicMock()
        mock_handler.get_valid_token.return_value = "valid-token"
        mock_oauth_cls.return_value = mock_handler

        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_put.return_value = mock_resp

        from src.tools.cart import add_to_cart

        items = [
            _valid_item(),
            _valid_item(upc="0001111060904", quantity=2),
        ]
        result = add_to_cart(user.id, items)

        assert result["success"] is True
        assert result["items_added"] == 2
        assert result["items_failed"] == 0
        assert result["failed_items"] == []
        assert result["checkout_url"] == "https://www.kroger.com/cart"

        # Verify the API was called with correct payload
        call_kwargs = mock_put.call_args
        assert call_kwargs.kwargs["json"]["items"] == [
            {"upc": "0001111060903", "quantity": 1, "modality": "PICKUP"},
            {"upc": "0001111060904", "quantity": 2, "modality": "PICKUP"},
        ]


class TestAddToCartAPIErrors:
    """Tests for Kroger Cart API error handling."""

    @patch("src.tools.cart.requests.put")
    @patch("src.tools.cart.OAuthHandler")
    @patch("src.tools.cart.get_db_session")
    def test_api_error_returns_structured_error(self, mock_get_db, mock_oauth_cls, mock_put, db_session, user):
        """Non-204 API response returns structured failure with all items failed."""
        mock_get_db.return_value = db_session
        _make_token(db_session, user.id)

        mock_handler = MagicMock()
        mock_handler.get_valid_token.return_value = "valid-token"
        mock_oauth_cls.return_value = mock_handler

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request: Invalid UPC"
        mock_put.return_value = mock_resp

        from src.tools.cart import add_to_cart

        result = add_to_cart(user.id, [_valid_item()])
        assert result["success"] is False
        assert result["items_added"] == 0
        assert result["items_failed"] == 1
        assert result["failed_items"][0]["error_code"] == "KROGER_API_ERROR"

    @patch("src.tools.cart.requests.put")
    @patch("src.tools.cart.OAuthHandler")
    @patch("src.tools.cart.get_db_session")
    def test_401_returns_auth_expired(self, mock_get_db, mock_oauth_cls, mock_put, db_session, user):
        """401 from Kroger API returns AUTH_EXPIRED."""
        mock_get_db.return_value = db_session
        _make_token(db_session, user.id)

        mock_handler = MagicMock()
        mock_handler.get_valid_token.return_value = "expired-token"
        mock_oauth_cls.return_value = mock_handler

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_put.return_value = mock_resp

        from src.tools.cart import add_to_cart

        result = add_to_cart(user.id, [_valid_item()])
        assert result["error_code"] == "AUTH_EXPIRED"

    @patch("src.tools.cart.requests.put")
    @patch("src.tools.cart.OAuthHandler")
    @patch("src.tools.cart.get_db_session")
    def test_429_returns_rate_limit(self, mock_get_db, mock_oauth_cls, mock_put, db_session, user):
        """429 from Kroger API returns RATE_LIMIT_EXCEEDED."""
        mock_get_db.return_value = db_session
        _make_token(db_session, user.id)

        mock_handler = MagicMock()
        mock_handler.get_valid_token.return_value = "valid-token"
        mock_oauth_cls.return_value = mock_handler

        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_put.return_value = mock_resp

        from src.tools.cart import add_to_cart

        result = add_to_cart(user.id, [_valid_item()])
        assert result["error_code"] == "RATE_LIMIT_EXCEEDED"

    @patch("src.tools.cart.OAuthHandler")
    @patch("src.tools.cart.get_db_session")
    def test_network_error_returns_kroger_api_error(self, mock_get_db, mock_oauth_cls, db_session, user):
        """Network error during API call returns KROGER_API_ERROR."""
        mock_get_db.return_value = db_session
        _make_token(db_session, user.id)

        mock_handler = MagicMock()
        mock_handler.get_valid_token.return_value = "valid-token"
        mock_oauth_cls.return_value = mock_handler

        from src.tools.cart import add_to_cart

        with patch("src.tools.cart.requests.put", side_effect=Exception("Connection refused")):
            result = add_to_cart(user.id, [_valid_item()])

        assert result["error_code"] == "INTERNAL_ERROR"
        assert "message" in result
