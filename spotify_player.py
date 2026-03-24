#!/usr/bin/env python3
"""Spotify track display for the LED matrix."""
import math
import threading
import time
from pathlib import Path
from typing import Optional

from PIL import Image, ImageFont
from spotify_module import SpotifyModule, PlaybackInfo

W, H = 64, 64

from components import ArtCache, ProgressBar, ScrollingText, AlbumArt, PlayIndicator
from transitions.player_transition import PlayerTransition
from players.player_fullscreen import PlayerFullscreen
from players.player_standard import PlayerStandard
from players.player_lyrics import PlayerLyrics

class ComponentsBox:
    pass

class SpotifyPlayer:
    def __init__(self, config, spotify_module: SpotifyModule):
        self.spotify_module = spotify_module
        self.always_fullscreen = config.getboolean('Matrix', 'always_fullscreen', fallback=False)
        self.fetch_interval = int(config.get('Matrix', 'fetch_interval', fallback='1'))
        self.shutdown_delay = int(config.get('Matrix', 'shutdown_delay', fallback='600'))
        self.scroll_delay = int(config.get('Matrix', 'scroll_delay', fallback='4'))
        self.scroll_speed = float(config.get('Matrix', 'scroll_speed', fallback='15.0'))
        self.target_fps = config.getint('Matrix', 'target_fps', fallback=60)

        for p in [Path("font.otf"), Path(__file__).parent / "font.otf"]:
            if p.exists():
                self.font = ImageFont.truetype(str(p), 5)
                break
        else:
            self.font = ImageFont.load_default()

        self.black_screen = Image.new("RGB", (W, H), (0, 0, 0))
        self.art_cache = ArtCache()
        self.player_transition = PlayerTransition(self.target_fps)

        self.progress_bar = ProgressBar(0, 62, 64, 2)
        self.title_scroll = ScrollingText(1, 1, 52, 6, self.scroll_speed, self.scroll_delay, self.font)
        self.artist_scroll = ScrollingText(1, 7, 52, 6, self.scroll_speed, self.scroll_delay, self.font)
        self.title_scroll.add_sync(self.artist_scroll)
        self.album_art = AlbumArt(8, 14, 48, 48, self.art_cache)
        self.play_indicator = PlayIndicator(56, 3, 5, 7)

        self.components = ComponentsBox()
        self.components.progress_bar = self.progress_bar
        self.components.title_scroll = self.title_scroll
        self.components.artist_scroll = self.artist_scroll
        self.components.album_art = self.album_art
        self.components.play_indicator = self.play_indicator

        self.current_track_id = None
        self.is_playing = None
        self.last_active_time = time.time()
        self.last_playing_time = time.time()
        
        self.response = None
        self.response_timestamp = 0.0
        self.response_progress_ms = 0
        self.pending_response = None
        
        self.last_generated_frame = None
        self.last_is_playing = None
        self.play_show_time = 0.0
        
        self._last_prog_ms = 0
        self._last_track_prog = None
        
        self.lyrics_transition_start = 0.0
        self.was_showing_lyrics = False

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
            self.player_transition.start(response.track_id, self.current_track_id, self.last_generated_frame, self.black_screen)
            self.current_track_id = response.track_id
            self.player_transition.update_history(response.track_id)
            self.was_showing_lyrics = False
            self.lyrics_transition_start = 0.0

        progress_ms = response.progress_ms
        if self.response_timestamp > 0 and response.is_playing:
            progress_ms += int((now - self.response_timestamp) * 1000)

        duration_ms = response.duration_ms
        if duration_ms > 0: progress_ms = min(progress_ms, duration_ms)

        if getattr(self, '_last_track_prog', None) == response.track_id:
            diff = self._last_prog_ms - progress_ms
            if 0 < diff < 3000:
                progress_ms = self._last_prog_ms
            elif diff >= 3000 and progress_ms < 3000:
                self.play_show_time = now
        self._last_prog_ms = progress_ms
        self._last_track_prog = response.track_id
        
        self.components.title_scroll.update_text(response.title)
        self.components.artist_scroll.update_text(response.artist)
        self._request_art(response.art_url)

        target_frame = self._generate_appearance(response, progress_ms, duration_ms, now)

        if self.player_transition.active:
            return self.player_transition.generate_frame(target_frame, dt)
        return target_frame

    def _has_current_lyrics(self, response, progress_ms):
        if not response.lyrics or response.lyrics.get('lyrics', {}).get('syncType') != 'LINE_SYNCED':
            return False
            
        anim_time_ms = 466
        lines = response.lyrics['lyrics']['lines']
        current_line = None
        current_idx = -1
        
        for i, line in enumerate(lines):
            if int(line['startTimeMs']) <= progress_ms:
                current_line = line
                current_idx = i
            else: break
            
        if not current_line:
            next_lyric_ms = next((int(l['startTimeMs']) for l in lines if l['words'].strip() and l['words'].strip() != "♪"), None)
            return next_lyric_ms is not None and next_lyric_ms - progress_ms <= anim_time_ms
            
        text = current_line['words'].strip()
        if text and text != "♪": return True
            
        next_lyric_ms = next((int(lines[j]['startTimeMs']) for j in range(current_idx + 1, len(lines)) if lines[j]['words'].strip() and lines[j]['words'].strip() != "♪"), None)
                
        if next_lyric_ms is not None:
            pause_start_ms = int(current_line['startTimeMs'])
            if next_lyric_ms - pause_start_ms <= 5000: return True
            if next_lyric_ms - progress_ms <= anim_time_ms: return True
                
        return False

    def _generate_appearance(self, response, progress_ms, duration_ms, now):
        self.components.title_scroll.update(now)
        self.components.artist_scroll.update(now)

        show_play = False
        if response.is_playing and (now - self.play_show_time < 2.0): show_play = True
        if not self.player_transition.active and (now - self.player_transition.finish_time < 2.0): show_play = True

        time_paused_ms = 0 if response.is_playing else int((now - self.last_playing_time) * 1000)
        time_playing_ms = int((now - max(self.play_show_time, self.player_transition.finish_time)) * 1000)

        showing_lyric = self._has_current_lyrics(response, progress_ms)
        can_show_lyrics = time_playing_ms > 2000 and response.is_playing and showing_lyric and not self.player_transition.active
        
        if can_show_lyrics and not self.was_showing_lyrics:
            self.lyrics_transition_start = now
        elif not can_show_lyrics and self.was_showing_lyrics:
            self.lyrics_transition_start = now
        
        self.was_showing_lyrics = can_show_lyrics
            
        lyric_transition_time = now - self.lyrics_transition_start
        max_lyrics_frames = 42
        fps = float(self.target_fps)

        if can_show_lyrics:
            lyrics_frames = min(max_lyrics_frames, lyric_transition_time * fps)
        else:
            lyrics_frames = max(0.0, max_lyrics_frames - (lyric_transition_time * fps))

        pause_delay = 10000
        lyrics_delay = 2000

        if can_show_lyrics and lyrics_frames < max_lyrics_frames * 0.5:
            t = self.lyrics_transition_start
            show_play = response.is_playing and ((t - self.play_show_time < 2.1) or \
                        (not self.player_transition.active and t - self.player_transition.finish_time < 2.1))

        if self.always_fullscreen or time_paused_ms > pause_delay:
            return PlayerFullscreen.generate(response, self.components)
        elif lyrics_frames > 0:
            return PlayerLyrics.generate(
                response, progress_ms, duration_ms, show_play, self.components,
                lyrics_frames, max_lyrics_frames, showing_lyric
            )
        
        return PlayerStandard.generate(response, progress_ms, duration_ms, show_play, self.components)

