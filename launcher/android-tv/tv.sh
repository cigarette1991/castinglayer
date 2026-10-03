#!/usr/bin/env bash
# Drive an Android TV / Google TV over the network with adb: install the
# Castinglayer launcher, make it the home screen, and use the keyboard as a remote.
#
#   ./tv.sh pair 192.168.1.50:37123 123456   # Android 11+ "Wireless debugging" pairing
#   ./tv.sh connect [192.168.1.50]           # finds the TV itself if no IP; remembers it
#   ./tv.sh install [path/to.apk]            # default: the APK built in app/build
#   ./tv.sh set-home                         # make the launcher the Home screen
#   ./tv.sh restore-home                     # put the stock launcher back
#   ./tv.sh remote                           # arrow keys / Enter / Backspace / h / q
#   ./tv.sh key home|back|ok|up|down|left|right|power|volup|voldown|mute
#   ./tv.sh shot [file.png]                  # screenshot of what's on the TV
#   ./tv.sh jellyfin                         # install Jellyfin from its GitHub releases (no Play Store)
#   ./tv.sh degoogle [--all]                 # disable Google apps; --all also kills Cast + Play Store
#   ./tv.sh regoogle                         # undo degoogle
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/castinglayer"
TV_FILE="$CONF_DIR/tv_adb"
LAUNCHER="com.castinglayer.launcher"
HOME_ACTIVITY="$LAUNCHER/.HomeActivity"
# Stock home screens: Google TV, Android TV (newer), Android TV (older).
STOCK_LAUNCHERS=(com.google.android.apps.tv.launcherx com.google.android.tvlauncher com.google.android.leanbacklauncher)

# Google apps degoogle turns off. All are disabled per-user (pm disable-user), never
# uninstalled, so regoogle brings every one of them back.
GOOGLE_APPS=(
  com.google.android.youtube.tv com.google.android.youtube.tvmusic com.google.android.youtube.tvkids
  com.google.android.videos com.google.android.play.games
  com.google.android.katniss                      # Google Assistant / search
  com.google.android.apps.tv.dreamx com.google.android.backdrop   # ambient-mode screensavers
  com.google.android.tvrecommendations com.google.android.leanbacklauncher.recommendations
  com.google.android.feedback com.google.android.apps.tv.launcherx com.google.android.tvlauncher
)
# Only with --all. Without these there is no Google Cast (castlayer won't find the TV),
# no Play Store, and the Google TV phone-app remote stops working; use ./tv.sh remote instead.
# Google Play Services itself is left alone: disabling it can stop the TV from booting cleanly.
GOOGLE_APPS_ALL=(
  com.google.android.apps.mediashell              # Cast receiver
  com.android.vending                             # Play Store
  com.google.android.tv.remote.service            # Google TV phone-app remote
)

die() { echo "error: $*" >&2; exit 1; }

need_adb() {
  command -v adb >/dev/null && return
  if command -v brew >/dev/null; then
    echo "Installing adb (android-platform-tools)..."
    brew install --cask android-platform-tools
  else
    die "adb not found. Install Android platform-tools first."
  fi
}

target() {
  [[ -f "$TV_FILE" ]] || die "no TV yet. Run: $0 connect <tv-ip>"
  cat "$TV_FILE"
}

tvadb() { adb -s "$(target)" "$@"; }

keycode() {
  case "$1" in
    home) echo KEYCODE_HOME ;; back) echo KEYCODE_BACK ;;
    ok|enter|select) echo KEYCODE_DPAD_CENTER ;;
    up) echo KEYCODE_DPAD_UP ;; down) echo KEYCODE_DPAD_DOWN ;;
    left) echo KEYCODE_DPAD_LEFT ;; right) echo KEYCODE_DPAD_RIGHT ;;
    power) echo KEYCODE_POWER ;; wake) echo KEYCODE_WAKEUP ;; sleep) echo KEYCODE_SLEEP ;;
    volup) echo KEYCODE_VOLUME_UP ;; voldown) echo KEYCODE_VOLUME_DOWN ;; mute) echo KEYCODE_VOLUME_MUTE ;;
    play|pause) echo KEYCODE_MEDIA_PLAY_PAUSE ;; settings) echo KEYCODE_SETTINGS ;;
    input|inputs) echo KEYCODE_TV_INPUT ;;
    KEYCODE_*) echo "$1" ;;
    *) die "unknown key '$1'" ;;
  esac
}

