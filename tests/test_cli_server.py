import urllib.request

import pytest

from castinglayer.cli import build_parser, parse_resolution
from castinglayer.server import StreamServer, local_ip_for


def test_parse_resolution():
    assert parse_resolution("1280x720") == (1280, 720)
    assert parse_resolution("720p") == (1280, 720)
    with pytest.raises(Exception):
        parse_resolution("big")


def test_parser_cast_defaults():
    args = build_parser().parse_args(["cast", "-d", "Living Room"])
    assert args.device == "Living Room"
    assert args.resolution == (1920, 1080)
    assert args.fps == 30


def test_server_serves_hls_with_cors(tmp_path):
    (tmp_path / "stream.m3u8").write_text("#EXTM3U\n")
    server = StreamServer(tmp_path, port=0, bind="127.0.0.1").start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/stream.m3u8") as r:
            assert r.headers["Access-Control-Allow-Origin"] == "*"
            assert r.headers["Content-Type"] == "application/vnd.apple.mpegurl"
            assert r.read() == b"#EXTM3U\n"
    finally:
        server.stop()


def test_local_ip_for_loopback():
    assert local_ip_for("127.0.0.1") == "127.0.0.1"



def test_no_command_means_cast(monkeypatch):
    import castinglayer.cli as cli

    calls = []
    monkeypatch.setattr(cli, "cmd_cast", lambda a: calls.append(a) or 0)
    assert cli.main([]) == 0
    assert cli.main(["-d", "TV"]) == 0
    assert [a.command for a in calls] == ["cast", "cast"]
    assert calls[1].device == "TV"


def test_monitor_reloads_stalled_receiver(tmp_path):
    from types import SimpleNamespace
    from castinglayer import cli

    (tmp_path / "seg_00001.ts").write_bytes(b"x")
    server = StreamServer(tmp_path, port=0, bind="127.0.0.1").start()
    try:
        assert server.last_segment_at is None
        urllib.request.urlopen(f"http://127.0.0.1:{server.port}/seg_00001.ts").read()
        assert server.last_segment_at is not None

        reloads = []
        proc = SimpleNamespace(poll=lambda: 1 if reloads else None, returncode=0)
        cast = SimpleNamespace(app_id=cli.MEDIA_RECEIVER_APP_ID,
                               media_controller=SimpleNamespace(status=None))
        cli._monitor(cast, proc, tmp_path / "log", server=server,
                     reload=lambda: reloads.append(1), stall_after=0.1)
        assert reloads == [1]
    finally:
        server.stop()
