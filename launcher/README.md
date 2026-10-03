# TV launcher

A four-tile home screen for the TV: **Jellyfin**, **Casts**, **Settings**, **Inputs**. There are two versions: pick the one that matches your setup.

## A. On the TV itself (Google TV / Android TV)

`launcher/android-tv/` is an Android TV app plus `tv.sh`, which drives the TV over the network from your Mac. You don't need a remote.

1. **Get the APK:** open the repo's **Actions** tab on GitHub, open the latest *Android TV launcher APK* run, and download the `castinglayer-launcher` artifact. To build it yourself instead, run `cd launcher/android-tv && ./gradlew assembleRelease`; it needs the Android SDK.
2. **Turn on network debugging on the TV:** go to Settings → System → About and select *Build* 7 times. Then open Settings → System → Developer options and turn on *USB debugging*, plus *Wireless debugging* if it's listed. To navigate the TV menus, use the Google TV phone app as a remote or plug in a USB keyboard.
3. From the Mac:
   ```bash
   cd launcher/android-tv
   ./tv.sh pair <tv-ip>:<pair-port> <code>   # only if the TV shows "Pair device with pairing code"
   ./tv.sh connect <tv-ip>[:port]            # accept "Allow debugging?" on the TV
   ./tv.sh install ~/Downloads/app-release.apk
   ./tv.sh set-home                          # Home button now opens the launcher
   ./tv.sh jellyfin                          # installs Jellyfin from GitHub, no Play Store
   ./tv.sh remote                            # your keyboard is now the TV remote
   ```

### De-Google the TV

```bash
./tv.sh degoogle          # turns off YouTube, Assistant, Play Movies/Games, ambient mode, recommendations, stock launcher
./tv.sh degoogle --all    # also turns off Google Cast, the Play Store and the phone-app remote
./tv.sh regoogle          # undoes either one
```

The apps are disabled, not uninstalled, so everything can be reversed. Plain `degoogle` leaves **Google Cast on**, so `castlayer` keeps working. With `--all` the TV can no longer receive a cast; use the Pi for screen sharing instead. Google Play Services is never touched, because the TV may not boot cleanly without it. The only way to remove Google completely is to stop using the TV's own OS, which is what option B does.

## B. On a Raspberry Pi plugged into the TV (no Google at all)

`launcher/pi/` turns a Pi 4 or 5 running Raspberry Pi OS (with desktop) into the TV's box:

- The launcher runs in Firefox, in kiosk mode, at boot.
- **Casts:** UxPlay, an open-source AirPlay receiver. Mirror from the Mac via Control Center → Screen Mirroring, with under a second of delay.
- **Inputs:** switches the TV between the Pi and HDMI 1–N, and turns it on and off, over HDMI-CEC.
- **Jellyfin:** opens your Jellyfin server's web client, at the URL you set under Settings.
- Open `http://<pi-ip>:8080` on your phone and the same page works as a remote.

```bash
git clone https://github.com/cigarette1991/castinglayer.git
cd castinglayer/launcher/pi && ./setup.sh && sudo reboot
```
