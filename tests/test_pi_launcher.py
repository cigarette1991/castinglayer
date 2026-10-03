import importlib.util
import json
import subprocess
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[1] / "launcher" / "pi" / "server.py"
spec = importlib.util.spec_from_file_location("pi_launcher", SERVER)
pi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pi)


class FakeRunner:
    def __init__(self, stdout="", returncode=0):
        self.calls = []
        self.stdout = stdout
        self.returncode = returncode

    def __call__(self, cmd):
        self.calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, self.returncode, self.stdout, "")


@pytest.fixture
def app(tmp_path):
    runner = FakeRunner(stdout="Physical Address           : 2.0.0.0\n")
    return pi.App(runner, tmp_path / "launcher.json"), runner


def test_hdmi_switch_uses_set_stream_path(app):
    a, runner = app
    a.action("tv/hdmi/3", {})
    assert ["cec-ctl", "-d", "/dev/cec0", "--to", "0", "--image-view-on"] in runner.calls
    assert runner.calls[-1][-3:] == ["15", "--set-stream-path", "phys-addr=3.0.0.0"]


def test_show_pi_uses_its_own_physical_address(app):
    a, runner = app
    a.action("tv/pi", {})
    assert runner.calls[-1][-1] == "phys-addr=2.0.0.0"


def test_tv_power(app):
    a, runner = app
    a.action("tv/off", {})
    assert runner.calls[-1][-1] == "--standby"


def test_unknown_action(app):
    a, _ = app
    with pytest.raises(KeyError):
        a.action("rm/-rf", {})


def test_config_roundtrip_and_airplay_restart(app):
    a, runner = app
    out = a.action("config", {"jellyfin_url": "http://10.0.0.5:8096/", "airplay_name": "Lounge"})
    assert out["config"]["jellyfin_url"] == "http://10.0.0.5:8096"
    assert a.config()["airplay_name"] == "Lounge"
    assert ["pkill", "-x", "uxplay"] in runner.calls


@pytest.mark.parametrize("bad", [
    {"jellyfin_url": "javascript:alert(1)"},
    {"airplay_name": ""},
    {"airplay_name": "x" * 41},
    {"hdmi_ports": 0},
    {"hdmi_ports": "lots"},
])
def test_config_validation(bad):
    with pytest.raises(ValueError):
        pi.clean_config_update(bad)


def test_http_api(app):
    a, _ = app
    server = ThreadingHTTPServer(("127.0.0.1", 0), pi.make_handler(a))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status = json.load(urllib.request.urlopen(base + "/api/status"))
        assert status["hdmi_ports"] == 4
        page = urllib.request.urlopen(base + "/").read().decode()
        assert "Jellyfin" in page and "Inputs" in page

        def post(path, body):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
            return urllib.request.urlopen(req)

        assert json.load(post("/api/tv/on", {}))["ok"]
        with pytest.raises(urllib.error.HTTPError) as e:
            post("/api/config", {"hdmi_ports": 99})
        assert e.value.code == 400
        with pytest.raises(urllib.error.HTTPError) as e:
            post("/api/nope", {})
        assert e.value.code == 404
    finally:
        server.shutdown()
