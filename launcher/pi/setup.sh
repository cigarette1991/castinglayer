#!/usr/bin/env bash
# Turn a Raspberry Pi (Raspberry Pi OS Bookworm or newer, *with desktop*) into a
# TV box: boots straight into the Castinglayer launcher, receives AirPlay
# screen mirroring from Macs and iPhones, and controls the TV over HDMI-CEC.
#
# Run on the Pi as your normal user:   ./setup.sh
set -euo pipefail

[[ $EUID -ne 0 ]] || { echo "Run as your normal user, not root (sudo is used where needed)."; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST=/opt/castinglayer-launcher
ME="$(id -un)"

echo "==> Installing packages"
sudo apt-get update
sudo apt-get install -y uxplay gstreamer1.0-plugins-bad gstreamer1.0-libav avahi-daemon v4l-utils python3
# Firefox rather than Chromium: no Google services in the kiosk.
command -v firefox >/dev/null || command -v firefox-esr >/dev/null \
  || sudo apt-get install -y firefox || sudo apt-get install -y firefox-esr
FIREFOX="$(command -v firefox || command -v firefox-esr)"

echo "==> Installing the launcher to $DEST"
sudo mkdir -p "$DEST"
sudo cp -r "$HERE/server.py" "$HERE/static" "$DEST/"
sudo install -m 755 "$HERE/castinglayer-airplay" /usr/local/bin/castinglayer-airplay

# HDMI-CEC (/dev/cec0) is owned by the video group.
sudo usermod -aG video "$ME"

# Let the launcher's "Reboot the Pi" button work without a password, and nothing else.
echo "$ME ALL=(root) NOPASSWD: /usr/bin/systemctl reboot" | sudo tee /etc/sudoers.d/castinglayer-launcher >/dev/null
sudo chmod 440 /etc/sudoers.d/castinglayer-launcher

sed "s/@USER@/$ME/" "$HERE/systemd/castinglayer-launcher.service" \
  | sudo tee /etc/systemd/system/castinglayer-launcher.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now castinglayer-launcher.service

echo "==> Starting the kiosk and AirPlay receiver at login (XDG autostart; Pi OS runs these under labwc and wayfire)"
KIOSK_CMD="$FIREFOX --kiosk http://localhost:8080/?kiosk=1"
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/castinglayer-kiosk.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Castinglayer launcher
Exec=sh -c 'sleep 3; $KIOSK_CMD'
DESKTOP
cat > "$HOME/.config/autostart/castinglayer-airplay.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Castinglayer AirPlay receiver
Exec=/usr/local/bin/castinglayer-airplay
DESKTOP
# Boot to the desktop, logged in automatically, so the launcher comes up on its own.
if command -v raspi-config >/dev/null; then
  sudo raspi-config nonint do_boot_behaviour B4 || true
fi

IP="$(hostname -I | awk '{print $1}')"
cat <<DONE

All set. Reboot to start:   sudo reboot

After it boots:
  - The TV shows the launcher (Jellyfin, Casts, Settings, Inputs).
  - From your phone, open http://$IP:8080 to use it as a remote.
  - On the Mac: Control Center -> Screen Mirroring -> $(hostname).
  - Set your Jellyfin server URL under Settings.
DONE
