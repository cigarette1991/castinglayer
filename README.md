# castinglayer

`castlayer` is a small command-line tool that mirrors your macOS display to any Google Cast device: Chromecast, Google TV, Android TVs with Cast built in, and Nest Hubs.

```
$ castlayer cast -d "Living Room TV"
Searching for Google Cast devices (5s)...
Capturing Capture screen 0 -> 1920x1080@30 6M (h264_videotoolbox)
Casting to Living Room TV...
Live on Living Room TV. Press Ctrl+C to stop.
```

## How it works

```
 macOS screen ──AVFoundation──▶ ffmpeg (VideoToolbox H.264 + AAC) ──▶ live HLS playlist
                                                                           │
 Cast device ◀── "play http://<your-mac>:<port>/stream.m3u8" ── pychromecast │
     └──────────────────── fetches segments over HTTP ◀── built-in server ◀─┘
```

1. ffmpeg captures the display through AVFoundation and encodes it in real time. It uses the hardware `h264_videotoolbox` encoder and falls back to `libx264`.
2. A small HTTP server on your Mac serves the rolling HLS playlist. It sends CORS headers, which the receiver needs.
3. `pychromecast` finds devices over mDNS. It tells the Default Media Receiver on the chosen device to play the stream as `LIVE`.
4. Pressing Ctrl+C closes the receiver app, stops ffmpeg, and removes the temporary files.

## Install

```bash
brew install ffmpeg
pipx install git+https://github.com/cigarette1991/castinglayer.git
# or from a clone:  python3 -m pip install -e .
castlayer doctor
```

**Screen Recording permission:** the first time you run it, macOS asks whether your terminal app (Terminal, iTerm, …) may record the screen. You can also turn this on yourself in **System Settings → Privacy & Security → Screen Recording**. Restart the terminal afterwards. The macOS firewall may also ask whether Python can accept incoming connections. Allow it, because the Cast device pulls the video from your Mac.

## Usage

```bash
castlayer devices                 # list Cast devices on the network
castlayer displays                # list screens and audio inputs
castlayer cast                    # cast the main screen (if only one Cast device exists)
castlayer cast -d kitchen -s 1    # second display to "Kitchen Display" (partial names ok)
castlayer cast -r 720p --fps 24 -b 3M   # lighter stream for weak Wi-Fi
castlayer stop -d "Living Room"   # stop casting on a device
```

| option | meaning |
|---|---|
| `-d/--device` | device name (case-insensitive, partial match) |
| `-s/--screen` | screen number from `castlayer displays` |
| `-a/--audio` | audio input to send, e.g. `"BlackHole 2ch"` |
| `--no-audio` | no audio track at all (by default a silent track is sent, for receiver compatibility) |
| `-r/--resolution` | maximum output size; keeps the aspect ratio (`1920x1080`, `720p`, …) |
| `--fps`, `-b/--bitrate` | frame rate and video bitrate (defaults: 30, `6M`) |
| `--segment-time` | HLS segment length in seconds; lower means less delay |
| `--host IP` | contact a device by IP when mDNS discovery is blocked (repeatable) |
| `--advertise-ip` | the IP the Cast device should fetch from (auto-detected by default) |
| `--port` | HTTP port for the stream (random by default) |
| `--keep-receiver` | leave the receiver app open on exit |
| `-v` | print the ffmpeg command and stream URL |

### Sending your Mac's sound

macOS doesn't let apps capture system audio directly. Install a loopback driver:

```bash
brew install blackhole-2ch
```

Then route your output to it. To keep hearing sound locally, make a *Multi-Output Device* in Audio MIDI Setup that includes BlackHole and your speakers. Then run:

```bash
castlayer cast -a "BlackHole 2ch"
```

## Limitations

- **Delay:** Google Cast has no public API for live screen mirroring, so the video goes out as HLS. Expect about 3–6 seconds of delay. That is fine for presentations, videos and dashboards, but not for games. `--segment-time 0.5` lowers the delay a little.
- Older Chromecasts (generations 1–3) play up to 1080p at 30 fps. Ultra and Google TV models can take `--fps 60`.
- Speaker groups and audio-only devices can't show video.
- Your Mac and the Cast device must be able to reach each other on the LAN. Guest and client-isolated Wi-Fi networks block this.

## Development

```bash
python3 -m pip install -e '.[dev]'
python3 -m pytest
```
