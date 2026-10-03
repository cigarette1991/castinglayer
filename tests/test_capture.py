from pathlib import Path

import pytest

from castinglayer.capture import (
    CaptureError,
    CaptureSettings,
    build_command,
    parse_device_list,
    resolve_audio,
    resolve_screen,
)

LISTING = """\
[AVFoundation indev @ 0x7f8b1c004a00] AVFoundation video devices:
[AVFoundation indev @ 0x7f8b1c004a00] [0] FaceTime HD Camera
[AVFoundation indev @ 0x7f8b1c004a00] [1] Capture screen 0
[AVFoundation indev @ 0x7f8b1c004a00] [2] Capture screen 1
[AVFoundation indev @ 0x7f8b1c004a00] AVFoundation audio devices:
[AVFoundation indev @ 0x7f8b1c004a00] [0] BlackHole 2ch
[AVFoundation indev @ 0x7f8b1c004a00] [1] MacBook Pro Microphone
: Input/output error
"""


def test_parse_device_list():
    d = parse_device_list(LISTING)
    assert [(x.index, x.name) for x in d.video] == [
        (0, "FaceTime HD Camera"), (1, "Capture screen 0"), (2, "Capture screen 1"),
    ]
    assert [x.name for x in d.audio] == ["BlackHole 2ch", "MacBook Pro Microphone"]
    assert [s.screen_number for s in d.screens] == [0, 1]


def test_resolve_screen():
    d = parse_device_list(LISTING)
    assert resolve_screen(d, None).index == 1
    assert resolve_screen(d, "1").index == 2
    assert resolve_screen(d, "capture screen 1").index == 2
    with pytest.raises(CaptureError):
        resolve_screen(d, "5")


def test_resolve_screen_without_permission():
    d = parse_device_list(LISTING.replace("Capture screen", "Webcam"))
    with pytest.raises(CaptureError, match="Screen Recording"):
        resolve_screen(d, None)


def test_resolve_audio():
    d = parse_device_list(LISTING)
    assert resolve_audio(d, None) is None
    assert resolve_audio(d, "blackhole 2ch").index == 0
    assert resolve_audio(d, "1").name == "MacBook Pro Microphone"
    with pytest.raises(CaptureError):
        resolve_audio(d, "nope")


def test_build_command_silent_audio(tmp_path: Path):
    cmd = build_command("ffmpeg", CaptureSettings(video_index=1), tmp_path)
    assert cmd[cmd.index("-i") + 1] == "1:none"
    assert "anullsrc=channel_layout=stereo:sample_rate=48000" in cmd
    assert "1:a:0" in cmd
    assert cmd[-1] == str(tmp_path / "stream.m3u8")
    assert cmd[cmd.index("-bufsize") + 1] == "12M"


def test_build_command_device_audio(tmp_path: Path):
    cmd = build_command("ffmpeg", CaptureSettings(video_index=2, audio_index=0), tmp_path)
    assert cmd[cmd.index("-i") + 1] == "2:0"
    assert "anullsrc" not in " ".join(cmd)
    assert "0:a:0" in cmd


def test_build_command_no_audio(tmp_path: Path):
    cmd = build_command("ffmpeg", CaptureSettings(video_index=1, include_audio=False), tmp_path)
    assert "-c:a" not in cmd and "anullsrc" not in " ".join(cmd)
