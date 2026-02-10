#!/usr/bin/env python3
"""
spotify_player.py: Handles the display of Spotify track information and album art on the LED matrix.
"""

import math
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Optional

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
    SLIDE_ANIMATION_FRAMES = 17  # Number of frames for slide animation
    ART_SIZE_COMPACT = (40, 40)  # Width, Height for compact album art (square, shrunken to make room for lyrics)
    ART_POSITION = (12, 14)  # X, Y position of album art (centered horizontally: (64-40)/2 = 12)
    LYRICS_START_Y = 55  # Y position to start drawing lyrics (below album art which ends at y=54)
    LYRICS_LINE_HEIGHT = 6  # Height of each lyric line
    

    def __init__(self, config, spotify_module: SpotifyModule):
        self.spotify_module = spotify_module
        self.always_fullscreen = config.getboolean('Matrix', 'always_fullscreen', fallback=False)
        
        # Load font
        try:
            font_paths = [
                Path("font.otf"),  # From project root
                Path(__file__).parent / "font.otf"  # Relative to current file
            ]
            
            for font_path in font_paths:
                if font_path.exists():
                    self.font = ImageFont.truetype(str(font_path), 5)
                    break
            else:
                raise FileNotFoundError("Font file not found")
                
        except (OSError, FileNotFoundError):
            print("Warning: Could not load font 'font.otf', using default")
            self.font = ImageFont.load_default()
        
        # Track state
        self.current_art_url = ''
        self.current_art_img: Optional[Image.Image] = None
        self.current_title = ''
        self.current_artist = ''
        self.current_track_id: Optional[str] = None
        self.current_prominent_color = self.PLAY_COLOR  # Default to green if no art
        
        # Queue history for detecting next/previous
        self.track_queue_history = []  # List of track_ids in order
        self.max_queue_history = 10  # Keep last 10 tracks
        
        # Slide animation state
        self.slide_animation_active = False
        self.slide_animation_frame = 0
        self.slide_direction = 1  # 1 for left (next), -1 for right (previous)
        self.previous_frame: Optional[Image.Image] = None
        self.previous_frame_modified: Optional[Image.Image] = None  # Cached modified previous frame
        self.next_frame: Optional[Image.Image] = None
        self.next_track_art_img: Optional[Image.Image] = None  # Cached art for next track
        self.next_track_art_url: Optional[str] = None
        
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
        self.response_timestamp: float = 0.0  # When response was last updated
        self.response_progress_ms: int = 0  # progress_ms at response_timestamp
        
        # Start background thread for Spotify data
        self.thread = threading.Thread(target=self._get_current_playback_async, daemon=True)
        self.thread.start()

    def _get_current_playback_async(self):
        """Background thread for fetching Spotify playback data."""
        time.sleep(3)  # Initial delay
        while True:
            try:
                self.response = self.spotify_module.get_current_playback()
                if self.response:
                    self.response_timestamp = time.time()
                    self.response_progress_ms = self.response.progress_ms
                time.sleep(self.FETCH_INTERVAL)
            except Exception as e:
                print(f"Error fetching Spotify data: {e}")
                time.sleep(self.FETCH_INTERVAL)
    

    def generate(self) -> Optional[Image.Image]:
        """Generate the current display frame."""
        if not self.spotify_module.queue.empty():
            self.response = self.spotify_module.queue.get()
            self.spotify_module.queue.queue.clear()
            if self.response:
                self.response_timestamp = time.time()
                self.response_progress_ms = self.response.progress_ms
        
        return self._generate_frame(self.response)


    def _generate_frame(self, response: Optional[PlaybackInfo]) -> Optional[Image.Image]:
        """Generate a display frame from Spotify response."""
        current_time = math.floor(time.time())
        
        if response is None:
            return self._generate_inactive_frame()
        
        # Extract playback info
        artist = response.artist
        title = response.title
        art_url = response.art_url
        is_playing = response.is_playing
        duration_ms = response.duration_ms
        lyrics = response.lyrics
        track_id = response.track_id
        
        # Extrapolate progress_ms if playing to account for time since last API call
        # This ensures lyrics appear on time even between API updates
        if is_playing and self.response_timestamp > 0:
            elapsed_seconds = time.time() - self.response_timestamp
            elapsed_ms = int(elapsed_seconds * 1000)
            progress_ms = self.response_progress_ms + elapsed_ms
            # Clamp to duration to avoid going past the end
            if duration_ms > 0:
                progress_ms = min(progress_ms, duration_ms)
        else:
            progress_ms = response.progress_ms
        
        # Check for track change and determine direction
        if track_id and track_id != self.current_track_id:
            self._handle_track_change(track_id)
        
        # Update last active time if playing
        if is_playing:
            self.last_active_time = current_time
        
        # Check if we should show black screen due to inactivity
        if current_time - self.last_active_time >= self.shutdown_delay:
            return self.black_screen
        
        # Handle slide animation
        if self.slide_animation_active:
            frame = self._generate_slide_animation_frame(
                artist, title, art_url, is_playing, progress_ms, duration_ms, lyrics
            )
            if frame is not None:
                return frame
            # Animation complete, continue with normal frame generation
        
        if self.always_fullscreen:
            return self._generate_fullscreen_frame(art_url, is_playing)
        else:
            return self._generate_now_playing_frame(
                artist, title, art_url, is_playing, progress_ms, duration_ms, lyrics
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


    def _generate_slide_animation_frame(self, artist: str, title: str, art_url: str,
                                       is_playing: bool, progress_ms: int, duration_ms: int,
                                       lyrics: Optional[dict] = None) -> Optional[Image.Image]:
        """Generate slide animation frame during track transition."""
        if not self.slide_animation_active:
            return None
        
        # Generate new frame with updated track info
        # Temporarily update track info for frame generation
        temp_artist = self.current_artist
        temp_title = self.current_title
        temp_art_url = self.current_art_url
        temp_art_img = self.current_art_img
        temp_prominent_color = self.current_prominent_color
        
        # Fetch new album art once (cache it for subsequent frames)
        if art_url and (art_url != self.next_track_art_url or self.next_track_art_img is None):
            if not is_playing:
                # Fullscreen size for paused
                self.next_track_art_img = self._fetch_and_resize_image(art_url, self.CANVAS_WIDTH, self.CANVAS_HEIGHT)
            else:
                # Compact size for playing
                self.next_track_art_img = self._fetch_and_resize_image(art_url, self.ART_SIZE_COMPACT[0], self.ART_SIZE_COMPACT[1])
            self.next_track_art_url = art_url
        elif not art_url:
            # No art URL, use default color
            self.current_prominent_color = self.PLAY_COLOR
        
        new_art_img = self.next_track_art_img
        
        self.current_artist = artist
        self.current_title = title
        self.current_art_url = art_url
        self.current_art_img = new_art_img if new_art_img else temp_art_img
        self._update_playback_state(is_playing)
        
        # Generate new frame
        new_frame = Image.new("RGB", (self.CANVAS_WIDTH, self.CANVAS_HEIGHT), (0, 0, 0))
        draw = ImageDraw.Draw(new_frame)
        
        # Show fullscreen when paused (after pause delay)
        current_time = math.floor(time.time())
        show_fullscreen = not is_playing and (current_time - self.paused_time >= self.PAUSED_DELAY)
        
        if show_fullscreen and self.current_art_img and art_url:
            if self.current_art_img.size == self.ART_SIZE_COMPACT:
                self.current_art_img = self._fetch_and_resize_image(art_url, self.CANVAS_WIDTH, self.CANVAS_HEIGHT)
            new_frame.paste(self.current_art_img, (0, 0))
        else:
            # Show compact view
            if self.current_art_img and self.current_art_img.size == self.ART_SIZE_COMPACT:
                new_frame.paste(self.current_art_img, self.ART_POSITION)
            
            # Draw track title and artist text (without updating animation state)
            text_length = self.CANVAS_WIDTH - 12
            x_offset = 1
            spacer = "     "
            
            title = title or "Unknown Title"
            artist = artist or "Unknown Artist"
            
            # Draw title (static, no scrolling during animation)
            title_len = self.font.getlength(title)
            if title_len > text_length:
                draw.text((x_offset, 1), title[:20] + "...", self.TITLE_COLOR, font=self.font)
            else:
                draw.text((x_offset, 1), title, self.TITLE_COLOR, font=self.font)
            
            # Draw artist (static, no scrolling during animation)
            artist_len = self.font.getlength(artist)
            if artist_len > text_length:
                draw.text((x_offset, 7), artist[:20] + "...", self.ARTIST_COLOR, font=self.font)
            else:
                draw.text((x_offset, 7), artist, self.ARTIST_COLOR, font=self.font)
            
            # Clear text areas
            draw.rectangle((0, 0, 0, 12), fill=(0, 0, 0))
            draw.rectangle((52, 0, 63, 12), fill=(0, 0, 0))

            # Draw lyrics if available and playing
            if is_playing and lyrics and 'lyrics' in lyrics and 'lines' in lyrics['lyrics']:
                self._draw_lyrics(new_frame, draw, lyrics, progress_ms)
            
            # Draw play/pause indicator for the new frame (sliding in)
            # Don't draw progress bar - it will be drawn statically on top
            self._draw_play_pause_indicator(draw, is_playing)
        
        # Restore previous state
        self.current_artist = temp_artist
        self.current_title = temp_title
        self.current_art_url = temp_art_url
        self.current_art_img = temp_art_img
        # Keep the new prominent color for the progress bar (drawn on composite)
        # Don't restore temp_prominent_color - we want the new track's color
        
        # Calculate slide progress (0.0 to 1.0)
        progress = self.slide_animation_frame / self.SLIDE_ANIMATION_FRAMES
        
        # Create composite frame
        composite = Image.new("RGB", (self.CANVAS_WIDTH, self.CANVAS_HEIGHT), (0, 0, 0))
        
        if self.previous_frame_modified:
            # Calculate offsets based on direction
            # For left slide (next): previous moves left, new comes from right
            # For right slide (previous): previous moves right, new comes from left
            if self.slide_direction == 1:  # Left (next)
                prev_offset = int(-self.CANVAS_WIDTH * progress)
                new_offset = int(self.CANVAS_WIDTH * (1 - progress))
            else:  # Right (previous)
                prev_offset = int(self.CANVAS_WIDTH * progress)
                new_offset = int(-self.CANVAS_WIDTH * (1 - progress))
            
            # Draw previous frame (with hidden progress bar and play/pause) - use cached version
            composite.paste(self.previous_frame_modified, (prev_offset, 0))
            # Draw new frame (with play/pause visible, but no progress bar)
            composite.paste(new_frame, (new_offset, 0))
        else:
            # No previous frame (first track or fullscreen), just show new frame
            composite.paste(new_frame, (0, 0))
        
        # Draw static progress bar on top (doesn't transition)
        composite_draw = ImageDraw.Draw(composite)
        self._draw_progress_bar(composite_draw, progress_ms, duration_ms)
        
        # Update animation frame
        self.slide_animation_frame += 1
        
        # Check if animation is complete
        if self.slide_animation_frame >= self.SLIDE_ANIMATION_FRAMES:
            self.slide_animation_active = False
            self.slide_animation_frame = 0
            self.previous_frame = None
            self.previous_frame_modified = None
            self.next_frame = None
            # Preserve cached image before clearing
            cached_art_img = self.next_track_art_img
            cached_art_url = self.next_track_art_url
            self.next_track_art_img = None
            self.next_track_art_url = None
            # Now update the actual track info
            self._update_track_info(artist, title)
            # Reuse cached image if available to avoid re-fetching
            self._update_album_art(art_url, is_playing, cached_art_img if cached_art_url == art_url else None)
        
        return composite

    def _generate_now_playing_frame(self, artist: str, title: str, art_url: str, 
                           is_playing: bool, progress_ms: int, duration_ms: int, lyrics: Optional[dict] = None) -> Image.Image:
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
            if self.current_art_img.size == self.ART_SIZE_COMPACT:
                self.current_art_img = self._fetch_and_resize_image(art_url, self.CANVAS_WIDTH, self.CANVAS_HEIGHT)
            frame.paste(self.current_art_img, (0, 0))
            return frame
        
        # Show compact view
        if self.current_art_img and self.current_art_img.size == self.ART_SIZE_COMPACT:
            frame.paste(self.current_art_img, self.ART_POSITION)
        
        # Draw track title and artist text
        self._draw_scrolling_text(draw, title, artist)

        # Draw lyrics if available and playing
        if is_playing and lyrics and 'lyrics' in lyrics and 'lines' in lyrics['lyrics']:
            self._draw_lyrics(frame, draw, lyrics, progress_ms)
        
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


    def _handle_track_change(self, new_track_id: str):
        """Handle track change and determine slide direction."""
        if not new_track_id:
            return
        
        # Capture current frame as previous before any updates
        if not self.always_fullscreen and (self.current_title or self.current_artist):
            # Generate frame with current state
            self.previous_frame = self._generate_now_playing_frame(
                self.current_artist, self.current_title, self.current_art_url,
                self.is_playing, 0, 0, None
            )
            # Pre-modify previous frame (hide progress bar and play/pause) and cache it
            self.previous_frame_modified = self.previous_frame.copy()
            prev_draw = ImageDraw.Draw(self.previous_frame_modified)
            # Cover progress bar at bottom (line 63)
            prev_draw.rectangle((0, 62, 63, 63), fill=(0, 0, 0))
            # Cover play/pause indicator (around 55, 3 to 59, 9)
            prev_draw.rectangle((54, 2, 63, 10), fill=(0, 0, 0))
        else:
            self.previous_frame_modified = None
        
        # Determine direction based on queue history
        slide_direction = 1  # Default to left (next)
        
        if self.current_track_id and new_track_id in self.track_queue_history:
            # Track is in history - check position
            current_index = -1
            new_index = -1
            
            for i, tid in enumerate(self.track_queue_history):
                if tid == self.current_track_id:
                    current_index = i
                if tid == new_track_id:
                    new_index = i
            
            # If new track is before current in history, it's previous (right)
            if new_index < current_index and new_index >= 0:
                slide_direction = -1  # Right (previous)
        
        # Start slide animation
        self.slide_animation_active = True
        self.slide_animation_frame = 0
        self.slide_direction = slide_direction
        
        # Clear cached next track art (will be fetched when animation starts)
        self.next_track_art_img = None
        self.next_track_art_url = None
        
        # Update track ID (but don't update other track info yet - that happens after animation)
        self.current_track_id = new_track_id
        
        # Update queue history
        if new_track_id not in self.track_queue_history:
            self.track_queue_history.append(new_track_id)
        else:
            # Move to end if already in history
            self.track_queue_history.remove(new_track_id)
            self.track_queue_history.append(new_track_id)
        
        # Limit history size
        if len(self.track_queue_history) > self.max_queue_history:
            self.track_queue_history = self.track_queue_history[-self.max_queue_history:]
    
    def _update_track_info(self, artist: str, title: str):
        """Update track information and reset animations if needed."""
        if self.current_title != title or self.current_artist != artist:
            self.current_artist = artist
            self.current_title = title
            self._reset_animation_state()


    def _update_album_art(self, art_url: str, is_playing: bool, cached_img: Optional[Image.Image] = None):
        """Update album art based on playback state."""
        if not art_url:
            self.current_prominent_color = self.PLAY_COLOR
            return
            
        current_time = math.floor(time.time())
        show_fullscreen = not is_playing and (current_time - self.paused_time >= self.PAUSED_DELAY)
        
        if show_fullscreen and self.current_art_url != art_url:
            self.current_art_url = art_url
            # Reuse cached image if available and correct size, otherwise fetch/resize
            if cached_img and cached_img.size == (self.CANVAS_WIDTH, self.CANVAS_HEIGHT):
                self.current_art_img = cached_img
            elif cached_img and cached_img.size == self.ART_SIZE_COMPACT:
                # Resize from compact size to 64x64
                self.current_art_img = cached_img.resize((self.CANVAS_WIDTH, self.CANVAS_HEIGHT), resample=Image.LANCZOS)
            else:
                self.current_art_img = self._fetch_and_resize_image(art_url, self.CANVAS_WIDTH, self.CANVAS_HEIGHT)
        elif not show_fullscreen:
            needs_update = (self.current_art_url != art_url or 
                          (self.current_art_img and self.current_art_img.size == (self.CANVAS_WIDTH, self.CANVAS_HEIGHT)))
            if needs_update:
                self.current_art_url = art_url
                # Reuse cached image if available and correct size, otherwise fetch/resize
                if cached_img and cached_img.size == self.ART_SIZE_COMPACT:
                    self.current_art_img = cached_img
                elif cached_img and cached_img.size == (self.CANVAS_WIDTH, self.CANVAS_HEIGHT):
                    # Resize from 64x64 to compact size
                    self.current_art_img = cached_img.resize(self.ART_SIZE_COMPACT, resample=Image.LANCZOS)
                else:
                    self.current_art_img = self._fetch_and_resize_image(art_url, self.ART_SIZE_COMPACT[0], self.ART_SIZE_COMPACT[1])
    

    def _is_gray_or_white(self, r: int, g: int, b: int) -> bool:
        """Check if a color is gray or white."""
        # Calculate the difference between max and min RGB values
        max_val = max(r, g, b)
        min_val = min(r, g, b)
        diff = max_val - min_val
        
        # Gray/white colors have low difference between RGB components
        # Threshold: if difference is less than 30, it's likely gray/white
        return diff < 30

    def _is_too_dark(self, r: int, g: int, b: int, threshold: int = 120) -> bool:
        """Check if a color is too dark (brightness below threshold)."""
        brightness = max(r, g, b)
        return brightness < threshold

    def _colors_similar_hue(self, r1: int, g1: int, b1: int, r2: int, g2: int, b2: int, threshold: float = 0.15) -> bool:
        """Check if two colors have similar hue (color family)."""
        # Normalize colors to compare hue ratios
        # Avoid division by zero
        max1 = max(r1, g1, b1) or 1
        max2 = max(r2, g2, b2) or 1
        
        # Calculate normalized RGB ratios
        ratios1 = (r1 / max1, g1 / max1, b1 / max1)
        ratios2 = (r2 / max2, g2 / max2, b2 / max2)
        
        # Check if ratios are similar (within threshold)
        diff = sum(abs(a - b) for a, b in zip(ratios1, ratios2))
        return diff < threshold

    def _is_vibrant_bright(self, r: int, g: int, b: int) -> bool:
        """Check if a color is vibrant and bright."""
        # First check if it's gray or white - exclude those
        if self._is_gray_or_white(r, g, b):
            return False
        
        # Calculate brightness (0-255)
        brightness = max(r, g, b)
        
        # Calculate saturation (0.0-1.0)
        max_val = max(r, g, b)
        min_val = min(r, g, b)
        if max_val == 0:
            saturation = 0.0
        else:
            saturation = (max_val - min_val) / max_val
        
        # Require high saturation (>0.3) and good brightness (>100)
        return saturation > 0.3 and brightness > 100

    def _extract_prominent_color(self, img: Image.Image) -> tuple:
        """Extract the most prominent vibrant and bright color from an image."""
        try:
            # Resize to small size for faster processing
            small_img = img.resize((16, 16), resample=Image.LANCZOS)
            
            # Convert to RGB if needed
            if small_img.mode != 'RGB':
                small_img = small_img.convert('RGB')
            
            # Get all pixels
            pixels = list(small_img.getdata())
            
            # Filter to only vibrant, bright colors and count frequencies
            vibrant_color_counts = {}
            for r, g, b in pixels:
                if self._is_vibrant_bright(r, g, b):
                    # Quantize to reduce similar colors (round to nearest 16)
                    r_q = (r // 16) * 16
                    g_q = (g // 16) * 16
                    b_q = (b // 16) * 16
                    color = (r_q, g_q, b_q)
                    vibrant_color_counts[color] = vibrant_color_counts.get(color, 0) + 1
            
            # Find the most common vibrant color
            if vibrant_color_counts:
                most_common = max(vibrant_color_counts.items(), key=lambda x: x[1])[0]
                # Get average of original vibrant colors that match this quantized color
                matching_colors = [(r, g, b) for r, g, b in pixels 
                                 if self._is_vibrant_bright(r, g, b) and
                                 ((r // 16) * 16, (g // 16) * 16, (b // 16) * 16) == most_common]
                if matching_colors:
                    base_r = sum(c[0] for c in matching_colors) // len(matching_colors)
                    base_g = sum(c[1] for c in matching_colors) // len(matching_colors)
                    base_b = sum(c[2] for c in matching_colors) // len(matching_colors)
                    
                    # Safety check: ensure base color is not gray/white
                    if self._is_gray_or_white(base_r, base_g, base_b):
                        return self.PLAY_COLOR
                    
                    # Look for lighter variations of this color in the artwork
                    lighter_variations = []
                    for r, g, b in pixels:
                        if (self._is_vibrant_bright(r, g, b) and 
                            self._colors_similar_hue(base_r, base_g, base_b, r, g, b)):
                            brightness_base = max(base_r, base_g, base_b)
                            brightness_candidate = max(r, g, b)
                            # Prefer lighter versions (higher brightness)
                            if brightness_candidate > brightness_base:
                                lighter_variations.append((r, g, b, brightness_candidate))
                    
                    # If we found lighter variations, use the lightest one
                    if lighter_variations:
                        # Sort by brightness (descending) and take the lightest
                        lighter_variations.sort(key=lambda x: x[3], reverse=True)
                        best_r, best_g, best_b, _ = lighter_variations[0]
                        # Check if the color is too dark
                        if self._is_too_dark(best_r, best_g, best_b):
                            return self.PLAY_COLOR
                        return (best_r, best_g, best_b)
                    
                    # Otherwise use the base color, but check if it's too dark
                    if self._is_too_dark(base_r, base_g, base_b):
                        return self.PLAY_COLOR
                    return (base_r, base_g, base_b)
            
            # If no vibrant colors found, try to find any bright color (but not gray/white)
            bright_color_counts = {}
            for r, g, b in pixels:
                brightness = max(r, g, b)
                if brightness > 120 and not self._is_gray_or_white(r, g, b):  # At least somewhat bright and not gray/white
                    r_q = (r // 16) * 16
                    g_q = (g // 16) * 16
                    b_q = (b // 16) * 16
                    color = (r_q, g_q, b_q)
                    bright_color_counts[color] = bright_color_counts.get(color, 0) + 1
            
            if bright_color_counts:
                most_common = max(bright_color_counts.items(), key=lambda x: x[1])[0]
                matching_colors = [(r, g, b) for r, g, b in pixels 
                                 if max(r, g, b) > 120 and not self._is_gray_or_white(r, g, b) and
                                 ((r // 16) * 16, (g // 16) * 16, (b // 16) * 16) == most_common]
                if matching_colors:
                    base_r = sum(c[0] for c in matching_colors) // len(matching_colors)
                    base_g = sum(c[1] for c in matching_colors) // len(matching_colors)
                    base_b = sum(c[2] for c in matching_colors) // len(matching_colors)
                    
                    # Check if the base color is gray or white
                    if self._is_gray_or_white(base_r, base_g, base_b):
                        return self.PLAY_COLOR
                    
                    # Look for lighter variations of this color in the artwork
                    lighter_variations = []
                    for r, g, b in pixels:
                        brightness = max(r, g, b)
                        if (brightness > 120 and not self._is_gray_or_white(r, g, b) and
                            self._colors_similar_hue(base_r, base_g, base_b, r, g, b)):
                            brightness_base = max(base_r, base_g, base_b)
                            # Prefer lighter versions (higher brightness)
                            if brightness > brightness_base:
                                lighter_variations.append((r, g, b, brightness))
                    
                    # If we found lighter variations, use the lightest one
                    if lighter_variations:
                        # Sort by brightness (descending) and take the lightest
                        lighter_variations.sort(key=lambda x: x[3], reverse=True)
                        best_r, best_g, best_b, _ = lighter_variations[0]
                        # Check if the color is too dark
                        if self._is_too_dark(best_r, best_g, best_b):
                            return self.PLAY_COLOR
                        return (best_r, best_g, best_b)
                    
                    # Otherwise use the base color, but check if it's too dark
                    if self._is_too_dark(base_r, base_g, base_b):
                        return self.PLAY_COLOR
                    return (base_r, base_g, base_b)
            
            # Fallback to default green if no suitable color found or if color is gray/white
            return self.PLAY_COLOR
        except Exception as e:
            print(f"Error extracting color: {e}")
            return self.PLAY_COLOR

    def _fetch_and_resize_image(self, url: str, width: int, height: int) -> Optional[Image.Image]:
        """Fetch and resize an image from URL."""
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content))
            resized = img.resize((width, height), resample=Image.LANCZOS)
            
            # Extract prominent color from the original image (before resizing for display)
            # Use a larger version for better color accuracy
            color_img = img.resize((64, 64), resample=Image.LANCZOS)
            self.current_prominent_color = self._extract_prominent_color(color_img)
            
            return resized
        except Exception as e:
            print(f"Error fetching image {url}: {e}")
            return None


    def _draw_lyrics(self, frame: Image.Image, draw: ImageDraw.Draw, lyrics: dict, progress_ms: int):
        """Draw synchronized lyrics on the display - split into rows that fit on screen, showing progressively."""
        lyric_lines = lyrics['lyrics']['lines']
        current_time_ms = int(progress_ms)

        # Find the current lyric line and calculate its duration
        current_line_text = None
        current_line_start_ms = 0
        next_line_start_ms = None
        
        for i, line in enumerate(lyric_lines):
            line_start_ms = int(line['startTimeMs'])
            if line_start_ms <= current_time_ms:
                text = line['words'].strip()
                if text:
                    current_line_text = text
                    current_line_start_ms = line_start_ms
            else:
                # Found the next line - use its start time as the end of current line
                if current_line_text:
                    next_line_start_ms = line_start_ms
                break
        
        # If we're at the last line, estimate duration (use 3 seconds default)
        if current_line_text and next_line_start_ms is None:
            next_line_start_ms = current_line_start_ms + 3000
        
        if current_line_text and next_line_start_ms:
            # Calculate progress through this lyric line (0.0 to 1.0)
            line_duration_ms = next_line_start_ms - current_line_start_ms
            elapsed_in_line_ms = current_time_ms - current_line_start_ms
            progress_through_line = min(1.0, max(0.0, elapsed_in_line_ms / line_duration_ms)) if line_duration_ms > 0 else 0.0
            
            # Split the lyric line into rows that fit on screen
            text_width = self.CANVAS_WIDTH - 4  # Available width for lyrics
            words = [w for w in current_line_text.split() if w]  # Filter out empty strings
            rows = []
            current_row = ""
            
            for word in words:
                test_row = f"{current_row} {word}".strip() if current_row else word
                if self.font.getlength(test_row) <= text_width:
                    current_row = test_row
                else:
                    if current_row:
                        rows.append(current_row)
                    current_row = word
            
            if current_row:
                rows.append(current_row)
            
            # If no rows were created but we have text, use the whole line (might be very long)
            if not rows and current_line_text:
                # Try to fit as much as possible
                if self.font.getlength(current_line_text) <= text_width:
                    rows = [current_line_text]
                else:
                    # Force split by character if needed
                    rows = [current_line_text[:min(len(current_line_text), 30)]]
            
            # Show rows progressively based on progress through the lyric
            total_rows = len(rows)
            if total_rows > 0:
                # Calculate which row to show based on progress
                # Each row gets an equal portion of the lyric duration
                # Example: 3 rows, progress 0.0-0.33 shows row 0, 0.33-0.66 shows row 1, 0.66-1.0 shows row 2
                # For progress 1.0, show the last row
                if progress_through_line >= 1.0:
                    row_index = total_rows - 1
                else:
                    # Each row gets 1/total_rows of the duration
                    # int() truncates, so we get: [0, 1/3) -> 0, [1/3, 2/3) -> 1, [2/3, 1.0) -> 2
                    row_index = int(progress_through_line * total_rows)
                    # Clamp to valid range (shouldn't be needed, but safety check)
                    row_index = min(row_index, total_rows - 1)
                row_to_show = rows[row_index]
                
                # Limit by available vertical space (below art, above progress bar)
                available_space = 63 - self.LYRICS_START_Y
                max_visible_rows = max(1, available_space // self.LYRICS_LINE_HEIGHT)
                
                # Draw the current row (centered vertically in available space if we have room)
                if row_to_show.strip():
                    y_pos = self.LYRICS_START_Y
                    
                    # Make sure we don't draw over the progress bar
                    if y_pos < 63:
                        # Center the text horizontally
                        text_width_actual = self.font.getlength(row_to_show)
                        x = max(0, (self.CANVAS_WIDTH - text_width_actual) // 2)
                        draw.text((x, y_pos), row_to_show, fill=self.TITLE_COLOR, font=self.font)

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
            draw.rectangle((0, line_y - 1, progress_width, line_y), fill=self.current_prominent_color)


    def _draw_play_pause_indicator(self, draw: ImageDraw.Draw, is_playing: bool):
        """Draw play/pause indicator icon."""
        x, y = 55, 3
        
        if is_playing:
            # Pause icon (two vertical bars) when playing
            draw.line([(x, y), (x, y + 6)], fill=self.current_prominent_color, width=2)
            draw.line([(x + 3, y), (x + 3, y + 6)], fill=self.current_prominent_color, width=2)
        else:
            # Play icon (triangle) when paused
            draw.polygon([(x, y), (x, y + 6), (x + 4, y + 3)], fill=self.current_prominent_color)
    

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