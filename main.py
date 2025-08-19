#!/usr/bin/env python3
"""
Raspberry Pi Spotify Matrix Display Controller

Main controller for displaying Spotify album art on an LED matrix.
Supports both hardware and emulated matrix modes.
"""

import argparse
import configparser
import math
import sys
import time
import warnings
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

from spotify_player import SpotifyScreen
from spotify_module import SpotifyModule


class MatrixController:
    """Main controller for the LED matrix display."""
    
    def __init__(self, config_path: Path, is_emulated: bool = False, fullscreen: bool = False):
        self.config_path = config_path
        self.is_emulated = is_emulated
        self.fullscreen = fullscreen
        self.canvas_width = 64
        self.canvas_height = 64
        
        # Load configuration
        self.config = self._load_config()
        
        # Initialize modules and apps
        self.modules = {'spotify': SpotifyModule(self.config)}
        self.apps = [SpotifyScreen(self.config, self.modules, self.fullscreen)]
        
        # Setup matrix
        self.matrix = self._setup_matrix()
        
        # Runtime variables
        self.shutdown_delay = self.config.getint('Matrix', 'shutdown_delay', fallback=600)
        self.black_screen = Image.new("RGB", (self.canvas_width, self.canvas_height), (0, 0, 0))
        self.last_active_time = math.floor(time.time())
    
    def _load_config(self) -> configparser.ConfigParser:
        """Load configuration from INI file."""
        config = configparser.ConfigParser()
        
        if not self.config_path.exists():
            print(f"Configuration file not found: {self.config_path}")
            sys.exit(1)
        
        config.read(self.config_path)
        return config
    
    def _setup_matrix(self):
        """Setup the LED matrix with appropriate options."""
        # Import matrix library based on mode
        if self.is_emulated:
            from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions
        else:
            from rgbmatrix import RGBMatrix, RGBMatrixOptions
        
        options = RGBMatrixOptions()
        options.hardware_mapping = self.config.get('Matrix', 'hardware_mapping', fallback='regular')
        options.rows = self.canvas_width
        options.cols = self.canvas_height
        options.brightness = 100 if self.is_emulated else self.config.getint('Matrix', 'brightness', fallback=100)
        options.gpio_slowdown = self.config.getint('Matrix', 'gpio_slowdown', fallback=1)
        options.limit_refresh_rate_hz = self.config.getint('Matrix', 'limit_refresh_rate_hz', fallback=0)
        options.drop_privileges = False
        
        return RGBMatrix(options=options)
    
    def run(self):
        """Main display loop."""
        print("Starting Spotify Matrix Display...")
        
        try:
            while True:
                frame, is_playing = self.apps[0].generate()
                current_time = math.floor(time.time())
                
                if frame is not None:
                    if is_playing:
                        self.last_active_time = current_time
                    elif current_time - self.last_active_time >= self.shutdown_delay:
                        frame = self.black_screen
                else:
                    frame = self.black_screen
                
                self.matrix.SetImage(frame)
                time.sleep(0.08)
                
        except KeyboardInterrupt:
            print("\nShutting down gracefully...")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources."""
        if hasattr(self, 'matrix'):
            self.matrix.Clear()
            del self.matrix


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog='RpiSpotifyMatrixDisplay',
        description='Displays album art of currently playing song on an LED matrix'
    )
    
    parser.add_argument(
        '-f', '--fullscreen', 
        action='store_true', 
        help='Always display album art in fullscreen'
    )
    parser.add_argument(
        '-e', '--emulated', 
        action='store_true', 
        help='Run in a matrix emulator'
    )
    parser.add_argument(
        '-c', '--config',
        type=Path,
        default=Path('config.ini'),
        help='Path to configuration file (default: config.ini)'
    )
    
    args = parser.parse_args()
    
    # Suppress deprecation warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    
    try:
        controller = MatrixController(
            config_path=args.config,
            is_emulated=args.emulated,
            fullscreen=args.fullscreen
        )
        controller.run()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
