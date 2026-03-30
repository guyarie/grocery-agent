"""
Unit tests for the OAuthCallbackServer.

Tests server start/stop, valid callback handling, state validation,
port fallback, and timeout behavior.
"""

import threading
import time
import urllib.request
import urllib.error

import pytest

from src.oauth_callback import OAuthCallbackServer


@pytest.fixture()
def server():
    """Create and yield an OAuthCallbackServer, ensuring cleanup."""
    srv = OAuthCallbackServer(expected_state="test-state-123")
    yield srv
    # Best-effort cleanup
    try:
        srv.stop()
    except Exception:
        pass


class TestOAuthCallbackServer:
    """Tests for OAuthCallbackServer lifecycle and callback handling."""

    def test_start_and_stop(self, server: OAuthCallbackServer):
        """Server starts on a port and stops cleanly."""
        port = server.start()
        assert isinstance(port, int)
        assert 8400 <= port <= 8410
        server.stop()

    def test_valid_callback_stores_code(self, server: OAuthCallbackServer):
        """A valid GET /callback with correct state stores the auth code."""
        port = server.start()
        url = f"http://localhost:{port}/callback?code=AUTH_CODE_XYZ&state=test-state-123"
        resp = urllib.request.urlopen(url, timeout=5)
        assert resp.status == 200
        body = resp.read().decode()
        assert "Authentication successful" in body

        code = server.wait_for_code(timeout=2)
        assert code == "AUTH_CODE_XYZ"
        server.stop()

    def test_invalid_state_rejected(self, server: OAuthCallbackServer):
        """A callback with wrong state returns 400 and does NOT store a code."""
        port = server.start()
        url = f"http://localhost:{port}/callback?code=SOME_CODE&state=wrong-state"
        try:
            urllib.request.urlopen(url, timeout=5)
            pytest.fail("Expected HTTP error for invalid state")
        except urllib.error.HTTPError as exc:
            assert exc.code == 400

        assert server.auth_code is None
        assert not server.completion_event.is_set()
        server.stop()

    def test_missing_code_rejected(self, server: OAuthCallbackServer):
        """A callback with correct state but no code returns 400."""
        port = server.start()
        url = f"http://localhost:{port}/callback?state=test-state-123"
        try:
            urllib.request.urlopen(url, timeout=5)
            pytest.fail("Expected HTTP error for missing code")
        except urllib.error.HTTPError as exc:
            assert exc.code == 400

        assert server.auth_code is None
        server.stop()

    def test_404_for_unknown_path(self, server: OAuthCallbackServer):
        """Requests to paths other than /callback return 404."""
        port = server.start()
        url = f"http://localhost:{port}/other"
        try:
            urllib.request.urlopen(url, timeout=5)
            pytest.fail("Expected 404")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        server.stop()

    def test_wait_for_code_returns_none_on_timeout(self):
        """wait_for_code returns None when no callback arrives before timeout."""
        srv = OAuthCallbackServer(expected_state="s")
        srv.start()
        result = srv.wait_for_code(timeout=1)
        assert result is None
        # stop() is called inside wait_for_code on timeout

    def test_port_fallback_when_port_in_use(self):
        """If the requested port is occupied, the server falls back to the next."""
        import socket

        # Block port 8400 with a raw socket so the second server must fall back
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        blocker.bind(("localhost", 8400))
        blocker.listen(1)

        try:
            srv = OAuthCallbackServer(expected_state="s", port=8400)
            port = srv.start()
            assert port != 8400
            assert 8401 <= port <= 8410
            srv.stop()
        finally:
            blocker.close()

    def test_completion_event_set_on_valid_callback(self):
        """The completion event is set after a valid callback."""
        srv = OAuthCallbackServer(expected_state="evt-state")
        port = srv.start()
        url = f"http://localhost:{port}/callback?code=C&state=evt-state"
        urllib.request.urlopen(url, timeout=5)
        assert srv.completion_event.is_set()
        srv.stop()

    def test_port_property_before_start(self):
        """port property is None before start() is called."""
        srv = OAuthCallbackServer(expected_state="s")
        assert srv.port is None
