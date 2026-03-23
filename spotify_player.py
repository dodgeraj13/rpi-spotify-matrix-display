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
            if 0 < self._last_prog_ms - progress_ms < 3000:
                progress_ms = self._last_prog_ms
        self._last_prog_ms = progress_ms
        self._last_track_prog = response.track_id

        if self.current_title != response.title or self.current_artist != response.artist:
            self.current_artist, self.current_title = response.artist, response.title
            self.scroll.update_limits(response.title, response.artist, W - 18)
        
        self._request_art(response.art_url)

        is_paused_long = not response.is_playing and (now - self.last_playing_time > 10.0)

        if self.always_fullscreen or is_paused_long:
            target_frame = self._generate_fullscreen_frame(response.art_url)
        else:
            target_frame = self._generate_normal_frame(response, progress_ms, duration_ms, now, dt)

        if self.transition.active:
            return self.transition.generate_frame(target_frame, dt)
        return target_frame

    def _generate_fullscreen_frame(self, target_url: str) -> Image.Image:
        img = Image.new("RGB", (W, H), (0, 0, 0))
        art = self.art_cache.get(target_url, 64)
        if art: img.paste(art, (0, 0))
        return img

    def _has_current_lyrics(self, response, progress_ms):
        if not response.lyrics or response.lyrics.get('lyrics', {}).get('syncType') != 'LINE_SYNCED':
            return False
        text = None
        for line in response.lyrics['lyrics']['lines']:
            if int(line['startTimeMs']) <= progress_ms:
                text = line['words'].strip()
            else: break
        return bool(text and text != "♪")

    def _update_lyrics_state(self, response, progress_ms, now, dt):
        has_lyrics = self._has_current_lyrics(response, progress_ms)
        prev_frames = self.lyrics_frames
        
        frames_to_add = dt * self.target_fps
        
        if has_lyrics and response.is_playing and not self.transition.active and (now - self.transition.finish_time > 0.4):
            if self.lyrics_frames < self.max_lyrics_frames:
                self.lyrics_frames = min(self.max_lyrics_frames, self.lyrics_frames + frames_to_add)
        elif self.lyrics_frames > 0:
            self.lyrics_frames = max(0.0, self.lyrics_frames - frames_to_add)

        if self.lyrics_frames > prev_frames: self.lyrics_active = True
        elif self.lyrics_frames < prev_frames: self.lyrics_active = False
        if self.lyrics_frames == 0: self.lyrics_active = False

        return has_lyrics

    def _generate_normal_frame(self, response: PlaybackInfo, progress_ms: int, duration_ms: int, now: float, dt: float) -> Image.Image:
        img = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        has_lyrics_now = self._update_lyrics_state(response, progress_ms, now, dt)
        t_total = self.lyrics_frames / self.max_lyrics_frames
        art_t = min(1.0, self.lyrics_frames / 16.0)
        
        text_x = int(1 + (16 * art_t))
        btn_start_x = W + 3
        
        if self.lyrics_active:
            btn_x = int(56 + (btn_start_x - 56) * (1.0 - t_total))
            btn_y = 54
            text_width = btn_x - 3 - text_x - 1
        else:
            btn_x, btn_y = 55, 3
            text_width = 52 - text_x - 1
            
        box_left, box_right = btn_x - 3, btn_x + 9
        box_top, box_bottom = btn_y - 3, btn_y + 9

        title_pos, artist_pos = self.scroll.update(art_t, now)
        
        self._draw_text(draw, self.current_title, text_x, 1, text_width, title_pos)
        self._draw_text(draw, self.current_artist, text_x, 7, text_width, artist_pos)

        if art_t < 0.5:
            bar_y = 62 + int(art_t * 4)
            if bar_y < 64:
                self._draw_progress_bar(draw, progress_ms, duration_ms, 0, bar_y, W)

        bar_width = W - text_x - 1 if t_total > 0 else text_width
        if self.lyrics_frames > 16:
            green_w = round(bar_width * progress_ms / duration_ms) if duration_ms > 0 else 0
            if self.lyrics_frames <= 22:
                green_w = int(green_w * ((self.lyrics_frames - 16) / 6.0))
                if green_w > 0: draw.rectangle((text_x, 14, text_x + green_w - 1, 15), fill=GREEN)
            else:
                grey = int(100 * ((self.lyrics_frames - 22) / 6.0))
                draw.rectangle((text_x, 14, text_x + bar_width - 1, 15), fill=(grey, grey, grey))
                if green_w > 0: draw.rectangle((text_x, 14, text_x + green_w - 1, 15), fill=GREEN)
        elif t_total == 1.0:
            self._draw_progress_bar(draw, progress_ms, duration_ms, text_x, 14, bar_width)

        if box_left < W and t_total == 0:
            draw.rectangle((box_left, box_top, box_right, box_bottom), fill=(0, 0, 0))

        if art_t > 0.5: draw.rectangle((0, 0, text_x - 1, 16), fill=(0, 0, 0))
        draw.rectangle((W - 1, 0, W - 1, 16), fill=(0, 0, 0))

        art_size = int(48 - (33 * art_t))
        art = self.art_cache.get(response.art_url, art_size)
        if art:
            img.paste(art, (int(8 - (7 * art_t)), int(14 - (13 * art_t))))

        if self.lyrics_frames >= 23 and has_lyrics_now:
            c = int(255 * min(1.0, (self.lyrics_frames - 22) / 6.0))
            self._draw_lyrics(draw, response.lyrics, progress_ms, 18, (c, c, c))

        if box_left < W and btn_x < W:
            freeze = False
            if response.is_playing and (now - self.play_show_time < 2.0): freeze = True
            if not self.transition.active and (now - self.transition.finish_time < 2.0): freeze = True
            pad = 1 if t_total > 0 else 0
            draw.rectangle((box_left - pad, box_top - pad, box_right + pad, box_bottom + pad), fill=(0, 0, 0))
            self._draw_play_pause(draw, btn_x, btn_y, response.is_playing, freeze)

        return img

    def _draw_text(self, draw, text, x, y, width, pos):
        if not text: return
        if self.font.getlength(text) > width:
            draw.text((x - pos, y), text + "     " + text, WHITE, font=self.font)
        else:
            draw.text((x, y), text, WHITE, font=self.font)

    def _draw_progress_bar(self, draw, progress_ms, duration_ms, x, y, width):
        draw.rectangle((x, y, x + width - 1, y + 1), fill=(100, 100, 100))
        if duration_ms > 0:
            w = round(width * progress_ms / duration_ms)
            if w > 0: draw.rectangle((x, y, x + min(w, width) - 1, y + 1), fill=GREEN)

    def _draw_play_pause(self, draw, x, y, is_playing, freeze):
        if not is_playing:
            draw.rectangle((x, y, x + 1, y + 6), fill=GREEN)
            draw.rectangle((x + 3, y, x + 4, y + 6), fill=GREEN)
        elif freeze:
            draw.polygon([(x, y), (x, y + 6), (x + 4, y + 3)], fill=GREEN)
        else:
            t = time.time()
            for i in range(3):
                h = 1.0 + 2.5 * (0.5 + 0.5 * math.sin(t * (12 + i * 3) + i * 2))
                t_y = max(y, int(y + 3 - h))
                b_y = min(y + 6, int(y + 3 + h))
                draw.rectangle((x + i * 2, t_y, x + i * 2, b_y), fill=GREEN)

    def _draw_lyrics(self, draw, lyrics, progress_ms, y_offset, fill):
        text = None
        for line in lyrics['lyrics']['lines']:
            if int(line['startTimeMs']) <= progress_ms: text = line['words'].strip()
            else: break
        if not text or text == "♪": return

        words = text.split()
        out, cur = [], ""
        for word in words:
            if self.font.getlength(f"{cur} {word}".strip()) <= W - 4:
                cur = f"{cur} {word}".strip()
            else:
                if cur: out.append(cur)
                cur, rem = "", word
                while rem:
                    if self.font.getlength(rem) <= W - 4:
                        cur = rem
                        break
                    
                    found = False
                    for i in range(len(rem) - 1, 0, -1):
                        if rem[i] == '-' and self.font.getlength(rem[:i+1]) <= W - 4:
                            out.append(rem[:i+1])
                            rem, found = rem[i+1:], True
                            break
                    if found: continue
                    
                    for i in range(len(rem) - 1, 0, -1):
                        if self.font.getlength(rem[:i] + "-") <= W - 4:
                            out.append(rem[:i] + "-")
                            rem, found = rem[i:], True
                            break
                    if not found:
                        out.append(rem[0])
                        rem = rem[1:]
        if cur: out.append(cur)

        for i, line in enumerate(out):
            y = y_offset + i * 6
            if y + 6 > H: break
            draw.text((2, y), line, fill=fill, font=self.font)
