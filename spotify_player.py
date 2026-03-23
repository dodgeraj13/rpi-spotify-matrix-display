#!/usr/bin/env python3
"""Spotify track display for the LED matrix."""
import math
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Optional

import requests
from PIL import Image, ImageDraw, ImageFont

from spotify_module import SpotifyModule, PlaybackInfo

W, H = 64, 64
WHITE = (255, 255, 255)
GREEN = (102, 240, 110)

from components import ArtCache, ScrollManager, TransitionManager
from player_fullscreen import PlayerFullscreen
from player_standard import PlayerStandard
from player_lyrics import PlayerLyrics

class SpotifyPlayer:
    def __init__(self, config, spotify_module: SpotifyModule):
        self.spotify_module = spotify_module
        self.always_fullscreen = config.getboolean('Matrix', 'always_fullscreen', fallback=False)
        self.fetch_interval = int(config.get('Matrix', 'fetch_interval', fallback='1'))
        self.shutdown_delay = int(config.get('Matrix', 'shutdown_delay', fallback='600'))
        self.scroll_delay = int(config.get('Matrix', 'scroll_delay', fallback='4'))
        self.target_fps = config.getint('Matrix', 'target_fps', fallback=60)

        for p in [Path("font.otf"), Path(__file__).parent / "font.otf"]:
            if p.exists():
                self.font = ImageFont.truetype(str(p), 5)
                break
        else:
            self.font = ImageFont.load_default()

        self.black_screen = Image.new("RGB", (W, H), (0, 0, 0))
        self.art_cache = ArtCache()
        self.scroll = ScrollManager(self.font, self.scroll_delay)
        self.transition = TransitionManager(self.target_fps)
        self.player_fullscreen = PlayerFullscreen(self.font, self.art_cache)
        self.player_standard = PlayerStandard(self.font, self.art_cache)
        self.player_lyrics = PlayerLyrics(self.font, self.art_cache)

        self.current_title = ''
        self.current_artist = ''
        self.current_track_id = None
        self.is_playing = None
        self.last_active_time = time.time()
        self.last_playing_time = time.time()
        
        self.response = None
        self.response_timestamp = 0.0
        self.response_progress_ms = 0
        self.pending_response = None
        
        self.last_generated_frame = None
        self.lyrics_frames = 0
        self.max_lyrics_frames = 28
        self.lyrics_active = False
        
        self.last_is_playing = None
        self.play_show_time = 0.0
        
        self._last_prog_ms = 0
        self._last_track_prog = None

        threading.Thread(target=self._fetch_loop, daemon=True).start()

    def _fetch_loop(self):
        time.sleep(3)
        while True:
            start_time = time.time()
            try:
                self.spotify_module.get_current_playback()
            except Exception as e:
                print(f"Error fetching Spotify data: {e}")
            finally:
                elapsed = time.time() - start_time
                time.sleep(max(0.0, self.fetch_interval - elapsed))

    def generate(self, dt: float):
        now = time.time()
        self._process_queue(now)
        
        if self.pending_response and not self.art_cache.is_fetching:
            self.response = self.pending_response
            self.response_timestamp = now
            self.response_progress_ms = self.response.progress_ms
            self.pending_response = None

        frame = self._generate_frame(self.response, now, dt)
        self.last_generated_frame = frame
        return frame

    def _process_queue(self, now):
        if not self.spotify_module.queue.empty():
            new_data = self.spotify_module.queue.get()
            with self.spotify_module.queue.mutex:
                self.spotify_module.queue.queue.clear()
            
            if new_data:
                if self.response is None or (self.response.track_id and new_data.track_id != self.response.track_id):
                    self.pending_response = new_data
                    self._request_art(new_data.art_url)
                else:
                    self.response = new_data
                    self.response_timestamp = now
                    self.response_progress_ms = self.response.progress_ms
                    self.pending_response = None

    def _request_art(self, art_url):
        if not art_url: return
        safe = [art_url]
        if self.response and self.response.art_url: safe.append(self.response.art_url)
        if self.pending_response and self.pending_response.art_url: safe.append(self.pending_response.art_url)
        self.art_cache.fetch(art_url, safe)

    def _generate_frame(self, response: Optional[PlaybackInfo], now: float, dt: float) -> Optional[Image.Image]:
        if not response: return self.black_screen

        if response.is_playing != self.last_is_playing:
            self.play_show_time = now
        self.last_is_playing = response.is_playing
        self.is_playing = response.is_playing
        
        if response.is_playing:
            self.last_active_time = math.floor(now)
            self.last_playing_time = now
        elif math.floor(now) - self.last_active_time > self.shutdown_delay:
            return self.black_screen

        if response.track_id and response.track_id != self.current_track_id:
            self.transition.start(response.track_id, self.current_track_id, self.last_generated_frame, self.black_screen)
            self.current_track_id = response.track_id
            self.transition.update_history(response.track_id)
            self.lyrics_frames = 0

        progress_ms = response.progress_ms
        if self.response_timestamp > 0 and response.is_playing:
            progress_ms += int((now - self.response_timestamp) * 1000)

        duration_ms = response.duration_ms
        if duration_ms > 0: progress_ms = min(progress_ms, duration_ms)

        # Prevent small backward jumps in progress to avoid lyric animation glitches
        if hasattr(self, '_last_prog_ms') and getattr(self, '_last_track_prog', None) == response.track_id:
            diff = self._last_prog_ms - progress_ms
            if 0 < diff < 3000:
                progress_ms = self._last_prog_ms
            elif diff >= 3000:
                self.play_show_time = now
        self._last_prog_ms = progress_ms
        self._last_track_prog = response.track_id

        if self.current_title != response.title or self.current_artist != response.artist:
            self.current_artist, self.current_title = response.artist, response.title
            self.scroll.update_limits(response.title, response.artist, W - 18)
        
        self._request_art(response.art_url)

        is_paused_long = not response.is_playing and (now - self.last_playing_time > 10.0)

        if self.always_fullscreen or is_paused_long:
            target_frame = self.player_fullscreen.generate(response)
        else:
            target_frame = self._generate_normal_frame(response, progress_ms, duration_ms, now, dt)

        if self.transition.active:
            return self.transition.generate_frame(target_frame, dt)
        return target_frame

    def _has_current_lyrics(self, response, progress_ms):
        if not response.lyrics or response.lyrics.get('lyrics', {}).get('syncType') != 'LINE_SYNCED':
            return False
            
        lines = response.lyrics['lyrics']['lines']
        current_line = None
        current_idx: int = -1
        
        for i, line in enumerate(lines):
            if int(line['startTimeMs']) <= progress_ms:
                current_line = line
                current_idx = int(i)
            else: break
            
        if not current_line:
            # Before the first lyric line
            next_lyric_ms = None
            for line in lines:
                l_text = line['words'].strip()
                if l_text and l_text != "♪":
                    next_lyric_ms = int(line['startTimeMs'])
                    break
            if next_lyric_ms is not None and next_lyric_ms - progress_ms <= 1500:
                return True
            return False
            
        text = current_line['words'].strip()
        if text and text != "♪":
            return True
            
        # We are on a pause line (empty or "♪"). Check how long this pause is.
        next_lyric_ms = None
        for j in range(int(current_idx) + 1, len(lines)):
            l_text = lines[j]['words'].strip()
            if l_text and l_text != "♪":
                next_lyric_ms = int(lines[j]['startTimeMs'])
                break
                
        if next_lyric_ms is not None:
            n_lyric_ms: int = next_lyric_ms or 0
            pause_start_ms = int(current_line['startTimeMs'])
            # If the pause is short (<= 5 seconds), don't collapse lyrics mode
            if n_lyric_ms - pause_start_ms <= 5000:
                return True
            # For longer pauses, start expanding earlier so it's ready when vocals hit
            if n_lyric_ms - progress_ms <= 1500:
                return True
                
        return False

    def _update_lyrics_state(self, response, progress_ms, now, dt):
        has_lyrics = self._has_current_lyrics(response, progress_ms)
        prev_frames = self.lyrics_frames
        
        frames_to_add = dt * self.target_fps
        
        can_show = True
        if self.transition.active or (now - self.transition.finish_time < 0.4): can_show = False
        if now - self.play_show_time < 2.0: can_show = False
        
        if has_lyrics and response.is_playing and can_show:
            if self.lyrics_frames < self.max_lyrics_frames:
                self.lyrics_frames = min(self.max_lyrics_frames, self.lyrics_frames + frames_to_add)
        elif self.lyrics_frames > 0:
            self.lyrics_frames = max(0.0, self.lyrics_frames - frames_to_add)

        if self.lyrics_frames > prev_frames: self.lyrics_active = True
        elif self.lyrics_frames < prev_frames: self.lyrics_active = False
        if self.lyrics_frames == 0: self.lyrics_active = False

        return has_lyrics

    def _generate_normal_frame(self, response: PlaybackInfo, progress_ms: int, duration_ms: int, now: float, dt: float) -> Image.Image:
        has_lyrics_now = self._update_lyrics_state(response, progress_ms, now, dt)
        
        art_t = min(1.0, self.lyrics_frames / 16.0)
        title_pos, artist_pos = self.scroll.update(art_t, now)

        freeze = False
        if response.is_playing and (now - self.play_show_time < 2.0): freeze = True
        if not self.transition.active and (now - self.transition.finish_time < 2.0): freeze = True
        if self.lyrics_frames > 0: freeze = False

        if self.lyrics_frames > 0:
            return self.player_lyrics.generate(
                response, progress_ms, duration_ms, title_pos, artist_pos, 
                self.current_title, self.current_artist, freeze, 
                self.lyrics_frames, self.max_lyrics_frames, has_lyrics_now
            )
        else:
            return self.player_standard.generate(
                response, progress_ms, duration_ms, title_pos, artist_pos, 
                self.current_title, self.current_artist, freeze
            )
