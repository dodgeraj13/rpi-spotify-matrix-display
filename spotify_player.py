#!/usr/bin/env python3
"""
Spotify Player Screen Module

Handles the display of Spotify track information and album art on the LED matrix.
"""

import math
import threading
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont

from spotify_module import SpotifyModule, PlaybackInfo


class SpotifyPlayer:
    """Main Spotify display for the LED matrix."""
    
    # Display constants
    CANVAS_WIDTH = 64
    CANVAS_HEIGHT = 64
    TITLE_COLOR = (255, 255, 255)
    ARTIST_COLOR = (255, 255, 255)
    PLAY_COLOR = (102, 240, 110)
    SCROLL_DELAY = 4
    PAUSED_DELAY = 5
    FETCH_INTERVAL = 1
    

    def __init__(self, config, spotify_module: SpotifyModule, fullscreen: bool = False):
        self.spotify_module = spotify_module
        self.full_screen_always = fullscreen
        
        # Load font
        try:
            # Try to load font from project root first, then relative to current file
            font_paths = [
                Path("tiny.otf"),  # From project root
                Path(__file__).parent / "tiny.otf"  # Relative to current file
            ]
            
            font_loaded = False
            for font_path in font_paths:
                if font_path.exists():
                    self.font = ImageFont.truetype(str(font_path), 5)
                    font_loaded = True
                    break
            
            if not font_loaded:
                raise FileNotFoundError("Font file not found")
                
        except (OSError, FileNotFoundError):
            print("Warning: Could not load font 'tiny.otf', using default")
            self.font = ImageFont.load_default()
        
        # Track state
        self.current_art_url = ''
        self.current_art_img: Optional[Image.Image] = None
        self.current_title = ''
        self.current_artist = ''
        
        # Animation state
        self.title_animation_cnt = 0
        self.artist_animation_cnt = 0
        self.last_title_reset = math.floor(time.time())
        self.last_artist_reset = math.floor(time.time())
        
        # Playback state
        self.paused = True
        self.paused_time = math.floor(time.time())
        self.is_playing = False
        
        # Shutdown delay logic
        self.shutdown_delay = config.getint('Matrix', 'shutdown_delay', fallback=600)
        self.last_active_time = math.floor(time.time())
        self.black_screen = Image.new("RGB", (self.CANVAS_WIDTH, self.CANVAS_HEIGHT), (0, 0, 0))
        
        # Spotify integration
        self.response: Optional[PlaybackInfo] = None
        
        # Start background thread for Spotify data
        self.thread = threading.Thread(target=self._get_current_playback_async, daemon=True)
        self.thread.start()


    def _get_current_playback_async(self):
        """Background thread for fetching Spotify playback data."""
        time.sleep(3)  # Initial delay
        while True:
            try:
                self.response = self.spotify_module.get_current_playback()
                time.sleep(self.FETCH_INTERVAL)
            except Exception as e:
                print(f"Error fetching Spotify data: {e}")
                time.sleep(self.FETCH_INTERVAL)
    

    def generate(self) -> Optional[Image.Image]:
        """Generate the current display frame."""
        if not self.spotify_module.queue.empty():
            self.response = self.spotify_module.queue.get()
            self.spotify_module.queue.queue.clear()
        
        return self._generate_frame(self.response)


    def _generate_frame(self, response: Optional[PlaybackInfo]) -> Optional[Image.Image]:
        """Generate a display frame from Spotify response."""
        current_time = math.floor(time.time())
        
        if response is None:
            return self._generate_inactive_frame()
        
        # Access attributes directly from the dataclass object
        artist = response.artist
        title = response.title
        art_url = response.art_url
        is_playing = response.is_playing
        progress_ms = response.progress_ms
        duration_ms = response.duration_ms
        
        # Update last active time if playing
        if is_playing:
            self.last_active_time = current_time
        
        # Check if we should show black screen due to inactivity
        if current_time - self.last_active_time >= self.shutdown_delay:
            return self.black_screen
        
        if self.full_screen_always:
            return self._generate_fullscreen_frame(art_url, is_playing)
        else:
            return self._generate_now_playing_frame(
                artist, title, art_url, is_playing, progress_ms, duration_ms
            )
    

    def _generate_fullscreen_frame(self, art_url: str, is_playing: bool) -> Image.Image:
        """Generate fullscreen album art frame."""
        if art_url and self.current_art_url != art_url:
            self.current_art_url = art_url
            self.current_art_img = self._fetch_and_resize_image(art_url, self.CANVAS_WIDTH, self.CANVAS_HEIGHT)
        
        frame = Image.new("RGB", (self.CANVAS_WIDTH, self.CANVAS_HEIGHT), (0, 0, 0))
        if self.current_art_img:
            frame.paste(self.current_art_img, (0, 0))
        
        return frame


    def _generate_now_playing_frame(self, artist: str, title: str, art_url: str, 
                           is_playing: bool, progress_ms: int, duration_ms: int) -> Image.Image:
        """Generate now playing display frame with album art and text."""
        self._update_playback_state(is_playing)
        self._update_track_info(artist, title)
        self._update_album_art(art_url, is_playing)
        
        frame = Image.new("RGB", (self.CANVAS_WIDTH, self.CANVAS_HEIGHT), (0, 0, 0))
        draw = ImageDraw.Draw(frame)
        
        # Show fullscreen when paused (after pause delay)
        current_time = math.floor(time.time())
        show_fullscreen = not is_playing and (current_time - self.paused_time >= self.PAUSED_DELAY)
        
        if show_fullscreen and self.current_art_img and art_url:
            if self.current_art_img.size == (48, 48):
                self.current_art_img = self._fetch_and_resize_image(art_url, self.CANVAS_WIDTH, self.CANVAS_HEIGHT)
            frame.paste(self.current_art_img, (0, 0))
            return frame
        
        # Show compact view
        if self.current_art_img and self.current_art_img.size == (48, 48):
            frame.paste(self.current_art_img, (8, 14))
        
        # Draw text overlays
        self._draw_scrolling_text(draw, title, artist)
        
        # Draw progress bar
        self._draw_progress_bar(draw, progress_ms, duration_ms)
        
        # Draw play/pause indicator
        self._draw_play_pause_indicator(draw, is_playing)
        
        return frame


    def _generate_inactive_frame(self) -> Optional[Image.Image]:
        """Generate frame when no active playback."""
        current_time = math.floor(time.time())
        
        # Check if we should show black screen due to inactivity
        if current_time - self.last_active_time >= self.shutdown_delay:
            return self.black_screen
        
        self._reset_state()
        return None
    

    def _update_playback_state(self, is_playing: bool):
        """Update internal playback state."""
        if not is_playing and not self.paused:
            self.paused_time = math.floor(time.time())
            self.paused = True
        elif is_playing and self.paused:
            # Reset animation state when transitioning from paused to playing
            self._reset_animation_state()
            self.paused_time = math.floor(time.time())
            self.paused = False
        
        self.is_playing = is_playing


    def _update_track_info(self, artist: str, title: str):
        """Update track information and reset animations if needed."""
        if self.current_title != title or self.current_artist != artist:
            self.current_artist = artist
            self.current_title = title
            self._reset_animation_state()


    def _update_album_art(self, art_url: str, is_playing: bool):
        """Update album art based on playback state."""
        if not art_url:
            return
            
        current_time = math.floor(time.time())
        show_fullscreen = not is_playing and (current_time - self.paused_time >= self.PAUSED_DELAY)
        
        if show_fullscreen and self.current_art_url != art_url:
            self.current_art_url = art_url
            self.current_art_img = self._fetch_and_resize_image(art_url, self.CANVAS_WIDTH, self.CANVAS_HEIGHT)
        elif not show_fullscreen and (self.current_art_url != art_url or 
                                    (self.current_art_img and self.current_art_img.size == (self.CANVAS_WIDTH, self.CANVAS_HEIGHT))):
            self.current_art_url = art_url
            self.current_art_img = self._fetch_and_resize_image(art_url, 48, 48)
    

    def _fetch_and_resize_image(self, url: str, width: int, height: int) -> Optional[Image.Image]:
        """Fetch and resize an image from URL."""
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content))
            return img.resize((width, height), resample=Image.LANCZOS)
        except Exception as e:
            print(f"Error fetching image {url}: {e}")
            return None


    def _draw_scrolling_text(self, draw: ImageDraw.Draw, title: str, artist: str):
        """Draw scrolling text for title and artist."""
        text_length = self.CANVAS_WIDTH - 12
        x_offset = 1
        spacer = "     "
        
        # Handle None values
        title = title or "Unknown Title"
        artist = artist or "Unknown Artist"
        
        # Draw title
        title_len = self.font.getlength(title)
        if title_len > text_length:
            scroll_text = title + spacer + title
            draw.text((x_offset - self.title_animation_cnt, 1), scroll_text, self.TITLE_COLOR, font=self.font)
            self._update_title_animation()
        else:
            draw.text((x_offset, 1), title, self.TITLE_COLOR, font=self.font)
        
        # Draw artist
        artist_len = self.font.getlength(artist)
        if artist_len > text_length:
            scroll_text = artist + spacer + artist
            draw.text((x_offset - self.artist_animation_cnt, 7), scroll_text, self.ARTIST_COLOR, font=self.font)
            self._update_artist_animation()
        else:
            draw.text((x_offset, 7), artist, self.ARTIST_COLOR, font=self.font)
        
        # Clear text areas
        draw.rectangle((0, 0, 0, 12), fill=(0, 0, 0))
        draw.rectangle((52, 0, 63, 12), fill=(0, 0, 0))


    def _update_title_animation(self):
        """Update title scrolling animation."""
        current_time = math.floor(time.time())
        if current_time - self.last_title_reset >= self.SCROLL_DELAY:
            self.title_animation_cnt += 1
        
        title_text = self.current_title or "Unknown Title"
        if (self.title_animation_cnt == 0 and self.artist_animation_cnt > 0 or
            self.title_animation_cnt >= self.font.getlength(title_text + "     ")):
            self.title_animation_cnt = 0
            self.last_title_reset = current_time


    def _update_artist_animation(self):
        """Update artist scrolling animation."""
        current_time = math.floor(time.time())
        if current_time - self.last_artist_reset >= self.SCROLL_DELAY:
            self.artist_animation_cnt += 1
        
        artist_text = self.current_artist or "Unknown Artist"
        if (self.artist_animation_cnt == 0 and self.title_animation_cnt > 0 or
            self.artist_animation_cnt >= self.font.getlength(artist_text + "     ")):
            self.artist_animation_cnt = 0
            self.last_artist_reset = current_time


    def _draw_progress_bar(self, draw: ImageDraw.Draw, progress_ms: int, duration_ms: int):
        """Draw progress bar at bottom of display."""
        line_y = 63
        draw.rectangle((0, line_y - 1, 63, line_y), fill=(100, 100, 100))
        
        if duration_ms > 0:
            progress_width = round(((progress_ms / duration_ms) * 100) // 1.57)
            draw.rectangle((0, line_y - 1, progress_width, line_y), fill=self.PLAY_COLOR)


    def _draw_play_pause_indicator(self, draw: ImageDraw.Draw, is_playing: bool):
        """Draw play/pause indicator icon."""
        x, y = 55, 3
        
        if is_playing:
            # Pause icon (two vertical bars) when playing
            draw.line([(x, y), (x, y + 6)], fill=self.PLAY_COLOR, width=2)
            draw.line([(x + 3, y), (x + 3, y + 6)], fill=self.PLAY_COLOR, width=2)
        else:
            # Play icon (triangle) when paused
            draw.polygon([(x, y), (x, y + 6), (x + 4, y + 3)], fill=self.PLAY_COLOR)
    

    def _reset_animation_state(self):
        """Reset animation counters and timers."""
        self.title_animation_cnt = 0
        self.artist_animation_cnt = 0
        current_time = math.floor(time.time())
        self.last_title_reset = current_time
        self.last_artist_reset = current_time
    

    def _reset_state(self):
        """Reset all state variables."""
        self.current_art_url = ''
        self.is_playing = False
        self._reset_animation_state()
        self.paused = True
        self.paused_time = math.floor(time.time())