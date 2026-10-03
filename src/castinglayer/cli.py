"""castlayer: mirror your macOS display to a Google Cast device."""

from __future__ import annotations

import argparse
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional

from . import __version__
from .capture import (
    PLAYLIST_NAME,
    CaptureError,
    CaptureSettings,
    available_encoders,
    build_command,
    find_ffmpeg,
    list_devices,
    pick_encoder,
    playlist_segment_count,
    resolve_audio,
    resolve_screen,
)
from .server import StreamServer, local_ip_for

MEDIA_RECEIVER_APP_ID = "CC1AD845"
CONFIG_DIR = Path.home() / ".config" / "castinglayer"
LAST_DEVICE_FILE = CONFIG_DIR / "last_device"
SCREEN_RECORDING_SETTINGS = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"


def _err(msg: str) -> None:
    print(f"castlayer: {msg}", file=sys.stderr)


def _info(msg: str) -> None:
    print(msg, flush=True)


def parse_resolution(value: str):
    m = re.fullmatch(r"(\d+)[xX:](\d+)", value.strip())
    if not m:
        presets = {"1080p": (1920, 1080), "720p": (1280, 720), "480p": (854, 480), "4k": (3840, 2160)}
        if value.lower() in presets:
            return presets[value.lower()]
        raise argparse.ArgumentTypeError(f"invalid resolution {value!r} (use e.g. 1920x1080 or 720p)")
    return int(m.group(1)), int(m.group(2))


# ---------------------------------------------------------------- commands


def cmd_devices(args) -> int:
    from .cast import discover, stop_discovery

    _info(f"Searching for Google Cast devices ({args.timeout:g}s)...")
    casts, browser = discover(args.timeout, args.host)
    stop_discovery(browser)
    if not casts:
        _info("No devices found.")
        return 1
    width = max(len(c.cast_info.friendly_name) for c in casts)
    for c in casts:
        ci = c.cast_info
        _info(f"  {ci.friendly_name:<{width}}  {ci.model_name or '?':<22} {ci.host}:{ci.port}  ({ci.cast_type})")
    return 0


def cmd_displays(args) -> int:
    devices = list_devices()
    _info("Screens (use --screen N):")
    for d in devices.screens:
        _info(f"  {d.screen_number}: {d.name}  (avfoundation index {d.index})")
    if not devices.screens:
        _info("  none - grant Screen Recording permission to your terminal app")
    _info("Audio inputs (use --audio NAME|INDEX):")
    for d in devices.audio:
        _info(f"  {d.index}: {d.name}")
    return 0


def cmd_doctor(args) -> int:
    ok = True

    def check(label: str, passed: bool, hint: str = "") -> None:
        nonlocal ok
        ok &= passed
        _info(f"  [{'ok' if passed else '!!'}] {label}" + ("" if passed or not hint else f"\n       {hint}"))

    _info("castlayer doctor")
    check("running on macOS", platform.system() == "Darwin", "screen capture uses AVFoundation (macOS only)")
    ffmpeg = shutil.which("ffmpeg")
    check("ffmpeg installed", bool(ffmpeg), "brew install ffmpeg")
    if ffmpeg:
        has_vt = "h264_videotoolbox" in available_encoders(ffmpeg)
        _info("  [--] hardware H.264 encoder (h264_videotoolbox) "
              + ("found" if has_vt else "not found; will use libx264 (higher CPU use)"))
        try:
            devices = list_devices(ffmpeg)
            check(
                f"screens visible ({len(devices.screens)})",
                bool(devices.screens),
                "System Settings > Privacy & Security > Screen Recording: enable your terminal, then restart it",
            )
            has_loopback = any(re.search(r"blackhole|loopback|soundflower", d.name, re.I) for d in devices.audio)
            _info(
                "  [--] system-audio loopback device "
                + ("found" if has_loopback else "not found (optional: brew install blackhole-2ch for sound)")
            )
        except CaptureError as e:
            check("AVFoundation devices", False, str(e).splitlines()[0])
    try:
        import pychromecast  # noqa: F401

        check("pychromecast importable", True)
    except ImportError:
        check("pychromecast importable", False, "pip install pychromecast")
    return 0 if ok else 1


def cmd_stop(args) -> int:
    from .cast import CastError, choose, discover, stop_discovery

    casts, browser = discover(args.timeout, args.host)
    try:
        cast = choose(casts, args.device)
        cast.wait(timeout=15)
        cast.quit_app()
        _info(f"Stopped casting on {cast.cast_info.friendly_name}.")
        return 0
    except CastError as e:
        _err(str(e))
        return 1
    finally:
        stop_discovery(browser)


def _remembered_device() -> Optional[str]:
    try:
        return LAST_DEVICE_FILE.read_text().strip() or None
    except OSError:
        return None


