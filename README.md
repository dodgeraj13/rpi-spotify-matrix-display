# Raspberry Pi Spotify Matrix Display

A modern Python application that displays Spotify album art and track information on an LED matrix display. Built with modern Python practices, type hints, and clean architecture.

## Features

- 🎵 **Real-time Spotify Integration**: Display currently playing track information
- 🖼️ **Album Art Display**: Show album artwork in fullscreen or compact mode
- 📱 **Smart Display Modes**: Automatic switching between info and fullscreen views
- 🎨 **Smooth Animations**: Scrolling text for long track titles and artist names
- ⚙️ **Flexible Configuration**: Support for both INI files and environment variables
- 🖥️ **Emulator Support**: Test on your computer before deploying to Raspberry Pi
- 🐍 **Modern Python**: Built with Python 3.8+, type hints, and best practices

## Requirements

- Python 3.8 or higher
- Spotify Premium account
- Spotify API credentials

### Matrix Display Options
- **Emulator Mode**: Works on any computer for testing
- **Hardware Mode**: Requires building `rpi-rgb-led-matrix` from source on Raspberry Pi

## Installation

### Option 1: Install from source (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/rpi-spotify-matrix-display.git
cd rpi-spotify-matrix-display

# Install dependencies using Makefile
make install
```

### Option 2: Manual installation

```bash
# Clone the repository
git clone https://github.com/yourusername/rpi-spotify-matrix-display.git
cd rpi-spotify-matrix-display

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .
```

## Dependencies

The project requires the following Python packages:
- `Pillow>=11.3.0` - Image processing
- `numpy>=2.3.2` - Numerical operations
- `requests>=2.32.5` - HTTP requests
- `spotipy>=2.25.1` - Spotify Web API wrapper
- `RGBMatrixEmulator>=0.13.3` - Matrix emulator for development

## Quick Start

### Using Makefile (Recommended)

```bash
# Install dependencies
make install

# Run on Raspberry Pi with LED matrix
make run

# Run in emulator for testing
make emulate

# Run with fullscreen album art on hardware
make run-fullscreen

# Run with fullscreen album art in emulator
make emulate-fullscreen

# Show all available commands
make help
```

### Manual Commands

```bash
# Run display on a matrix
python main.py

# Emulate the display
python main.py -e

# Show fullscreen album art (can combine with -e)
python main.py -f
```

### Command Line Options

- `-e, --emulated`: Run in matrix emulator mode
- `-f, --fullscreen`: Always display album art in fullscreen
- `-h, --help`: Show help message

## Configuration

### Environment Variables

You can configure the application using environment variables:

```bash
# Matrix configuration
export MATRIX_HARDWARE_MAPPING="adafruit-hat-pwm"
export MATRIX_BRIGHTNESS="50"
export MATRIX_GPIO_SLOWDOWN="2"
export MATRIX_REFRESH_RATE="100"
export MATRIX_SHUTDOWN_DELAY="30"

# Spotify configuration
export SPOTIFY_CLIENT_ID="your_client_id"
export SPOTIFY_CLIENT_SECRET="your_client_secret"
export SPOTIFY_REDIRECT_URI="http://127.0.0.1:8080/callback"
export SPOTIFY_DEVICE_WHITELIST="Marantz AVR,Samsung TV"
```

### Configuration File

Alternatively, create a `config.ini` file:

```ini
[Matrix]
hardware_mapping = adafruit-hat-pwm
brightness = 50
gpio_slowdown = 2
limit_refresh_rate_hz = 100
shutdown_delay = 30

[Spotify]
client_id = your_client_id_here
client_secret = your_client_secret_here
redirect_uri = http://127.0.0.1:8080/callback
; device_whitelist = ['Marantz AVR', 'Samsung TV']
```

### Emulator Configuration

Customize the emulator appearance with `emulator_config.json`:

```json
{
    "pixel_glow": 6,
    "pixel_size": 8,
    "pixel_style": "square",
    "pixel_outline": 0,
    "display_adapter": "pygame"
}
```

## Development

### Project Structure

```
rpi-spotify-matrix-display/
├── main.py                  # Main controller and entry point
├── spotify_player.py        # Spotify player display logic
├── spotify_module.py        # Core Spotify API integration
├── config.ini              # Default configuration file
├── emulator_config.json    # Emulator appearance settings
├── tiny.otf                # Font file for text display
├── pyproject.toml          # Project configuration and dependencies
├── Makefile                # Build and run commands
└── README.md               # This file
```

### Available Make Commands

- `make install` - Install package dependencies
- `make run` - Run on Raspberry Pi with LED matrix
- `make emulate` - Run in emulator window for testing
- `make run-fullscreen` - Run on hardware with fullscreen artwork
- `make emulate-fullscreen` - Run in emulator with fullscreen artwork
- `make clean` - Reset repository to clean state
- `make help` - Show all available commands

## Spotify API Setup

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new application
3. Get your `client_id` and `client_secret`
4. Add `http://127.0.0.1:8080/callback` to redirect URIs
5. Update your configuration with the credentials

## Hardware Setup

### LED Matrix

This project supports various LED matrix configurations:

- **Adafruit HAT**: Use `hardware_mapping = adafruit-hat-pwm`
- **Regular**: Use `hardware_mapping = regular`
- **Custom**: Refer to [rpi-rgb-led-matrix documentation](https://github.com/hzeller/rpi-rgb-led-matrix)

### GPIO Configuration

Adjust `gpio_slowdown` based on your setup:
- **Value 1**: Standard Raspberry Pi
- **Value 2**: Raspberry Pi 2/3
- **Value 3**: Raspberry Pi 4

## Screenshots

![Matrix Display Screenshot](screenshot.png)

## Troubleshooting

### Common Issues

1. **Matrix not displaying**: Check GPIO permissions and hardware mapping
2. **Spotify authentication fails**: Verify API credentials and redirect URI
3. **Poor performance**: Adjust refresh rate and GPIO slowdown settings
4. **Font not loading**: Ensure `tiny.otf` is present

### Debug Mode

Enable debug output by setting environment variable:

```bash
export DEBUG=1
python main.py
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Run quality checks
6. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) - LED matrix library
- [spotipy](https://spotipy.readthedocs.io/) - Spotify Web API wrapper
- [Pillow](https://python-pillow.org/) - Image processing library
- [RGBMatrixEmulator](https://github.com/rm-hull/rgb-matrix-emulator) - Matrix emulator for development

## Changelog

### Version 2.0.0
- Complete rewrite with modern Python practices
- Type hints throughout the codebase
- Improved error handling and logging
- Better configuration management
- Cleaner architecture and separation of concerns
- Support for environment variables
- Enhanced documentation and examples
- Added Makefile for easy development workflow
- Integrated emulator support for testing