cmd="${1:-help}"; shift || true
case "$cmd" in
  pair)
    need_adb
    [[ $# -eq 2 ]] || die "usage: $0 pair <ip:pairing-port> <pairing-code>"
    adb pair "$1" "$2"
    echo "Paired. Now run: $0 connect <ip>:<port shown under 'IP address & Port'>"
    ;;
  connect)
    need_adb
    addr="${1:-}"
    if [[ -z "$addr" && -f "$TV_FILE" ]]; then
      addr="$(cat "$TV_FILE")"
    fi
    if [[ -z "$addr" ]]; then
      # Wireless debugging (Android 11+) advertises itself over mDNS once paired.
      addr="$(adb mdns services 2>/dev/null | awk '/_adb-tls-connect/ {print $NF; exit}')"
    fi
    if [[ -z "$addr" ]]; then
      # Older TVs: look for adb's classic port 5555 on this Wi-Fi network.
      ip="$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}')"
      [[ -n "$ip" ]] || die "not on a network? Pass the TV's IP: $0 connect <tv-ip>"
      echo "Looking for the TV on ${ip%.*}.0/24..."
      found="$(mktemp)"
      for i in $(seq 1 254); do
        (nc -z -w 1 "${ip%.*}.$i" 5555 >/dev/null 2>&1 && echo "${ip%.*}.$i:5555" >> "$found") &
      done
      wait
      addr="$(head -1 "$found")"; rm -f "$found"
      [[ -n "$addr" ]] || die "no TV found. Check USB/Wireless debugging is on, then: $0 connect <tv-ip>"
    fi
    [[ "$addr" == *:* ]] || addr="$addr:5555"
    adb connect "$addr"
    adb -s "$addr" get-state >/dev/null 2>&1 || die "couldn't reach $addr. Accept the 'Allow debugging?' prompt on the TV and retry."
    mkdir -p "$CONF_DIR"; echo "$addr" > "$TV_FILE"
    echo "Connected to $(adb -s "$addr" shell getprop ro.product.model | tr -d '\r') at $addr"
    ;;
  install)
    need_adb
    apk="${1:-}"
    if [[ -z "$apk" ]]; then
      apk="$(ls "$HERE"/app/build/outputs/apk/release/*.apk 2>/dev/null | head -1 || true)"
      [[ -n "$apk" ]] || die "no APK found. Build it (./gradlew assembleRelease) or pass a path."
    fi
    tvadb install -r "$apk"
    echo "Installed. Run '$0 set-home' to make it the Home screen."
    ;;
  set-home)
    need_adb
    tvadb shell pm path "$LAUNCHER" >/dev/null 2>&1 || die "launcher not installed. Run: $0 install"
    # Works on most Android 10+ builds; harmless where it doesn't.
    tvadb shell cmd package set-home-activity "$HOME_ACTIVITY" >/dev/null 2>&1 || true
    # Google TV ignores the setting above, so disable the stock launcher too.
    for pkg in "${STOCK_LAUNCHERS[@]}"; do
      if tvadb shell pm path "$pkg" >/dev/null 2>&1; then
        tvadb shell pm disable-user --user 0 "$pkg" >/dev/null && echo "Disabled $pkg (undo: $0 restore-home)"
      fi
    done
    tvadb shell am start -a android.intent.action.MAIN -c android.intent.category.HOME >/dev/null
    echo "Done. Home now opens the Castinglayer launcher."
    ;;
  restore-home)
    need_adb
    for pkg in "${STOCK_LAUNCHERS[@]}"; do
      tvadb shell pm enable "$pkg" >/dev/null 2>&1 && echo "Enabled $pkg" || true
    done
    tvadb shell am start -a android.intent.action.MAIN -c android.intent.category.HOME >/dev/null
    ;;
  key)
    need_adb
    [[ $# -ge 1 ]] || die "usage: $0 key <name>"
    for k in "$@"; do tvadb shell input keyevent "$(keycode "$k")"; done
    ;;
  remote)
    need_adb
    dev="$(target)"
    echo "Remote for $dev: arrows move, Enter = OK, Backspace = Back, h = Home, i = Inputs,"
    echo "+/- = volume, m = mute, p = play/pause, s = settings, q = quit"
    while IFS= read -rsn1 c; do
      k=""
      case "$c" in
        $'\e') read -rsn2 -t 0.05 rest || true
               case "$rest" in '[A') k=up ;; '[B') k=down ;; '[C') k=right ;; '[D') k=left ;; esac ;;
        '') k=ok ;; $'\x7f'|$'\b') k=back ;;
        h) k=home ;; i) k=input ;; s) k=settings ;; p) k=play ;; m) k=mute ;;
        +|=) k=volup ;; -) k=voldown ;; q) break ;;
      esac
      [[ -n "$k" ]] && adb -s "$dev" shell input keyevent "$(keycode "$k")" &
    done
    wait
    ;;
  shot)
    need_adb
    out="${1:-tv-$(date +%Y%m%d-%H%M%S).png}"
    tvadb exec-out screencap -p > "$out"
    echo "Saved $out"
    ;;
  jellyfin)
    need_adb
    abi="$(tvadb shell getprop ro.product.cpu.abi | tr -d '\r')"
    echo "Finding the latest Jellyfin for Android TV release..."
    url="$(curl -fsSL https://api.github.com/repos/jellyfin/jellyfin-androidtv/releases/latest \
      | grep -o '"browser_download_url": *"[^"]*\.apk"' | sed 's/.*"\(http[^"]*\)"/\1/' \
      | grep -i -- "-release" | head -1)"
    [[ -n "$url" ]] || die "couldn't find an APK on the Jellyfin releases page (TV CPU: $abi)"
    tmp="$(mktemp -d)/jellyfin.apk"
    curl -fL -o "$tmp" "$url"
    tvadb install -r "$tmp"
    echo "Installed Jellyfin from $url"
    ;;
  degoogle)
    need_adb
    tvadb shell pm path "$LAUNCHER" >/dev/null 2>&1 \
      || die "install the launcher first ($0 install && $0 set-home); degoogle turns off the stock home screen"
    pkgs=("${GOOGLE_APPS[@]}")
    [[ "${1:-}" == "--all" ]] && pkgs+=("${GOOGLE_APPS_ALL[@]}")
    tvadb shell cmd package set-home-activity "$HOME_ACTIVITY" >/dev/null 2>&1 || true
    for pkg in "${pkgs[@]}"; do
      if tvadb shell pm path "$pkg" >/dev/null 2>&1; then
        tvadb shell pm disable-user --user 0 "$pkg" >/dev/null && echo "Disabled $pkg"
      fi
    done
    tvadb shell am start -a android.intent.action.MAIN -c android.intent.category.HOME >/dev/null
    echo "Done. Undo any time with: $0 regoogle"
    [[ "${1:-}" == "--all" ]] || echo "Google Cast is still on, so castlayer keeps working. '$0 degoogle --all' turns it off too."
    ;;
  regoogle)
    need_adb
    for pkg in "${GOOGLE_APPS[@]}" "${GOOGLE_APPS_ALL[@]}"; do
      tvadb shell pm enable "$pkg" >/dev/null 2>&1 && echo "Enabled $pkg" || true
    done
    ;;
  help|-h|--help)
    sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
    ;;
  *) die "unknown command '$cmd' (try: $0 help)" ;;
esac
