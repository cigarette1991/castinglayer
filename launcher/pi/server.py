#!/usr/bin/env python3
"""Castinglayer launcher for a Raspberry Pi plugged into the TV.

Serves the four-tile launcher page (Jellyfin, Casts, Settings, Inputs) to the
kiosk browser on the TV, and a small JSON API the page calls. The same page
opened on a phone (http://<pi>:8080) works as a remote for the TV.

Only the standard library is used, so this runs on a stock Raspberry Pi OS.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Sequence

STATIC_DIR = Path(__file__).resolve().parent / "static"
CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "castinglayer" / "launcher.json"
DEFAULT_CONFIG = {"jellyfin_url": "", "airplay_name": socket.gethostname(), "hdmi_ports": 4}

Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]


def run(cmd: Sequence[str]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(list(cmd), capture_output=True, text=True, timeout=10)


def load_config(path: Path = CONFIG_PATH) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        cfg.update(json.loads(path.read_text()))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg: dict, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2) + "\n")


def clean_config_update(data: dict) -> dict:
    """Validate a settings update from the page; raises ValueError on bad input."""
    out = {}
    if "jellyfin_url" in data:
        url = str(data["jellyfin_url"]).strip()
        if url and not re.match(r"^https?://[^\s]+$", url):
            raise ValueError("Jellyfin URL must start with http:// or https://")
        out["jellyfin_url"] = url.rstrip("/")
    if "airplay_name" in data:
        name = str(data["airplay_name"]).strip()
        if not 0 < len(name) <= 40:
            raise ValueError("AirPlay name must be 1-40 characters")
        out["airplay_name"] = name
    if "hdmi_ports" in data:
        ports = int(data["hdmi_ports"])
        if not 1 <= ports <= 8:
            raise ValueError("HDMI ports must be between 1 and 8")
        out["hdmi_ports"] = ports
    return out


def lan_ip() -> str | None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))  # no packet is sent; this just picks the outgoing interface
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


class Cec:
    """HDMI-CEC control through cec-ctl (v4l-utils), using the Pi's /dev/cec0."""

    def __init__(self, runner: Runner = run, device: str = "/dev/cec0"):
        self.runner = runner
        self.device = device

    @property
    def available(self) -> bool:
        return shutil.which("cec-ctl") is not None and os.path.exists(self.device)

    def _ctl(self, *args: str) -> "subprocess.CompletedProcess[str]":
        return self.runner(["cec-ctl", "-d", self.device, *args])

    def register(self) -> None:
        # Announce the Pi as a playback device so the TV accepts commands from it.
        self._ctl("--playback", "--osd-name", "Castinglayer")

    def physical_address(self) -> str:
        out = self._ctl().stdout
        m = re.search(r"Physical Address\s*:\s*([0-9a-f]\.[0-9a-f]\.[0-9a-f]\.[0-9a-f])", out, re.I)
        return m.group(1) if m else "1.0.0.0"

    def tv_on(self) -> None:
        self._ctl("--to", "0", "--image-view-on")

    def tv_off(self) -> None:
        self._ctl("--to", "0", "--standby")

    def show_pi(self) -> None:
        self.tv_on()
        self._ctl("--to", "15", "--active-source", f"phys-addr={self.physical_address()}")

    def show_hdmi(self, port: int) -> None:
        if not 1 <= port <= 15:
            raise ValueError("bad HDMI port")
        self.tv_on()
        self._ctl("--to", "15", "--set-stream-path", f"phys-addr={port:x}.0.0.0")


class App:
    def __init__(self, runner: Runner = run, config_path: Path = CONFIG_PATH):
        self.runner = runner
        self.config_path = config_path
        self.cec = Cec(runner)

    def config(self) -> dict:
        return load_config(self.config_path)

    def airplay_running(self) -> bool:
        return self.runner(["pgrep", "-x", "uxplay"]).returncode == 0

    def status(self) -> dict:
        cfg = self.config()
        return {
            "hostname": socket.gethostname(),
            "ip": lan_ip(),
            "airplay_name": cfg["airplay_name"],
            "airplay_running": self.airplay_running(),
            "jellyfin_url": cfg["jellyfin_url"],
            "hdmi_ports": cfg["hdmi_ports"],
            "cec": self.cec.available,
        }

    def action(self, path: str, body: dict) -> dict:
        """Dispatch POST /api/<path>. Returns a JSON-able dict; raises ValueError/KeyError on bad input."""
        if path == "tv/on":
            self.cec.tv_on()
        elif path == "tv/off":
            self.cec.tv_off()
        elif path == "tv/pi":
            self.cec.show_pi()
        elif m := re.fullmatch(r"tv/hdmi/(\d+)", path):
            self.cec.show_hdmi(int(m.group(1)))
        elif path == "airplay/restart":
            # The autostart wrapper (castinglayer-airplay) relaunches uxplay with the current name.
            self.runner(["pkill", "-x", "uxplay"])
        elif path == "config":
            cfg = self.config()
            cfg.update(clean_config_update(body))
            save_config(cfg, self.config_path)
            if "airplay_name" in body:
                self.runner(["pkill", "-x", "uxplay"])
            return {"ok": True, "config": cfg}
        elif path == "system/reboot":
            self.runner(["sudo", "-n", "systemctl", "reboot"])
        else:
            raise KeyError(path)
        return {"ok": True}


def make_handler(app: App):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

        def log_message(self, fmt, *args):  # quieter journal
            if not self.path.startswith("/api/status"):
                super().log_message(fmt, *args)

        def _json(self, code: int, payload: dict) -> None:
            data = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.split("?")[0] == "/api/status":
                return self._json(200, app.status())
            if self.path.startswith("/api/"):
                return self._json(404, {"error": "not found"})
            return super().do_GET()

        def do_POST(self):
            if not self.path.startswith("/api/"):
                return self._json(404, {"error": "not found"})
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}") if length else {}
                if not isinstance(body, dict):
                    raise ValueError("expected a JSON object")
                return self._json(200, app.action(self.path[len("/api/"):].split("?")[0], body))
            except KeyError:
                return self._json(404, {"error": "unknown action"})
            except (ValueError, TypeError) as e:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": str(e)})
            except (OSError, subprocess.SubprocessError) as e:
                return self._json(500, {"error": str(e)})

    return Handler


def main(argv: Sequence[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--host", default="0.0.0.0", help="bind address (default: all, so a phone can be the remote)")
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args(argv)

    app = App()
    if app.cec.available:
        try:
            app.cec.register()
        except (OSError, subprocess.SubprocessError):
            pass
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    print(f"Castinglayer launcher on http://{lan_ip() or args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