def _remember_device(name: str) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        LAST_DEVICE_FILE.write_text(name + "\n")
    except OSError:
        pass


def _select_device(casts, name: Optional[str]):
    """Pick a device: explicit name > only device > last used > interactive menu."""
    from .cast import CastError, choose

    if not casts:
        raise CastError(
            "No TVs / Cast devices found. Check that:\n"
            "  - the TV is on and on the same Wi-Fi as this Mac (not a guest network)\n"
            "  - your terminal app is allowed in System Settings > Privacy & Security > Local Network\n"
            "  - or pass the TV's IP address directly: castlayer --host 192.168.1.50"
        )
    if name is not None or len(casts) == 1:
        return choose(casts, name)
    last = _remembered_device()
    for c in casts:
        if last and c.cast_info.friendly_name == last:
            return c
    if not sys.stdin.isatty():
        return choose(casts, None)  # raises with the list of names
    _info("Which TV?")
    for i, c in enumerate(casts, 1):
        _info(f"  {i}) {c.cast_info.friendly_name}  ({c.cast_info.model_name})")
    while True:
        answer = input(f"Enter 1-{len(casts)}: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(casts):
            return casts[int(answer) - 1]


def _screen_permission_help() -> None:
    _err(
        "macOS is blocking screen capture.\n"
        "  1. In the System Settings window that just opened, turn on your terminal app\n"
        "     (Terminal / iTerm) under Privacy & Security > Screen Recording.\n"
        "  2. Quit the terminal completely (Cmd+Q), reopen it, and run castlayer again."
    )
    if platform.system() == "Darwin":
        subprocess.run(["open", SCREEN_RECORDING_SETTINGS], check=False)


def cmd_cast(args) -> int:
    from .cast import CastError, discover, play_hls, stop_discovery

    ffmpeg = find_ffmpeg()
    devices = list_devices(ffmpeg)
    if not devices.screens:
        _screen_permission_help()
        return 1
    screen = resolve_screen(devices, args.screen)
    audio = resolve_audio(devices, args.audio)
    encoder = pick_encoder(args.encoder, ffmpeg)
    width, height = args.resolution

    _info(f"Searching for Google Cast devices ({args.timeout:g}s)...")
    casts, browser = discover(args.timeout, args.host)
    work_dir = Path(tempfile.mkdtemp(prefix="castlayer-"))
    log_path = work_dir / "ffmpeg.log"
    ffmpeg_proc: Optional[subprocess.Popen] = None
    server: Optional[StreamServer] = None
    cast = None
    started_playback = False

    # Turn SIGTERM into KeyboardInterrupt so cleanup always runs.
    signal.signal(signal.SIGTERM, _raise_interrupt)

    try:
        cast = _select_device(casts, args.device)
        name = cast.cast_info.friendly_name
        lan_ip = args.advertise_ip or local_ip_for(cast.cast_info.host)

        settings = CaptureSettings(
            video_index=screen.index,
            audio_index=audio.index if audio else None,
            include_audio=not args.no_audio,
            width=width,
            height=height,
            fps=args.fps,
            bitrate=args.bitrate,
            encoder=encoder,
            segment_time=args.segment_time,
            capture_cursor=not args.no_cursor,
        )
        cmd = build_command(ffmpeg, settings, work_dir)
        if args.verbose:
            _info("ffmpeg: " + " ".join(cmd))

        _info(f"Capturing {screen.name} -> {width}x{height}@{args.fps} {args.bitrate} ({encoder})"
              + (f", audio from {audio.name}" if audio else ""))
        log_file = open(log_path, "wb")
        ffmpeg_proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log_file, stderr=log_file)

        server = StreamServer(work_dir, port=args.port, verbose=args.verbose).start()
        url = f"http://{lan_ip}:{server.port}/{PLAYLIST_NAME}"
        if args.verbose:
            _info(f"Serving {url}")

        _wait_for_stream(ffmpeg_proc, work_dir / PLAYLIST_NAME, log_path, min_segments=3, timeout=30)

        _info(f"Casting to {name}...")
        play_hls(cast, url, title=f"{socket.gethostname()} - {screen.name}")
        started_playback = True
        _remember_device(name)
        _info(f"Live on {name}. Press Ctrl+C to stop.")

        return _monitor(cast, ffmpeg_proc, log_path)
    except KeyboardInterrupt:
        _info("\nStopping...")
        return 0
    except (CastError, CaptureError) as e:
        _err(str(e))
        return 1
    finally:
        if cast is not None and started_playback and not args.keep_receiver:
            try:
                if cast.app_id == MEDIA_RECEIVER_APP_ID:
                    cast.quit_app()
            except Exception:
                pass
        if ffmpeg_proc is not None and ffmpeg_proc.poll() is None:
            ffmpeg_proc.terminate()
            try:
                ffmpeg_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                ffmpeg_proc.kill()
        if server is not None:
            server.stop()
        stop_discovery(browser)
        shutil.rmtree(work_dir, ignore_errors=True)


