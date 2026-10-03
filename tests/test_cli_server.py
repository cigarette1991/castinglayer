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


def test_monitor_reloads_only_when_receiver_is_stuck(tmp_path):
    from types import SimpleNamespace
    from castinglayer import cli

    (tmp_path / "seg_00001.ts").write_bytes(b"x")
    playlist = tmp_path / "stream.m3u8"
    server = StreamServer(tmp_path, port=0, bind="127.0.0.1").start()
    try:
        assert server.last_segment_at is None
        urllib.request.urlopen(f"http://127.0.0.1:{server.port}/seg_00001.ts").read()
        assert server.last_segment == "seg_00001.ts"

        def run(segments):
            playlist.write_text("".join(f"#EXTINF:2.0,\nseg_{n:05d}.ts\n" for n in segments))
            mc = SimpleNamespace(status=SimpleNamespace(player_state="PLAYING", idle_reason=None),
                                 update_status=lambda: None)
            reloads, polls = [], []

            def reload():
                reloads.append(1)
                # Reloading ends the old session; that must not be mistaken for the user stopping.
                mc.status = SimpleNamespace(player_state="IDLE", idle_reason="INTERRUPTED")

            def poll():
                polls.append(1)
                return 1 if len(polls) > 4 else None

            cast = SimpleNamespace(app_id=cli.MEDIA_RECEIVER_APP_ID, media_controller=mc)
            result = cli._monitor(cast, SimpleNamespace(poll=poll, returncode=1), tmp_path / "log",
                                  server=server, reload=reload, playlist=playlist, stall_after=0.1)
            return reloads, result

        # Mac is slow: no new segments beyond the fetched one, so reloading would only hurt.
        assert run([1]) == ([], 1)
        # Receiver is stuck: segments are waiting but not fetched.
        server.httpd.last_segment_at = 0
        reloads, result = run([1, 2, 3, 4, 5])
        assert reloads and result == 1  # kept casting after the reload
    finally:
        server.stop()


def test_monitor_reloads_after_playback_error(tmp_path):
    from types import SimpleNamespace
    from castinglayer import cli

    mc = SimpleNamespace(status=SimpleNamespace(player_state="PLAYING", idle_reason=None),
                         update_status=lambda: None)
    reloads, polls = [], []

    def poll():
        polls.append(1)
        if len(polls) == 2:  # receiver hits an error (e.g. a 404 after falling behind)
            mc.status = SimpleNamespace(player_state="IDLE", idle_reason="ERROR")
        return 1 if len(polls) > 4 else None

    def reload():
        reloads.append(1)
        mc.status = SimpleNamespace(player_state="PLAYING", idle_reason=None)

    server = SimpleNamespace(last_segment_at=None, httpd=SimpleNamespace())
    cast = SimpleNamespace(app_id=cli.MEDIA_RECEIVER_APP_ID, media_controller=mc)
    result = cli._monitor(cast, SimpleNamespace(poll=poll, returncode=1), tmp_path / "log",
                          server=server, reload=reload)
    assert reloads == [1] and result == 1  # kept casting until ffmpeg stopped
