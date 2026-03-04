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


class SpotifyPlayer:

    def __init__(self, config, spotify_module: SpotifyModule):
        self.spotify_module = spotify_module
        self.always_fullscreen = config.getboolean('Matrix', 'always_fullscreen', fallback=False)
        self.fetch_interval = int(config.get('Matrix', 'fetch_interval', fallback='1'))
        self.scroll_delay = int(config.get('Matrix', 'scroll_delay', fallback='4'))
        self.shutdown_delay = int(config.get('Matrix', 'shutdown_delay', fallback='600'))

        for p in [Path("font.otf"), Path(__file__).parent / "font.otf"]:
            if p.exists():
                self.font = ImageFont.truetype(str(p), 5)
                break
        else:
            self.font = ImageFont.load_default()

        self.current_art_url = ''
        self.current_art_img: Optional[Image.Image] = None
        self.current_title = ''
        self.current_artist = ''
        self.title_animation_cnt = 0
        self.artist_animation_cnt = 0
        self.last_title_reset = self.last_artist_reset = math.floor(time.time())
        self.is_playing = None
        self.playback_start_time = 0.0
        self.last_active_time = math.floor(time.time())
        self.response: Optional[PlaybackInfo] = None
        self.response_timestamp = 0.0
        self.response_progress_ms = 0
        self.black_screen = Image.new("RGB", (W, H), (0, 0, 0))
        
        self.track_history = []
        self.current_track_id = None
        self.slide_active = False
        self.slide_frames = 0
        self.total_slide_frames = 16 
        self.slide_direction = 1
        self.prev_frame_snapshot: Optional[Image.Image] = None
        self.last_generated_frame: Optional[Image.Image] = None

        threading.Thread(target=self._fetch_loop, daemon=True).start()

    def _fetch_loop(self):
        time.sleep(3)
        while True:
            try:
                self.spotify_module.get_current_playback()
                time.sleep(self.fetch_interval)
            except Exception as e:
                print(f"Error fetching Spotify data: {e}")
                time.sleep(self.fetch_interval)

    def generate(self) -> Optional[Image.Image]:
        if not self.spotify_module.queue.empty():
            self.response = self.spotify_module.queue.get()
            with self.spotify_module.queue.mutex:
                self.spotify_module.queue.queue.clear()
            if self.response:
                self.response_timestamp = time.time()
                self.response_progress_ms = self.response.progress_ms

        frame = self._generate_frame(self.response)
        self.last_generated_frame = frame
        return frame

    def _generate_frame(self, response: Optional[PlaybackInfo]) -> Optional[Image.Image]:
        if not response:
            return self.black_screen

        if response.is_playing:
            if self.is_playing is False:
                self.playback_start_time = time.time()
            self.last_active_time = math.floor(time.time())
        self.is_playing = response.is_playing
        
        if not response.is_playing:
            if math.floor(time.time()) - self.last_active_time > self.shutdown_delay:
                return self.black_screen

        if response.track_id and response.track_id != self.current_track_id:
            self._handle_track_change(response.track_id)

        progress_ms = response.progress_ms
        if self.response_timestamp > 0 and response.is_playing:
            elapsed = int((time.time() - self.response_timestamp) * 1000)
            progress_ms += elapsed

        duration_ms = response.duration_ms
        if duration_ms > 0:
            progress_ms = min(progress_ms, duration_ms)

        self._update_track(response.artist, response.title)
        self._update_art(response.art_url)

        target_frame = None
        if self.always_fullscreen:
            target_frame = self._generate_fullscreen_frame(progress_ms, duration_ms)
        else:
            target_frame = self._generate_normal_frame(response, progress_ms, duration_ms)

        if self.slide_active:
            return self._generate_slide_transition(target_frame)
        
        return target_frame

    def _handle_track_change(self, new_track_id: str):
        if self.current_track_id is not None:
            self.slide_active = True
            self.slide_frames = 0
            self.prev_frame_snapshot = self.last_generated_frame or self.black_screen.copy()
            
            self.slide_direction = 1
            if new_track_id in self.track_history:
                 try:
                     old_i = self.track_history.index(self.current_track_id) if self.current_track_id in self.track_history else -1
                     new_i = self.track_history.index(new_track_id)
                     if old_i != -1 and new_i < old_i:
                         self.slide_direction = -1
                 except ValueError:
                     pass
        
        self.current_track_id = new_track_id
        if new_track_id not in self.track_history:
            self.track_history.append(new_track_id)
            if len(self.track_history) > 20:
                self.track_history.pop(0)

    def _generate_slide_transition(self, target_frame: Image.Image) -> Image.Image:
        progress = self.slide_frames / self.total_slide_frames
        offset = int(W * progress)
        
        composite = Image.new("RGB", (W, H), (0, 0, 0))
        
        if self.slide_direction == 1:
            composite.paste(self.prev_frame_snapshot, (-offset, 0))
            composite.paste(target_frame, (W - offset, 0))
        else:
            composite.paste(self.prev_frame_snapshot, (offset, 0))
            composite.paste(target_frame, (-W + offset, 0))

        self.slide_frames += 1
        if self.slide_frames >= self.total_slide_frames:
            self.slide_active = False
            
        return composite

    def _generate_fullscreen_frame(self, progress_ms: int, duration_ms: int) -> Image.Image:
        img = Image.new("RGB", (W, H), (0, 0, 0))

        if self.current_art_img:
            if self.current_art_img.size != (64, 64):
                img.paste(self.current_art_img.resize((64, 64), Image.LANCZOS), (0, 0))
            else:
                img.paste(self.current_art_img, (0, 0))

        draw = ImageDraw.Draw(img)
        self._draw_progress_bar(draw, progress_ms, duration_ms)

        return img

    def _generate_normal_frame(self, response: PlaybackInfo, progress_ms: int, duration_ms: int) -> Image.Image:
        img = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        show_button = not response.is_playing or time.time() - self.playback_start_time < 3.0
        text_width = W - 12 if show_button else W - 2

        self._draw_text(draw, self.current_title, 1, 1, text_width, is_title=True)
        self._draw_text(draw, self.current_artist, 1, 7, text_width, is_title=False)

        if show_button:
            draw.rectangle((text_width, 0, W - 1, 12), fill=(0, 0, 0))
            self._draw_play_pause(draw, W - 9, 3, is_playing=response.is_playing)

        if self.current_art_img:
            if self.current_art_img.size != (48, 48):
                 img.paste(self.current_art_img.resize((48, 48), Image.LANCZOS), (8, 14))
            else:
                 img.paste(self.current_art_img, (8, 14))

        if response.is_playing and response.lyrics and response.lyrics.get('lyrics', {}).get('lines'):
            self._draw_lyrics(img, draw, response.lyrics, progress_ms)

        self._draw_progress_bar(draw, progress_ms, duration_ms)

        return img

    def _update_track(self, artist: str, title: str):
        if self.current_title != title or self.current_artist != artist:
            self.current_artist = artist
            self.current_title = title
            self.title_animation_cnt = 0
            self.artist_animation_cnt = 0
            self.last_title_reset = self.last_artist_reset = math.floor(time.time())

    def _update_art(self, art_url: str):
        if self.current_art_url != art_url:
            self.current_art_url = art_url
            self.current_art_img = self._fetch_image(art_url)

    def _fetch_image(self, url: str) -> Optional[Image.Image]:
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content)).convert("RGB")
            return img
        except Exception as e:
            print(f"Error fetching image {url}: {e}")
            return None

    def _draw_text(self, draw: ImageDraw.Draw, text: str, x: int, y: int, width: int, is_title: bool):
        text = text or ("Unknown Title" if is_title else "Unknown Artist")
        spacer = "     "

        pixel_width = self.font.getlength(text)

        if pixel_width > width:
            animation_cnt = self.title_animation_cnt if is_title else self.artist_animation_cnt
            draw.text((x - animation_cnt, y), text + spacer + text, WHITE, font=self.font)

            t = math.floor(time.time())
            last_reset = self.last_title_reset if is_title else self.last_artist_reset

            if t - last_reset >= self.scroll_delay:
                if is_title:
                    self.title_animation_cnt += 1
                else:
                    self.artist_animation_cnt += 1

            if animation_cnt >= self.font.getlength(text + spacer):
                if is_title:
                    self.title_animation_cnt = 0
                    self.last_title_reset = t
                else:
                    self.artist_animation_cnt = 0
                    self.last_artist_reset = t
        else:
            draw.text((x, y), text, WHITE, font=self.font)

    def _draw_progress_bar(self, draw: ImageDraw.Draw, progress_ms: int, duration_ms: int):
        draw.rectangle((0, 62, 63, 63), fill=(100, 100, 100))
        if duration_ms > 0:
            w = round(64 * progress_ms / duration_ms)
            draw.rectangle((0, 62, min(w, 63), 63), fill=GREEN)

    def _draw_play_pause(self, draw: ImageDraw.Draw, x: int, y: int, is_playing: bool):
        if not is_playing:
            draw.line([(x, y), (x, y + 6)], fill=GREEN, width=2)
            draw.line([(x + 3, y), (x + 3, y + 6)], fill=GREEN, width=2)
        elif time.time() - self.playback_start_time < 3.0:
            draw.polygon([(x, y), (x, y + 6), (x + 4, y + 3)], fill=GREEN)

    def _draw_lyrics(self, frame: Image.Image, draw: ImageDraw.Draw, lyrics: dict, progress_ms: int):
        lines = lyrics['lyrics']['lines']
        current_line = None
        for line in lines:
            if int(line['startTimeMs']) <= progress_ms:
                w = line['words'].strip()
                if w:
                    current_line = w
            else:
                break

        if not current_line or current_line == "♪":
            return

        max_w = W - 6
        words = current_line.split()
        out, cur, max_lines = [], "", 7
        for i, word in enumerate(words):
            test = f"{cur} {word}".strip() if cur else word
            if self.font.getlength(test) <= max_w:
                cur = test
            else:
                if cur:
                    out.append(cur)
                cur = word
                if len(out) >= max_lines - 1 and i < len(words) - 1:
                    while cur and self.font.getlength(cur + "..") > max_w:
                        cur = cur.rsplit(" ", 1)[0]
                    cur = (cur + "..").strip() if cur else ""
                    break
        if cur:
            out.append(cur)

        line_h, total = 6, len(out) * 6
        y0 = 14 + (48 - total) // 2
        overlay = Image.new("RGBA", (64, 48), (0, 0, 0, 150))
        frame.paste(overlay, (0, 14), overlay)

        for i, line in enumerate(out):
            x = (W - self.font.getlength(line)) // 2
            draw.text((x, y0 + i * line_h), line, fill=WHITE, font=self.font)