def _raise_interrupt(*_):
    raise KeyboardInterrupt


def _log_tail(log_path: Path, lines: int = 15) -> str:
    try:
        return "\n".join(log_path.read_text(errors="replace").splitlines()[-lines:])
    except FileNotFoundError:
        return ""


def _wait_for_stream(proc, playlist: Path, log_path: Path, min_segments: int, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise CaptureError(f"ffmpeg exited with code {proc.returncode}:\n{_log_tail(log_path)}")
        if playlist_segment_count(playlist) >= min_segments:
            return
        time.sleep(0.2)
    raise CaptureError(f"Timed out waiting for the stream to start.\n{_log_tail(log_path)}")


def _monitor(cast, proc, log_path: Path) -> int:
    seen_playing = False
    while True:
        if proc.poll() is not None:
            _err(f"ffmpeg stopped unexpectedly (code {proc.returncode}):\n{_log_tail(log_path)}")
            return 1
        status = cast.media_controller.status
        state = status.player_state if status else None
        if state in ("PLAYING", "BUFFERING"):
            seen_playing = True
        if cast.app_id != MEDIA_RECEIVER_APP_ID and seen_playing:
            _info("Cast session ended on the receiver.")
            return 0
        if seen_playing and state == "IDLE":
            reason = getattr(status, "idle_reason", None)
            if reason == "ERROR":
                _err("The receiver reported a playback error.")
                return 1
            _info(f"Receiver went idle ({reason or 'stopped'}).")
            return 0
        time.sleep(0.5)


# ---------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="castlayer",
        description="Mirror your macOS display to a Google Cast device (Chromecast, Google TV, Nest Hub).",
        epilog="Run `castlayer` with no command to start casting your main screen.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    def discovery_opts(sp):
        sp.add_argument("--timeout", type=float, default=5.0, help="discovery time in seconds (default: 5)")
        sp.add_argument(
            "--host", action="append", metavar="IP",
            help="cast device IP to contact directly (repeatable; helps when mDNS is blocked)",
        )

    sp = sub.add_parser("devices", help="list Google Cast devices on the network")
    discovery_opts(sp)
    sp.set_defaults(func=cmd_devices)

    sp = sub.add_parser("displays", help="list capturable screens and audio inputs")
    sp.set_defaults(func=cmd_displays)

    sp = sub.add_parser("doctor", help="check that everything needed is installed and permitted")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("stop", help="stop whatever is casting on a device")
    sp.add_argument("-d", "--device", help="device name (case-insensitive, partial match ok)")
    discovery_opts(sp)
    sp.set_defaults(func=cmd_stop)

    sp = sub.add_parser("cast", help="mirror a screen to a Cast device")
    sp.add_argument("-d", "--device", help="device name (case-insensitive, partial match ok)")
    sp.add_argument("-s", "--screen", help="screen number from `castlayer displays` (default: main screen)")
    sp.add_argument("-a", "--audio", help="audio input name or index, e.g. 'BlackHole 2ch' for system sound")
    sp.add_argument("--no-audio", action="store_true", help="send no audio track at all")
    sp.add_argument("-r", "--resolution", type=parse_resolution, default=(1920, 1080),
                    help="max output size, e.g. 1920x1080, 720p (default: 1080p)")
    sp.add_argument("--fps", type=int, default=30, help="frames per second (default: 30)")
    sp.add_argument("-b", "--bitrate", default="6M", help="video bitrate (default: 6M)")
    sp.add_argument("--encoder", default="auto", help="auto | h264_videotoolbox | libx264 (default: auto)")
    sp.add_argument("--segment-time", type=float, default=2.0,
                    help="HLS segment length in seconds; lower = less latency but the TV may stall (default: 2)")
    sp.add_argument("--port", type=int, default=0, help="HTTP port to serve the stream on (default: random)")
    sp.add_argument("--advertise-ip", help="IP the Cast device should fetch the stream from (default: auto)")
    sp.add_argument("--no-cursor", action="store_true", help="hide the mouse cursor")
    sp.add_argument("--keep-receiver", action="store_true", help="don't close the receiver app on exit")
    sp.add_argument("-v", "--verbose", action="store_true")
    discovery_opts(sp)
    sp.set_defaults(func=cmd_cast)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {"devices", "displays", "doctor", "stop", "cast"}
    # Plain `castlayer` (optionally with cast options) just starts casting.
    if not argv or (argv[0] not in commands and argv[0] not in ("-h", "--help", "--version")):
        argv.insert(0, "cast")
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except CaptureError as e:
        _err(str(e))
        return 1
    except KeyboardInterrupt:
        return 130
