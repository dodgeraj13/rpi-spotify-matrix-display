# rpi-spotify-matrix-display

A Spotify display for 64x64 RGB LED matrices.

- **🎵 Spotify API Integration** – Show off your currently playing track
- **🖼️ Multiple Modes** – Display album artwork alongside track details or fullscreen
- **🚗 Scrolling Text** – Auto-scrolling text for long track titles and artist names
- **⏯️ Playback Indicators** – Play/pause indicator and track progression bar
- **🖥️ Emulator Support** – Test on your computer before deploying to a Raspberry Pi

<br>

![emulator screenshot](screenshot.png)

## Spotify Setup
1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app _(name/description can be anything)_
3. Add http://127.0.0.1:8080/callback to Redirect URIs
4. Save and copy the Client ID and Secret for later

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/yourusername/rpi-spotify-matrix-display.git

# 2. Enter the repo
cd rpi-spotify-matrix-display

# 3. Make the project (will request client/secret)
make
```

## How to Run
```bash
# For a Raspberry Pi connected to a matrix
make run

# Otherwise, emulate using
make emulate
```

After running, follow instructions provided in the console. Pasted link should begin with http://127.0.0.1:8080/callback. After successful authorization, play a song and the display will appear!

---

### Building Your Own Display

Don't have a Raspberry Pi or RGB matrix yet? No worries! Feel free to mess around with emulation and come back to this section once you're ready.

**Parts List**

- [Adafruit 64x64 RGB LED Matrix - 2.5mm Pitch - 1/32 Scan](https://www.adafruit.com/product/3649)
- [Adafruit RGB Matrix Bonnet for Raspberry Pi](https://www.adafruit.com/product/3211)
- [Raspberry Pi 3B+](https://www.raspberrypi.com/products/raspberry-pi-3-model-b-plus/) (or newer)
- Any microSD card
- [5V 10A Power Supply Adapter](https://www.amazon.com/gp/product/B08HCS1X66)

I also 3d printed a [matrix stand](https://www.thingiverse.com/thing:3781875) and a [pi mount](https://www.thingiverse.com/thing:2732552) for my [own build](https://imgur.com/a/64x64-album-art-matrix-backside-AjrOa5e).

Once you have all the components, you can proceed with the hardware setup.

<details>
<summary>Hardware Guide</summary>

#### Step 1: Install Pi OS
- [Download the Raspberry Pi Imager](https://www.raspberrypi.com/software/)
- Choose your Raspberry Pi
- Select `Raspberry Pi OS (Other) - OS Lite (64bit)`
- Set hostname (I put matrix), set pass (I kept user as pi)
- Enter wifi credentials
- Enable ssh using password
- When done, insert microSD card in pi and wait a few min for boot up

#### Step 2: Login via ssh
- `ssh pi@matrix.local`
- This puts you in the `/home/pi` directory
- You can use `pwd` to confirm where you are throughout this process

#### Step 3: Update packages and install git
- `sudo apt update` (get latest packages)
- `sudo apt upgrade` (upgrade out of date packages)
- `sudo apt install git`

#### Step 4: Proceed with the Installation instructions above
</details>

---

### Acknowledgements
- allenslab for creating the original [matrix-dashboard](https://www.reddit.com/r/3Dprinting/comments/ujyy4g/i_designed_and_3d_printed_a_led_matrix_dashboard/) code
- typorter for the [RGBMatrixEmulator](https://github.com/ty-porter/RGBMatrixEmulator) project
- hzeller for the [rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) library