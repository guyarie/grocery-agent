"""
Temporary HTTP server for handling Kroger OAuth2 callback redirects.

Since the MCP server runs over stdio (no HTTP), this module provides a
minimal threaded HTTP server that listens on localhost to catch the
OAuth redirect, extract the authorization code, and signal completion.
"""

import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

# Ports to attempt when starting the callback server
_DEFAULT_PORT = 8400
_PORT_RANGE_END = 8411  # exclusive — tries 8400-8410


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP request handler that captures the OAuth callback parameters."""

    def do_GET(self) -> None:  # noqa: N802 — required by BaseHTTPRequestHandler
        parsed = urlparse(self.path)

        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        params = parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]

        server: "OAuthCallbackServer" = self.server  # type: ignore[assignment]

        # Validate state
        if state != server.expected_state:
            logger.warning(
                "OAuth callback state mismatch: expected=%s got=%s",
                server.expected_state,
                state,
            )
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authentication failed</h2>"
                b"<p>Invalid state parameter. Please try again.</p>"
                b"</body></html>"
            )
            return

        if not code:
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authentication failed</h2>"
                b"<p>No authorization code received.</p>"
                b"</body></html>"
            )
            return

        # Store the auth code and signal completion
        server.auth_code = code
        server.completion_event.set()

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body>"
            b"<h2>Authentication successful!</h2>"
            b"<p>You can close this tab.</p>"
            b"</body></html>"
        )

    # Silence default stderr logging from BaseHTTPRequestHandler
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        logger.debug("OAuth callback server: %s", format % args)


class OAuthCallbackServer(HTTPServer):
    """Temporary HTTP server that waits for a single OAuth callback.

    Usage::

        server = OAuthCallbackServer(expected_state="random-state-string")
        port = server.start()          # starts in a background thread
        # ... direct user to auth URL with redirect_uri=http://localhost:{port}/callback
        code = server.wait_for_code()  # blocks up to 5 min
        server.stop()
    """

    # Disable SO_REUSEADDR so port conflicts are detected reliably
    allow_reuse_address = False

    def __init__(self, expected_state: str, port: int = _DEFAULT_PORT) -> None:
        self.expected_state = expected_state
        self.auth_code: str | None = None
        self.completion_event = threading.Event()
        self._requested_port = port
        self._thread: threading.Thread | None = None
        self._actual_port: int | None = None
        # Defer HTTPServer.__init__ until start() so we can do port fallback
        # We intentionally do NOT call super().__init__ here.

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> int:
        """Start the callback server in a background daemon thread.

        Tries the requested port first, then falls back through 8400-8410.

        Returns:
            The actual port the server is listening on.

        Raises:
            OSError: If no port in the range is available.
        """
        port = self._requested_port
        last_error: OSError | None = None

        ports_to_try = [port] if port != _DEFAULT_PORT else []
        ports_to_try.extend(range(_DEFAULT_PORT, _PORT_RANGE_END))
        # Deduplicate while preserving order
        seen: set[int] = set()
        unique_ports: list[int] = []
        for p in ports_to_try:
            if p not in seen:
                seen.add(p)
                unique_ports.append(p)

        for candidate in unique_ports:
            try:
                HTTPServer.__init__(self, ("127.0.0.1", candidate), _CallbackHandler)
                self._actual_port = candidate
                logger.info("OAuth callback server bound to port %d", candidate)
                break
            except OSError as exc:
                last_error = exc
                logger.debug("Port %d in use, trying next", candidate)
        else:
            raise OSError(
                f"Could not bind OAuth callback server to any port in range "
                f"{unique_ports[0]}-{unique_ports[-1]}"
            ) from last_error

        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()
        return self._actual_port  # type: ignore[return-value]

    def wait_for_code(self, timeout: int = 300) -> str | None:
        """Block until the authorization code is received or *timeout* seconds elapse.

        Args:
            timeout: Maximum seconds to wait (default 300 = 5 minutes).

        Returns:
            The authorization code string, or ``None`` on timeout.
        """
        received = self.completion_event.wait(timeout=timeout)
        if not received:
            logger.warning("OAuth callback timed out after %d seconds", timeout)
            self.stop()
            return None
        return self.auth_code

    def stop(self) -> None:
        """Shut down the HTTP server and join the background thread."""
        self.shutdown()  # signals serve_forever() to exit
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("OAuth callback server stopped")

    @property
    def port(self) -> int | None:
        """The port the server is actually listening on (after ``start()``)."""
        return self._actual_port
