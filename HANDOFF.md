# Handoff: the TV project, for a Claude session running on the Mac

You're the local Claude session on the user's Mac. A cloud session wrote everything below, but it couldn't reach the user's home network, so **none of it has run against the real TV or Mac yet.** Your job is the first real run.

## About the user (read this first)

- The user is **chronically ill** and works from the **sofa**, driving this session from their phone. Do everything you can yourself. Ask them to get up only when there's no other way, and then batch every at-the-Mac step into one trip.
- They have **no physical TV remote.** Before adb connects, they use the Google TV phone app as a remote. After that, `tv.sh` is the remote.
- Keep messages short and practical. When something works, say so plainly.
- **Goals, in order:**
  1. Control the TV over Wi-Fi, with nothing plugged in.
  2. Cast the Mac's screen to the TV, so they can screen-share for a friend.
  3. A custom launcher with four tiles: Jellyfin, Casts, Settings, Inputs.
  4. De-Google the TV.

## Get the code

```bash
git clone -b claude/lucid-knuth-is5pr7 https://github.com/cigarette1991/castinglayer.git ~/castinglayer
# or, in an existing clone:
git fetch origin claude/lucid-knuth-is5pr7 && git checkout claude/lucid-knuth-is5pr7 && git pull
```

Commit and push fixes to `claude/lucid-knuth-is5pr7`. Never commit IPs, device names or pairing codes. Run `caffeinate -dis &` so the Mac stays awake.

## What's in the repo

| path | what it is |
|---|---|
| `src/castinglayer/` | `castlayer` CLI. Mirrors the Mac screen to a Google Cast device: ffmpeg (AVFoundation capture, VideoToolbox H.264) → live HLS → built-in HTTP server → pychromecast tells the TV's Default Media Receiver to play it. Expect 3–6 s of delay. |
| `install.sh` | Installs Homebrew (if needed), ffmpeg, Python and a venv, and links `castlayer` into PATH. |
| `launcher/android-tv/` | Android TV launcher app (Kotlin, no AndroidX), home screen with the 4 tiles. |
| `launcher/android-tv/tv.sh` | Drives the TV over Wi-Fi with adb: `connect`, `pair`, `install`, `set-home`, `restore-home`, `remote`, `key`, `shot`, `jellyfin`, `degoogle`, `regoogle`. |
| `launcher/pi/` | Alternative with no Google at all: Raspberry Pi kiosk (Firefox), UxPlay AirPlay receiver, HDMI-CEC input switching. Only if the user buys a Pi. |
| `.github/workflows/launcher-apk.yml` | Builds the launcher APK. **It has built successfully** (artifact `castinglayer-launcher`). |
| `tests/` | 23 tests, all passing: `python3 -m pip install -e '.[dev]' && python3 -m pytest` |

## Step 1: connect to the TV over Wi-Fi

```bash
cd ~/castinglayer/launcher/android-tv
./tv.sh connect       # installs adb via Homebrew if missing; finds the TV via mDNS, then scans the /24 for port 5555
./tv.sh shot          # screenshot of the TV, so you can see the screen yourself
```

If no TV is found, developer mode is off. Walk the user through it using the **Google TV phone app** as the remote:
1. TV Settings → System → About → click **Android TV OS build** 7 times.
2. Settings → System → Developer options → **USB debugging** on. This is what enables network adb. Also turn on **Wireless debugging** if it's listed.
3. If the TV shows *Pair device with pairing code*: `./tv.sh pair <ip>:<pair-port> <code>`, then `./tv.sh connect <ip>:<port>`.
4. When the TV asks **"Allow debugging?"**, they tick **Always allow**.

From then on, use `./tv.sh key home|back|ok|up|down|left|right|volup|voldown|power|input|settings` and `./tv.sh shot` to see and drive the TV. Don't ask the user what the screen shows; take a screenshot.

## Step 2: casting (the user cares most about this)

```bash
cd ~/castinglayer && ./install.sh
castlayer doctor
castlayer devices     # the TV must be listed
castlayer -v          # casts the main screen; prints the ffmpeg command and stream URL
```

These macOS prompts each need one click **at the Mac**, so ask for them all in one trip:
- **Screen Recording** for the terminal app. After allowing it, the terminal must be quit (Cmd+Q) and reopened.
- **Local Network** access.
- **Allow incoming connections** for Python.

Use `./tv.sh shot` to check whether the TV is actually playing the stream.

If it isn't playing:
- **TV not found:** Local Network permission is missing, the Mac and TV are on different networks, or mDNS is blocked. Try `--host <tv-ip>`.
- **TV shows the cast screen, then goes idle:**
  1. Check the TV can reach the stream URL. Fetch it from another device, and check the macOS firewall.
  2. In `src/castinglayer/cast.py` `play_hls()`, the receiver hints `hlsSegmentFormat: ts` / `hlsVideoSegmentFormat: mpeg2_ts` are untested; removing them is a valid experiment.
  3. Also try `-r 720p -b 3M` and `--encoder libx264`.
- **ffmpeg exits immediately / "No capturable screens":** if AVFoundation capture is blocked on this macOS version, implement ScreenCaptureKit capture.
- Fix root causes in code and add tests.
- **Zero-code fallback while you debug:** Chrome → ⋮ → Cast… → Sources → Cast screen.

Once it works, try `--segment-time 0.5` to cut delay, and write the best settings into README.md.

## Step 3: launcher

1. **Get the APK**, either way:
   - From the latest green run of **Android TV launcher APK**: `gh run download --repo cigarette1991/castinglayer -n castinglayer-launcher`, or download it from the Actions page.
   - Or build it locally: install the Android SDK (`brew install --cask android-commandlinetools`), then run `./gradlew assembleRelease` in `launcher/android-tv`.
2. Install it:
   ```bash
   ./tv.sh install path/to/app-release.apk
   ./tv.sh set-home      # Home button opens the launcher (disables the stock launcher; undo: restore-home)
   ./tv.sh jellyfin      # installs Jellyfin from its GitHub releases, not the Play Store
   ```
3. Check every tile with `key` and `shot`:
   - **Jellyfin** opens the app.
   - **Casts** shows the cast name and IP.
   - **Settings** opens system settings.
   - **Inputs** lists the HDMI inputs and switches between them.

   Fix bugs in `launcher/android-tv/app/`. Nothing in the app has run on a device yet.

## Step 4: de-Google

```bash
./tv.sh degoogle        # disables YouTube, Assistant, Play Movies/Games, ambient mode, recommendations, stock launcher
./tv.sh regoogle        # undoes it
```

**Keep Google Cast on**, because `castlayer` needs it. Plain `degoogle` does. Only run `degoogle --all`, which also turns off Cast, the Play Store and the phone-app remote, if the user explicitly asks. Everything is disabled, not uninstalled, so it's all reversible. Google Play Services is never touched.

## When done

When casting works end to end, notify the user with the PushNotification tool if you have it, otherwise in a clear message. Include the exact command, e.g. *"Casting works — run: castlayer"*. Then report on the launcher and the de-Google step.
