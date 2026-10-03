"""Google Cast discovery and control (thin wrapper over pychromecast)."""

from __future__ import annotations

from typing import List, Optional, Sequence

import pychromecast
from pychromecast.discovery import stop_discovery

HLS_CONTENT_TYPE = "application/x-mpegURL"


class CastError(RuntimeError):
    pass


def discover(timeout: float = 5.0, known_hosts: Optional[Sequence[str]] = None):
    """Return (chromecasts, browser). Call stop_discovery(browser) when done."""
    casts, browser = pychromecast.get_chromecasts(
        timeout=timeout, known_hosts=list(known_hosts) if known_hosts else None
    )
    casts = sorted(casts, key=lambda c: c.cast_info.friendly_name.lower())
    return casts, browser


def choose(casts: List["pychromecast.Chromecast"], name: Optional[str]):
    if not casts:
        raise CastError(
            "No Google Cast devices found. Make sure the device is on the same network, "
            "or pass its IP with --host."
        )
    if name is None:
        if len(casts) == 1:
            return casts[0]
        raise CastError(
            "Multiple devices found; pick one with --device:\n"
            + "\n".join(f"  {c.cast_info.friendly_name}" for c in casts)
        )
    lowered = name.lower()
    exact = [c for c in casts if c.cast_info.friendly_name.lower() == lowered]
    if exact:
        return exact[0]
    partial = [c for c in casts if lowered in c.cast_info.friendly_name.lower()]
    if len(partial) == 1:
        return partial[0]
    if partial:
        raise CastError(
            f"{name!r} is ambiguous: " + ", ".join(c.cast_info.friendly_name for c in partial)
        )
    raise CastError(
        f"No device named {name!r}. Found: " + ", ".join(c.cast_info.friendly_name for c in casts)
    )


def play_hls(cast, url: str, title: str, timeout: float = 30.0) -> None:
    cast.wait(timeout=timeout)
    mc = cast.media_controller
    mc.play_media(
        url,
        HLS_CONTENT_TYPE,
        title=title,
        stream_type="LIVE",
        media_info={"hlsSegmentFormat": "ts", "hlsVideoSegmentFormat": "mpeg2_ts"},
    )
    mc.block_until_active(timeout=timeout)


__all__ = ["CastError", "choose", "discover", "play_hls", "stop_discovery"]
