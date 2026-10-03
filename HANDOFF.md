# Handoff: get castlayer casting to the TV

**Goal:** mirror the user's Mac screen to their TV over Google Cast. They have no TV remote, so casting is the only way to use the TV. They want to drive it from the couch, over SSH or a local Claude session, without sitting at the TV.

**Branch:** `claude/macos-display-cast-cli-dbi2ir`. Everything is committed and pushed.

## Status

- The code is written and the unit tests pass (`python3 -m pytest`, 12 tests).
- The ffmpeg → HLS pipeline was checked on Linux with a synthetic test source in place of the screen. Output was H.264 High plus AAC, in 1-second segments.
- **Not yet tested on a real Mac or a real Cast device.** The previous session ran in a cloud container that could not reach the user's network. The first real run is the next step.

## What it is

`castlayer` is a Python CLI:

1. ffmpeg captures the screen through AVFoundation and encodes it with `h264_videotoolbox`, falling back to `libx264`.
2. It writes a live HLS stream to a temp directory.
3. A built-in HTTP server serves that stream with CORS headers.
4. pychromecast tells the TV's Default Media Receiver to play it as `LIVE`.

Expect about 3–6 seconds of delay.

| file | role |
|---|---|
| `src/castinglayer/cli.py` | Commands: `cast` (default when no command is given), `devices`, `displays`, `doctor`, `stop`. Also the TV picker and remembered device (`~/.config/castinglayer/last_device`), and the cleanup on Ctrl+C. |
| `src/castinglayer/capture.py` | Parses the AVFoundation device list and builds the ffmpeg command |
| `src/castinglayer/server.py` | HLS HTTP server; `local_ip_for()` finds the LAN IP the TV should fetch from |
| `src/castinglayer/cast.py` | Discovery, device matching, `play_hls()` |
| `install.sh` | Installs Homebrew (if needed), ffmpeg and Python, creates a venv in `~/.castinglayer`, and links `castlayer` into `$(brew --prefix)/bin` |

## Next steps on the Mac

1. Make sure the TV is on and on the same Wi-Fi as the Mac (not a guest network).
2. `./install.sh`
3. `castlayer doctor`
4. `castlayer devices`. The TV should be listed. If it isn't, see the troubleshooting table.
5. `castlayer -v`. This casts the main screen and prints the ffmpeg command and stream URL.
6. The user must click **Allow** for Screen Recording, Local Network, and incoming connections for Python. After granting Screen Recording, quit the terminal (Cmd+Q) and reopen it.

### Running over SSH (so the user can sit on the couch)

- Turn on **System Settings → General → Sharing → Remote Login**.
- Add `/usr/libexec/sshd-keygen-wrapper` under **Privacy & Security → Screen Recording**. Without this, capture over SSH finds no screens.
- The Mac must stay logged in and unlocked.

## Troubleshooting

| symptom | likely cause / fix |
|---|---|
| "No capturable screens" | Screen Recording permission is missing. The tool opens the settings pane itself. Restart the terminal after granting it. |
| No TV found | Local Network permission for the terminal or Python is off, the Mac and TV are on different networks, or mDNS is blocked. Try `--host <TV IP>`. |
| TV shows the cast screen, then goes idle or errors | Check that the TV can reach the stream URL from `-v`; the macOS firewall may be blocking Python. Fix with `--advertise-ip`, a fixed `--port`, or a firewall rule. Then try `-r 720p -b 3M`, or `--encoder libx264`. |
| ffmpeg exits immediately | Read the log tail it prints. On recent macOS versions the AVFoundation screen input may be restricted. If so, the fallback is a ScreenCaptureKit-based capture, which isn't implemented yet. |

**Fallback that needs no code:** in Chrome, choose **⋮ → Cast… → Sources → Cast screen**, then pick the TV.

## Open risks and ideas

- The receiver hints `hlsSegmentFormat: ts` and `hlsVideoSegmentFormat: mpeg2_ts` are set in `cast.play_hls()`. These are untested on real hardware.
- A silent AAC track is sent by default for receiver compatibility. `--no-audio` drops it.
- Possible later work:
  - lower delay (shorter segments, or fMP4 / low-latency HLS)
  - ScreenCaptureKit capture
  - a menu-bar wrapper
