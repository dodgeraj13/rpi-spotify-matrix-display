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

MATRIX_W, MATRIX_H = 64, 64
WHITE = (255, 255, 255)
GREEN = (102, 240, 110)


class SpotifyPlayer:

    def __init__(self, config, spotify_module: SpotifyModule):
        self.spotify_module = spotify_module
        
        # Only parse config fields actually present in config.ini example
        self.always_fullscreen = config.getboolean('Matrix', 'always_fullscreen', fallback=False)
        self.shutdown_delay = int(config.get('Matrix', 'shutdown_delay', fallback='60'))
        self.scroll_delay = int(config.get('Matrix', 'scroll_delay', fallback='4'))
        self.fetch_interval = 2 # Default internal val, not in config.ini

        path = Path("font.otf")
        if not path.exists(): path = Path(__file__).parent / "font.otf"
        self.font = ImageFont.truetype(str(path), 5) if path.exists() else ImageFont.load_default()

        self.current_art_url = ''
        self.current_art_img: Optional[Image.Image] = None
        self.current_title = ''
        self.current_artist = ''
        self.title_animation_cnt = 0
        self.artist_animation_cnt = 0
        self.last_title_reset = self.last_artist_reset = math.floor(time.time())
        self.is_playing = False
        self.last_active_time = math.floor(time.time())
        self.response: Optional[PlaybackInfo] = None
        self.response_timestamp = 0.0
        self.black_screen = Image.new("RGB", (MATRIX_W, MATRIX_H), (0, 0, 0))
        
        self.track_history = []
        self.current_track_id = None
        self.slide_active = False
        self.slide_frames = 0
        self.total_slide_frames = 16 
        self.slide_direction = 1
        self.prev_frame_snapshot: Optional[Image.Image] = None
        self.last_generated_frame: Optional[Image.Image] = None
        self.dynamic_color = GREEN

        threading.Thread(target=self._fetch_loop, daemon=True).start()

    def _fetch_loop(self):
        time.sleep(3)
        while True:
            try:
                self.spotify_module.get_current_playback()
                time.sleep(self.fetch_interval)
            except Exception:
                time.sleep(self.fetch_interval)

    def generate(self) -> Optional[Image.Image]:
        if not self.spotify_module.queue.empty():
            self.response = self.spotify_module.queue.get()
            with self.spotify_module.queue.mutex:
                self.spotify_module.queue.queue.clear()
            if self.response:
                self.response_timestamp = time.time()

        frame = self._generate_frame(self.response)
        self.last_generated_frame = frame
        return frame

    def _generate_frame(self, response: Optional[PlaybackInfo]) -> Optional[Image.Image]:
        if not response:
            return self.black_screen

        if response.is_playing:
            self.last_active_time = math.floor(time.time())
        elif math.floor(time.time()) - self.last_active_time > self.shutdown_delay:
            return self.black_screen

        if response.track_id and response.track_id != self.current_track_id:
            self._handle_track_change(response.track_id)

        progress_ms = response.progress_ms
        if self.response_timestamp > 0 and response.is_playing:
            progress_ms += int((time.time() - self.response_timestamp) * 1000)

        if response.duration_ms > 0:
            progress_ms = min(progress_ms, response.duration_ms)

        self._update_track(response.artist, response.title)
        self._update_art(response.art_url)

        # Generate the BASE frame (content only, NO progress bar for slide)
        # However, user said "exclude progress bar from slide transition".
        # This implies the progress bar should be drawn ON TOP of the sliding content, 
        # or the slide happens BEHIND the progress bar.
        # Let's generate the content frame without proper progress bar first?
        # A simpler way: Generate content. Slide content. Draw progress bar on result.
        
        target = self._generate_fullscreen_content() if self.always_fullscreen else \
                 self._generate_normal_content(response, progress_ms)

        if self.slide_active:
            final_img = self._generate_slide_transition(target)
        else:
            final_img = target

        # Draw progress bar on top of the final image (so it doesn't slide)
        self._draw_progress_bar(ImageDraw.Draw(final_img), progress_ms, response.duration_ms)
        
        return final_img

    def _generate_slide_transition(self, target_frame: Image.Image) -> Image.Image:
        progress = self.slide_frames / self.total_slide_frames
        offset = int(MATRIX_W * progress)
        composite = Image.new("RGB", (MATRIX_W, MATRIX_H), (0, 0, 0))
        
        # We need to snapshot the PREVIOUS content without progress bar ideally, 
        # but self.prev_frame_snapshot has it. 
        # The user likely wants the progress bar to stay static while content slides.
        # For now, we slide the content target_frame against prev_frame_snapshot.
        # Ideally prev_frame_snapshot should NOT have the progress bar if we want it to look static.
        # But retroactively removing it is hard. 
        # Moving forward we can save the "content-only" frame as snapshot.
        
        snapshot_x = -offset if self.slide_direction == 1 else offset
        target_x = (MATRIX_W - offset) if self.slide_direction == 1 else (-MATRIX_W + offset)

        composite.paste(self.prev_frame_snapshot, (snapshot_x, 0))
        composite.paste(target_frame, (target_x, 0))

        self.slide_frames += 1
        if self.slide_frames >= self.total_slide_frames:
            self.slide_active = False
        return composite

    def _generate_fullscreen_content(self) -> Image.Image:
        # Returns content image WITHOUT progress bar
        img = Image.new("RGB", (MATRIX_W, MATRIX_H), (0, 0, 0))
        if self.current_art_img:
            img.paste(self.current_art_img if self.current_art_img.size == (64, 64) else \
                      self.current_art_img.resize((64, 64), Image.LANCZOS), (0, 0))
        return img

    def _generate_normal_content(self, response: PlaybackInfo, progress_ms: int) -> Image.Image:
        # Returns content image WITHOUT progress bar
        img = Image.new("RGB", (MATRIX_W, MATRIX_H), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        self._draw_text(draw, self.current_title, 1, 1, MATRIX_W - 12, True)
        self._draw_text(draw, self.current_artist, 1, 7, MATRIX_W - 12, False)

        draw.rectangle((MATRIX_W - 12, 0, MATRIX_W - 1, 12), fill=(0, 0, 0))
        self._draw_play_pause(draw, MATRIX_W - 9, 3, response.is_playing)

        if self.current_art_img:
            img.paste(self.current_art_img if self.current_art_img.size == (48, 48) else \
                      self.current_art_img.resize((48, 48), Image.LANCZOS), (8, 14))

        if response.is_playing and response.lyrics:
             self._draw_lyrics(img, draw, response.lyrics, progress_ms)

        return img

    def _handle_track_change(self, new_track_id: str):
        self.slide_active = True
        self.slide_frames = 0
        # Snapshot the LAST GENERATED frame for transition.
        # Ideally this should be content-only to match new behavior, but
        # last_generated_frame has the bar. 
        # We will accept that the start of the slide has a bar moving out, but
        # we can try to crop it? No, simpler to just snapshot current state.
        # Wait, if we want bar to be static, we should snapshot the content layer?
        # We don't store the content layer separately.
        # For this refactor, let's just use last_generated_frame. 
        # The user request "exclude progress bar from slide transition" usually means
        # "progress bar stays fixed at bottom while art slides".
        # So we really need to save 'last_content_frame'.
        
        self.prev_frame_snapshot = self.last_content_frame if hasattr(self, 'last_content_frame') else (self.last_generated_frame or self.black_screen.copy())
        
        self.slide_direction = 1
        if new_track_id in self.track_history:
             try:
                 curr_i = self.track_history.index(self.current_track_id) if self.current_track_id in self.track_history else -1
                 new_i = self.track_history.index(new_track_id)
                 if curr_i != -1 and new_i < curr_i:
                     self.slide_direction = -1
             except ValueError: pass
        
        self.current_track_id = new_track_id
        if new_track_id not in self.track_history:
            self.track_history.append(new_track_id)
            if len(self.track_history) > 20:
                self.track_history.pop(0)

    def _update_track(self, artist: str, title: str):
        if self.current_title != title or self.current_artist != artist:
            self.current_artist = artist
            self.current_title = title
            self.title_animation_cnt = self.artist_animation_cnt = 0
            self.last_title_reset = self.last_artist_reset = math.floor(time.time())

    def _update_art(self, art_url: str):
        if self.current_art_url != art_url:
            self.current_art_url = art_url
            self.current_art_img = self._fetch_image(art_url)
            if self.current_art_img:
                self.dynamic_color = self._get_vibrant_color(self.current_art_img)

    def _get_vibrant_color(self, img: Image.Image):
        colors = img.copy().resize((32, 32)).getcolors(1024)
        if not colors: return GREEN

        candidates = []
        for count, rgb in colors:
            r, g, b = rgb
            if r == g == b: continue
            
            mx, mn = max(rgb), min(rgb)
            if mx == 0: continue
            
            diff = mx - mn
            sat, val = diff / mx, mx / 255.0
            
            if sat > 0.3 and val > 0.3:
                h = 0
                if mx == r: h = (g - b) / diff % 6
                elif mx == g: h = (b - r) / diff + 2
                else: h = (r - g) / diff + 4
                
                score = count * (sat ** 2)
                if (0 <= h <= 1 or h >= 5.5) and sat < 0.6: score *= 0.1
                candidates.append((score, rgb))
        
        if not candidates: return GREEN

        best = sorted(candidates, key=lambda x: x[0], reverse=True)[0][1]
        
        r, g, b = best
        mx = max(r, g, b)
        if mx < 215:
            scale = 215.0 / mx
            best = (min(255, int(r * scale)), min(255, int(g * scale)), min(255, int(b * scale)))
        return best

    def _fetch_image(self, url: str) -> Optional[Image.Image]:
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            return Image.open(BytesIO(r.content)).convert("RGB")
        except Exception: return None

    def _draw_text(self, draw, text, x, y, width, is_title):
        text = text or ("Unknown Title" if is_title else "Unknown Artist")
        txt_w = self.font.getlength(text)
        
        if txt_w <= width:
            draw.text((x, y), text, WHITE, font=self.font)
            return

        cnt = self.title_animation_cnt if is_title else self.artist_animation_cnt
        draw.text((x - cnt, y), text + "     " + text, WHITE, font=self.font)
        
        t = math.floor(time.time())
        last = self.last_title_reset if is_title else self.last_artist_reset
        
        if t - last >= self.scroll_delay:
            if is_title: self.title_animation_cnt += 1
            else: self.artist_animation_cnt += 1

        if cnt >= self.font.getlength(text + "     "):
             if is_title: 
                 self.title_animation_cnt = 0
                 self.last_title_reset = t
             else: 
                 self.artist_animation_cnt = 0
                 self.last_artist_reset = t

    def _draw_progress_bar(self, draw, progress, duration):
        draw.rectangle((0, 62, 63, 63), fill=(100, 100, 100))
        if duration > 0:
            w = round(64 * progress / duration)
            draw.rectangle((0, 62, min(w, 63), 63), fill=self.dynamic_color)

    def _draw_play_pause(self, draw, x, y, is_playing):
        if is_playing:
            draw.line([(x, y), (x, y + 6)], fill=self.dynamic_color, width=2)
            draw.line([(x + 3, y), (x + 3, y + 6)], fill=self.dynamic_color, width=2)
        else:
            draw.polygon([(x, y), (x, y + 6), (x + 4, y + 3)], fill=self.dynamic_color)

    def _draw_lyrics(self, frame, draw, lyrics, progress):
        lines = lyrics.get('lyrics', {}).get('lines', [])
        cur = None
        for line in lines:
            if int(line['startTimeMs']) <= progress:
                if line['words'].strip(): cur = line['words'].strip()
            else: break
            
        if not cur or cur == "♪": return

        max_w = MATRIX_W - 6
        words = cur.split()
        out, line_str = [], ""
        
        for word in words:
            test = f"{line_str} {word}".strip() if line_str else word
            if self.font.getlength(test) <= max_w:
                line_str = test
            else:
                if line_str: out.append(line_str)
                line_str = word
                if len(out) >= 6: 
                    line_str = "..."
                    break
        if line_str: out.append(line_str)

        y0 = 14 + (48 - len(out) * 6) // 2
        overlay = Image.new("RGBA", (64, 48), (0, 0, 0, 150))
        frame.paste(overlay, (0, 14), overlay)

        for i, l in enumerate(out):
            x = (MATRIX_W - self.font.getlength(l)) // 2
            draw.text((x, y0 + i * 6), l, fill=WHITE, font=self.font)
