#!/usr/bin/env python3
"""
main.py: Entry point for Raspberry Pi Spotify Matrix Display
 - Parses command line arguments
 - Loads config
 - Prepares matrix
 - Connects to Spotify API (via spotipy)
 - Sets up Spotify player
 - Runs main loop, until interrupted
"""

import argparse
import configparser
import sys
import time
import warnings
from pathlib import Path

from spotify_module import SpotifyModule
from spotify_player import SpotifyPlayer

def load_config(config_path: str) -> configparser.ConfigParser:
    config = configparser.ConfigParser()

    if not Path(config_path).exists():
        print(f"Configuration file not found: {config_path}")
        sys.exit(1)
    
    config.read(config_path)
    return config


def setup_matrix(config: configparser.ConfigParser, is_emulated: bool):
    if is_emulated:
        from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions
    else:
        try:
            from rgbmatrix import RGBMatrix, RGBMatrixOptions
        except ImportError:
            print("❌ Error: Could not import 'rgbmatrix' module.")
            print("💡 This command is meant for running on a Raspberry Pi connected to an RGB matrix.")
            print("   Use 'make emulate' to run the display within an emulator window.")
            sys.exit(1)
    
    options = RGBMatrixOptions()
    options.hardware_mapping = config.get('Matrix', 'hardware_mapping', fallback='regular')
    options.rows = 64
    options.cols = 64
    options.brightness = 100 if is_emulated else config.getint('Matrix', 'brightness', fallback=100)
    options.gpio_slowdown = config.getint('Matrix', 'gpio_slowdown', fallback=1)
    options.limit_refresh_rate_hz = config.getint('Matrix', 'limit_refresh_rate_hz', fallback=0)
    options.drop_privileges = False
    
    return RGBMatrix(options=options)


def main():
    parser = argparse.ArgumentParser(description='Raspberry Pi Spotify Matrix Display')
    parser.add_argument('-e', '--emulate', action='store_true', help='run within an emulator window')
    args = parser.parse_args()

    # Suppress Pillow 12 (2025-10-15) deprecation warning
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="PIL")
    
    try:
        config = load_config('config.ini')
        matrix = setup_matrix(config, args.emulate)
        
        spotify_module = SpotifyModule(config)
        spotify_player = SpotifyPlayer(config, spotify_module)
        
        while True:
            frame = spotify_player.generate()
            
            if frame:
                matrix.SetImage(frame)
            else:
                matrix.Clear()
            
            time.sleep(0.08)
            
    except KeyboardInterrupt:
        print(' Interrupted with Ctrl-C')


if __name__ == '__main__':
    main()