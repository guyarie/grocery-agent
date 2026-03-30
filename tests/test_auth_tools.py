"""
Unit tests for get_kroger_auth_status tool.

Tests the three auth states (connected, expired, not_connected)
and structured error handling using an in-memory SQLite database.
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
        id="test-user-1",
        username="testuser",
        email="test@example.com",
        password_hash="fakehash",
    )
    db_session.add(u)
    db_session.commit()
    return u


def _make_token(db_session, user_id, expires_at, refresh_token="refresh-tok"):
    """Helper to insert a KrogerOAuthToken."""
    token = KrogerOAuthToken(
        id=str(uuid.uuid4()),
        user_id=user_id,
        access_token="access-tok",
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_at=expires_at,
        scope="product.compact cart.basic:write",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(token)
    db_session.commit()
    return token


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetKrogerAuthStatus:
    """Tests for the get_kroger_auth_status tool function."""

    @patch("src.tools.auth.get_db_session")
    def test_not_connected_when_no_token(self, mock_get_db, db_session, user):
        """When no token exists for the user, return not_connected."""
        mock_get_db.return_value = db_session

        from src.tools.auth import get_kroger_auth_status

        result = get_kroger_auth_status(user.id)
        assert result == {"status": "not_connected"}

    @patch("src.tools.auth.get_db_session")
    def test_connected_when_token_valid(self, mock_get_db, db_session, user):
        """When a non-expired token exists, return connected with expires_at."""
        mock_get_db.return_value = db_session
        future = datetime.utcnow() + timedelta(hours=1)
        _make_token(db_session, user.id, expires_at=future)

        from src.tools.auth import get_kroger_auth_status

        result = get_kroger_auth_status(user.id)
        assert result["status"] == "connected"
        assert "expires_at" in result

    @patch("src.tools.auth.OAuthHandler")
    @patch("src.tools.auth.get_db_session")
    def test_expired_when_refresh_fails(self, mock_get_db, mock_oauth_cls, db_session, user):
        """When token is expired and refresh fails, return expired."""
        mock_get_db.return_value = db_session
        past = datetime.utcnow() - timedelta(hours=1)
        _make_token(db_session, user.id, expires_at=past)

        # Make the OAuthHandler constructor return a mock whose refresh raises
        mock_handler = MagicMock()
        mock_handler.refresh_access_token.side_effect = KrogerAPIError("refresh failed")
        mock_oauth_cls.return_value = mock_handler

        from src.tools.auth import get_kroger_auth_status

        result = get_kroger_auth_status(user.id)
        assert result["status"] == "expired"
        assert "message" in result

    @patch("src.tools.auth.OAuthHandler")
    @patch("src.tools.auth.get_db_session")
    def test_connected_after_successful_refresh(self, mock_get_db, mock_oauth_cls, db_session, user):
        """When token is expired but refresh succeeds, return connected."""
        mock_get_db.return_value = db_session
        past = datetime.utcnow() - timedelta(hours=1)
        tok = _make_token(db_session, user.id, expires_at=past)

        new_expiry = datetime.utcnow() + timedelta(hours=1)

        def fake_refresh(refresh_token, uid):
            # Simulate what OAuthHandler does: update the token in DB
            tok.expires_at = new_expiry
            tok.updated_at = datetime.utcnow()
            db_session.commit()
            return tok

        mock_handler = MagicMock()
        mock_handler.refresh_access_token.side_effect = fake_refresh
        mock_oauth_cls.return_value = mock_handler

        from src.tools.auth import get_kroger_auth_status

        result = get_kroger_auth_status(user.id)
        assert result["status"] == "connected"
        assert "expires_at" in result

    @patch("src.tools.auth.get_db_session")
    def test_internal_error_returns_structured_error(self, mock_get_db):
        """When an unexpected exception occurs, return structured error."""
        mock_get_db.side_effect = RuntimeError("db exploded")

        from src.tools.auth import get_kroger_auth_status

        result = get_kroger_auth_status("any-user")
        assert result["error_code"] == "INTERNAL_ERROR"
        assert "message" in result

    @patch("src.tools.auth.get_db_session")
    def test_db_session_closed_on_success(self, mock_get_db, db_session, user):
        """DB session is closed after a successful call."""
        mock_session = MagicMock(wraps=db_session)
        mock_get_db.return_value = mock_session

        from src.tools.auth import get_kroger_auth_status

        get_kroger_auth_status(user.id)
        mock_session.close.assert_called_once()

    @patch("src.tools.auth.get_db_session")
    def test_db_session_closed_on_error(self, mock_get_db):
        """DB session is closed even when an error occurs."""
        mock_session = MagicMock()
        mock_session.query.side_effect = RuntimeError("boom")
        mock_get_db.return_value = mock_session

        from src.tools.auth import get_kroger_auth_status

        get_kroger_auth_status("any-user")
        mock_session.close.assert_called_once()


class TestConnectKroger:
    """Tests for the connect_kroger tool function."""

    @patch("src.tools.auth.OAuthHandler")
    @patch("src.tools.auth.OAuthCallbackServer")
    @patch("src.tools.auth.get_db_session")
    def test_successful_connection(self, mock_get_db, mock_server_cls, mock_oauth_cls, db_session, user):
        """Full happy path: server starts, code received, tokens exchanged."""
        mock_get_db.return_value = db_session

        # Mock the callback server
        mock_server = MagicMock()
        mock_server.start.return_value = 8400
        mock_server.wait_for_code.return_value = "AUTH_CODE_123"
        mock_server_cls.return_value = mock_server

        # Mock the OAuthHandler
        mock_handler = MagicMock()
        mock_handler.get_authorization_url.return_value = "https://api.kroger.com/v1/connect/oauth2/authorize?..."
        mock_oauth_cls.return_value = mock_handler

        from src.tools.auth import connect_kroger

        result = connect_kroger(user.id)
        assert result == {"status": "connected"}

        # Verify redirect_uri was overridden
        assert mock_handler.redirect_uri == "http://localhost:8400/callback"
        # Verify scopes were set
        assert mock_handler.scope == "product.compact cart.basic:write profile.compact"
        # Verify exchange was called with the code
        mock_handler.exchange_code_for_token.assert_called_once_with("AUTH_CODE_123", user.id)
        # Verify server was stopped in finally
        mock_server.stop.assert_called_once()

    @patch("src.tools.auth.OAuthHandler")
    @patch("src.tools.auth.OAuthCallbackServer")
    @patch("src.tools.auth.get_db_session")
    def test_timeout_returns_error(self, mock_get_db, mock_server_cls, mock_oauth_cls, db_session, user):
        """When no callback arrives within timeout, return AUTH_TIMEOUT error."""
        mock_get_db.return_value = db_session

        mock_server = MagicMock()
        mock_server.start.return_value = 8400
        mock_server.wait_for_code.return_value = None  # timeout
        mock_server_cls.return_value = mock_server

        mock_oauth_cls.return_value = MagicMock()

        from src.tools.auth import connect_kroger

        result = connect_kroger(user.id)
        assert result["error_code"] == "AUTH_TIMEOUT"
        assert "timed out" in result["message"].lower()

    @patch("src.tools.auth.OAuthHandler")
    @patch("src.tools.auth.OAuthCallbackServer")
    @patch("src.tools.auth.get_db_session")
    def test_port_conflict_returns_error(self, mock_get_db, mock_server_cls, mock_oauth_cls, db_session, user):
        """When the callback server can't bind to any port, return PORT_CONFLICT."""
        mock_get_db.return_value = db_session

        mock_server = MagicMock()
        mock_server.start.side_effect = OSError("All ports in use")
        mock_server_cls.return_value = mock_server

        mock_oauth_cls.return_value = MagicMock()

        from src.tools.auth import connect_kroger

        result = connect_kroger(user.id)
        assert result["error_code"] == "PORT_CONFLICT"

    @patch("src.tools.auth.OAuthHandler")
    @patch("src.tools.auth.OAuthCallbackServer")
    @patch("src.tools.auth.get_db_session")
    def test_kroger_api_error_returns_structured_error(self, mock_get_db, mock_server_cls, mock_oauth_cls, db_session, user):
        """When token exchange fails with KrogerAPIError, return structured error."""
        mock_get_db.return_value = db_session

        mock_server = MagicMock()
        mock_server.start.return_value = 8400
        mock_server.wait_for_code.return_value = "SOME_CODE"
        mock_server_cls.return_value = mock_server

        mock_handler = MagicMock()
        mock_handler.exchange_code_for_token.side_effect = KrogerAPIError("Token exchange failed: 400")
        mock_oauth_cls.return_value = mock_handler

        from src.tools.auth import connect_kroger

        result = connect_kroger(user.id)
        assert result["error_code"] == "KROGER_API_ERROR"
        assert "message" in result

    @patch("src.tools.auth.OAuthHandler")
    @patch("src.tools.auth.OAuthCallbackServer")
    @patch("src.tools.auth.get_db_session")
    def test_unexpected_error_returns_internal_error(self, mock_get_db, mock_server_cls, mock_oauth_cls, db_session, user):
        """When an unexpected exception occurs, return INTERNAL_ERROR."""
        mock_get_db.return_value = db_session

        mock_server = MagicMock()
        mock_server.start.return_value = 8400
        mock_server.wait_for_code.return_value = "CODE"
        mock_server_cls.return_value = mock_server

        mock_handler = MagicMock()
        mock_handler.exchange_code_for_token.side_effect = RuntimeError("something broke")
        mock_oauth_cls.return_value = mock_handler

        from src.tools.auth import connect_kroger

        result = connect_kroger(user.id)
        assert result["error_code"] == "INTERNAL_ERROR"
        assert "message" in result

    @patch("src.tools.auth.OAuthHandler")
    @patch("src.tools.auth.OAuthCallbackServer")
    @patch("src.tools.auth.get_db_session")
    def test_db_session_closed_after_success(self, mock_get_db, mock_server_cls, mock_oauth_cls):
        """DB session is closed after a successful connect_kroger call."""
        mock_session = MagicMock()
        mock_get_db.return_value = mock_session

        mock_server = MagicMock()
        mock_server.start.return_value = 8400
        mock_server.wait_for_code.return_value = "CODE"
        mock_server_cls.return_value = mock_server

        mock_oauth_cls.return_value = MagicMock()

        from src.tools.auth import connect_kroger

        connect_kroger("any-user")
        mock_session.close.assert_called_once()

    @patch("src.tools.auth.OAuthHandler")
    @patch("src.tools.auth.OAuthCallbackServer")
    @patch("src.tools.auth.get_db_session")
    def test_callback_server_stopped_on_error(self, mock_get_db, mock_server_cls, mock_oauth_cls):
        """Callback server is stopped even when an error occurs."""
        mock_get_db.return_value = MagicMock()

        mock_server = MagicMock()
        mock_server.start.return_value = 8400
        mock_server.wait_for_code.return_value = "CODE"
        mock_server_cls.return_value = mock_server

        mock_handler = MagicMock()
        mock_handler.exchange_code_for_token.side_effect = RuntimeError("boom")
        mock_oauth_cls.return_value = mock_handler

        from src.tools.auth import connect_kroger

        connect_kroger("any-user")
        mock_server.stop.assert_called_once()

    @patch("src.tools.auth.OAuthHandler")
    @patch("src.tools.auth.OAuthCallbackServer")
    @patch("src.tools.auth.get_db_session")
    def test_state_passed_to_callback_server(self, mock_get_db, mock_server_cls, mock_oauth_cls, db_session, user):
        """A random state string is generated and passed to the callback server."""
        mock_get_db.return_value = db_session

        mock_server = MagicMock()
        mock_server.start.return_value = 8400
        mock_server.wait_for_code.return_value = "CODE"
        mock_server_cls.return_value = mock_server

        mock_oauth_cls.return_value = MagicMock()

        from src.tools.auth import connect_kroger

        connect_kroger(user.id)

        # Verify OAuthCallbackServer was created with an expected_state
        call_kwargs = mock_server_cls.call_args
        assert "expected_state" in call_kwargs.kwargs or len(call_kwargs.args) > 0
        state_arg = call_kwargs.kwargs.get("expected_state") or call_kwargs.args[0]
        assert isinstance(state_arg, str)
        assert len(state_arg) == 32  # uuid4().hex is 32 chars
