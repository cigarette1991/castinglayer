"""Screen capture on macOS via ffmpeg's AVFoundation input, encoded to live HLS.

Google Cast's Default Media Receiver plays HLS (H.264 + AAC in MPEG-TS)
reliably, so we capture the display, encode it in real time and write a
rolling HLS playlist into a directory that the local HTTP server exposes.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

PLAYLIST_NAME = "stream.m3u8"

_DEVICE_LINE = re.compile(r"\[AVFoundation[^\]]*\]\s*\[(\d+)\]\s*(.+?)\s*$")
_SCREEN_NAME = re.compile(r"^Capture screen (\d+)$")


class CaptureError(RuntimeError):
    pass


@dataclass
class AVDevice:
    index: int
    name: str

    @property
    def screen_number(self) -> Optional[int]:
        m = _SCREEN_NAME.match(self.name)
        return int(m.group(1)) if m else None


@dataclass
class AVDevices:
    video: List[AVDevice] = field(default_factory=list)
    audio: List[AVDevice] = field(default_factory=list)

    @property
    def screens(self) -> List[AVDevice]:
        return [d for d in self.video if d.screen_number is not None]


def find_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise CaptureError("ffmpeg not found on PATH. Install it with: brew install ffmpeg")
    return path


def parse_device_list(output: str) -> AVDevices:
    """Parse the stderr of `ffmpeg -f avfoundation -list_devices true -i ""`."""
    devices = AVDevices()
    section: Optional[List[AVDevice]] = None
    for line in output.splitlines():
        if "AVFoundation video devices" in line:
            section = devices.video
            continue
        if "AVFoundation audio devices" in line:
            section = devices.audio
            continue
        m = _DEVICE_LINE.search(line)
        if m and section is not None:
            section.append(AVDevice(int(m.group(1)), m.group(2)))
    return devices


def list_devices(ffmpeg: Optional[str] = None) -> AVDevices:
    ffmpeg = ffmpeg or find_ffmpeg()
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        capture_output=True,
        text=True,
    )
    devices = parse_device_list(proc.stderr)
    if not devices.video and not devices.audio:
        raise CaptureError(
            "ffmpeg could not list AVFoundation devices (is this macOS, and was ffmpeg "
            "built with avfoundation?)\n" + proc.stderr.strip()
        )
    return devices


def available_encoders(ffmpeg: Optional[str] = None) -> str:
    ffmpeg = ffmpeg or find_ffmpeg()
    proc = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True)
    return proc.stdout


def pick_encoder(requested: str, ffmpeg: Optional[str] = None) -> str:
    if requested != "auto":
        return requested
    return "h264_videotoolbox" if "h264_videotoolbox" in available_encoders(ffmpeg) else "libx264"


def resolve_screen(devices: AVDevices, screen: Optional[str]) -> AVDevice:
    """Resolve a user-supplied screen selector to an AVFoundation video device.

    Accepts a screen number ("0" -> "Capture screen 0"), or a device name.
    Defaults to the first capture screen.
    """
    screens = devices.screens
    if not screens:
        raise CaptureError(
            "No capturable screens found. Grant Screen Recording permission to your "
            "terminal app (System Settings > Privacy & Security > Screen Recording) "
            "and restart it."
        )
    if screen is None:
        return screens[0]
    if screen.isdigit():
        for d in screens:
            if d.screen_number == int(screen):
                return d
        raise CaptureError(
            f"Screen {screen} not found. Available: "
            + ", ".join(str(d.screen_number) for d in screens)
        )
    for d in devices.video:
        if d.name.lower() == screen.lower():
            return d
    raise CaptureError(f"Video device {screen!r} not found. Run `castlayer displays`.")


def resolve_audio(devices: AVDevices, audio: Optional[str]) -> Optional[AVDevice]:
    if audio is None:
        return None
    for d in devices.audio:
        if (audio.isdigit() and d.index == int(audio)) or d.name.lower() == audio.lower():
            return d
    raise CaptureError(f"Audio device {audio!r} not found. Run `castlayer displays`.")


@dataclass
class CaptureSettings:
    video_index: int
    audio_index: Optional[int] = None  # None -> silent track (or none if include_audio False)
    include_audio: bool = True
    width: int = 1920
    height: int = 1080
    fps: int = 30
    bitrate: str = "6M"
    encoder: str = "h264_videotoolbox"
    segment_time: float = 1.0
    list_size: int = 6
    capture_cursor: bool = True


def build_command(ffmpeg: str, settings: CaptureSettings, out_dir: Path) -> List[str]:
    s = settings
    gop = max(1, int(round(s.fps * s.segment_time)))
    audio_in = str(s.audio_index) if s.audio_index is not None else "none"

    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "warning", "-nostdin",
        "-thread_queue_size", "512",
        "-f", "avfoundation",
        "-framerate", str(s.fps),
        "-capture_cursor", "1" if s.capture_cursor else "0",
        "-i", f"{s.video_index}:{audio_in}",
    ]
    if s.include_audio and s.audio_index is None:
        # Cast receivers are happiest with an audio track present; feed silence.
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]

    cmd += ["-map", "0:v:0"]
    if s.include_audio:
        cmd += ["-map", "0:a:0" if s.audio_index is not None else "1:a:0"]

    cmd += [
        "-vf",
        f"scale=w={s.width}:h={s.height}:force_original_aspect_ratio=decrease"
        f":force_divisible_by=2,fps={s.fps},format=yuv420p",
        "-c:v", s.encoder,
        "-b:v", s.bitrate, "-maxrate", s.bitrate, "-bufsize", _double(s.bitrate),
        "-g", str(gop), "-keyint_min", str(gop),
        "-force_key_frames", f"expr:gte(t,n_forced*{s.segment_time})",
        "-profile:v", "high",
    ]
    if s.encoder == "h264_videotoolbox":
        cmd += ["-realtime", "1", "-allow_sw", "1"]
    elif s.encoder == "libx264":
        cmd += ["-preset", "veryfast", "-tune", "zerolatency", "-level", "4.1", "-sc_threshold", "0"]

    if s.include_audio:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2"]

    cmd += [
        "-f", "hls",
        "-hls_time", str(s.segment_time),
        "-hls_list_size", str(s.list_size),
        "-hls_flags", "delete_segments+independent_segments+omit_endlist",
        "-hls_allow_cache", "0",
        "-hls_segment_type", "mpegts",
        "-hls_segment_filename", str(out_dir / "seg_%05d.ts"),
        str(out_dir / PLAYLIST_NAME),
    ]
    return cmd


def _double(rate: str) -> str:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([kKmM]?)", rate)
    if not m:
        return rate
    value = float(m.group(1)) * 2
    return f"{value:g}{m.group(2)}"


def playlist_segment_count(playlist: Path) -> int:
    try:
        return playlist.read_text().count("#EXTINF")
    except (FileNotFoundError, UnicodeDecodeError):
        return 0
