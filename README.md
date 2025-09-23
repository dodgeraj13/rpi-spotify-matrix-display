# Raspberry Pi Spotify Matrix Display

## Features

- 🎵 **Real-time Spotify Integration**: Display currently playing track information
- 🖼️ **Display Modes**: Show album artwork in fullscreen or compact mode
- 🎨 **Smooth Animations**: Scrolling text for long track titles and artist names
- 🖥️ **Emulator Support**: Test on your computer before deploying to Raspberry Pi

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/rpi-spotify-matrix-display.git

# Enter the repo
cd rpi-spotify-matrix-display

# Install using Makefile
make
```

## Quick Start


```bash
# Install dependencies
make install

# Run on Raspberry Pi with LED matrix
make run

# Run in emulator (no pi/matrix required)
make emulate

# Reset repository to a clean state
make clean

# Show all available commands
make help
```

```
rpi-spotify-matrix-display/
├── main.py                 # Main controller and entry point
├── spotify_player.py       # Spotify display logic
├── spotify_module.py       # Spotify API integration
├── config.ini              # Matrix and Spotify configuration
├── emulator_config.json    # Emulator configuration
├── pyproject.toml          # Project setup and dependencies
├── Makefile                # Useful run commands
├── LICENSE                 # GNU General Public License
├── tiny.otf                # Display font
├── screenshot.png          # Preview screenshot
└── README.md               # This file
```

## Spotify API Setup
1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app _(name/description can be anything)_
4. Add http://127.0.0.1:8080/callback to Redirect URIs
5. Save and copy Client ID and Secret for later

## Screenshots

![Matrix Display Screenshot](screenshot.png)

## Changelog

### Version 2.0
- Complete rewrite for cleaner architecture
- Migrated from requirements.txt to pyproject.toml
- Added Makefile for useful run commands

### Version 1.0
- Fork of matrix-dashboard project