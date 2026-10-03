"""Tiny HTTP server that exposes the live HLS directory to the Cast device."""

from __future__ import annotations

import socket
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _HLSHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".m3u8": "application/vnd.apple.mpegurl",
        ".ts": "video/mp2t",
    }

    def end_headers(self) -> None:
        # The Cast receiver fetches segments via XHR from its own origin, so CORS is required.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.end_headers()

    verbose = False
    server: "_Server"

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?")[0].endswith(".ts"):
            self.server.last_segment_at = time.monotonic()
        super().do_GET()

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        if self.verbose:
            super().log_message(format, *args)


class _Server(ThreadingHTTPServer):
    last_segment_at: float | None = None  # monotonic time the receiver last fetched a segment


class StreamServer:
    def __init__(self, directory: Path, port: int = 0, bind: str = "0.0.0.0", verbose: bool = False):
        handler = partial(type("_Handler", (_HLSHandler,), {"verbose": verbose}), directory=str(directory))
        self.httpd = _Server((bind, port), handler)
        self.httpd.daemon_threads = True
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return self.httpd.server_address[1]

    @property
    def last_segment_at(self) -> float | None:
        return self.httpd.last_segment_at

    def start(self) -> "StreamServer":
        self._thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def local_ip_for(target_host: str) -> str:
    """Return this machine's IP on the interface that routes to target_host."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((target_host, 8009))  # UDP connect sends nothing; it just picks a route
        return s.getsockname()[0]
