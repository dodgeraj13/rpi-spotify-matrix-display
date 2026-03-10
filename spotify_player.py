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
        self.last_title_reset = self.last_artist_reset = time.time()
        self.title_animation_pos = 0.0
        self.artist_animation_pos = 0.0
        self.last_scroll_time = time.time()
        self.last_text_x = 1
        self.title_limit = 0
        self.artist_limit = 0
        self.is_scrolling = False
        self.last_scroll_end_time = 0.0
        self.is_playing = None
        self.playback_start_time = 0.0
        self.last_active_time = math.floor(time.time())
        self.last_playing_time = time.time()  # Track when we were last playing
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

        self.lyrics_transition_frames = 0
        self.max_lyrics_transition_frames = 28

        self.last_is_playing_state = None
        self.play_show_time = 0.0
        self.slide_finish_time = 0.0
        self.is_scrolling = False
        self.title_limit = 0
        self.artist_limit = 0
        self.last_scroll_end_time = 0.0
        self.lyrics_mode_active = False  # True while button should be in lyrics position
        
        self._art_cache = {} # url -> resized_map (size -> Image)
        self._fetching_art_url: Optional[str] = None
        self.pending_response: Optional[PlaybackInfo] = None
        
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
                # Precise timing: sleep for the remainder of the interval
                elapsed = time.time() - start_time
                sleep_time = max(0.0, self.fetch_interval - elapsed)
                time.sleep(sleep_time)

    def generate(self) -> Optional[Image.Image]:
        now = time.time()
        
        if not self.spotify_module.queue.empty():
            new_data = self.spotify_module.queue.get()
            with self.spotify_module.queue.mutex:
                self.spotify_module.queue.queue.clear()
            
            if new_data:
                # If it's a new track, don't swap 'self.response' yet.
                # Put it in pending and wait for art fetch.
                if self.response and self.response.track_id and new_data.track_id != self.response.track_id:
                    self.pending_response = new_data
                    self._update_art(new_data.art_url)
                else:
                    self.response = new_data
                    self.response_timestamp = now
                    self.response_progress_ms = self.response.progress_ms if self.response else 0
                    self.pending_response = None

        # Check if pending response is now ready (art fetch finished)
        if self.pending_response:
            # Art is ready if the URL matches what we fetched OR if fetcher failed/finished
            # We track progress by checking if _fetching_art_url has cleared back to None
            if self._fetching_art_url is None:
                # Art is ready or failed. Trigger transition.
                self.response = self.pending_response
                self.response_timestamp = now
                self.response_progress_ms = self.response.progress_ms
                self.pending_response = None
                
                # Note: self._handle_track_change will be called inside _generate_frame
                # when it sees the updated self.response.track_id

        frame = self._generate_frame(self.response, now)
        self.last_generated_frame = frame
        return frame

    def _generate_frame(self, response: Optional[PlaybackInfo], now: float) -> Optional[Image.Image]:
        if not response:
            return self.black_screen

        if response.is_playing != self.last_is_playing_state:
            self.play_show_time = now
        
        if response.is_playing:
            self.last_active_time = math.floor(now)
        
        self.last_is_playing_state = response.is_playing
        self.is_playing = response.is_playing
        
        if not response.is_playing:
            if math.floor(now) - self.last_active_time > self.shutdown_delay:
                return self.black_screen

        if response.track_id and response.track_id != self.current_track_id:
            # This triggers the snapshot of the OLD frame (last_generated_frame)
            # and starts the slide_active flag.
            self._handle_track_change(response.track_id)

        progress_ms = response.progress_ms
        if self.response_timestamp > 0 and response.is_playing:
            elapsed = int((now - self.response_timestamp) * 1000)
            progress_ms += elapsed

        duration_ms = response.duration_ms
        if duration_ms > 0:
            progress_ms = min(progress_ms, duration_ms)

        self._update_track(response.artist, response.title, now)
        
        # We don't call _update_art here anymore because it's managed 
        # in generate() to synchronize with the transition.
        # But for non-track-changing updates (same song), we should ensure art is set.
        if self.current_art_url != response.art_url and self._fetching_art_url is None:
             self._update_art(response.art_url)

        # Check for 10-second pause to trigger fullscreen art
        if response.is_playing:
            self.last_playing_time = now
        
        is_paused_long = not response.is_playing and (now - self.last_playing_time > 10.0)

        target_frame = None
        if self.always_fullscreen or is_paused_long:
            target_frame = self._generate_fullscreen_frame(progress_ms, duration_ms, response.art_url)
        else:
            target_frame = self._generate_normal_frame(response, progress_ms, duration_ms, now)

        if self.slide_active:
            return self._generate_slide_transition(target_frame)
        
        return target_frame

    def _handle_track_change(self, new_track_id: str):
        if self.current_track_id is not None:
            self.slide_active = True
            self.slide_frames = 0
            self.lyrics_transition_frames = 0
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
            self.slide_finish_time = time.time()
            
        return composite

    def _generate_fullscreen_frame(self, progress_ms: int, duration_ms: int, target_url: str) -> Image.Image:
        img = Image.new("RGB", (W, H), (0, 0, 0))

        if self.current_art_img and self.current_art_url == target_url:
            if self.current_art_img.size != (64, 64):
                img.paste(self.current_art_img.resize((64, 64), Image.LANCZOS), (0, 0))
            else:
                img.paste(self.current_art_img, (0, 0))

        return img

    def _generate_normal_frame(self, response: PlaybackInfo, progress_ms: int, duration_ms: int, now: float) -> Image.Image:
        img = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 0. Check for active lyrics to drive transition
        has_lyrics_now = False
        if response.lyrics and response.lyrics.get('lyrics', {}).get('syncType') == 'LINE_SYNCED':
            lines = response.lyrics['lyrics']['lines']
            current_line = None
            for line in lines:
                if int(line['startTimeMs']) <= progress_ms:
                    current_line = line['words'].strip()
                else:
                    break
            
            if current_line and current_line != "♪":
                has_lyrics_now = True

        prev_lyrics_frames = self.lyrics_transition_frames
        if has_lyrics_now and response.is_playing and not self.slide_active and (now - self.slide_finish_time > 0.4):
            if self.lyrics_transition_frames < self.max_lyrics_transition_frames:
                self.lyrics_transition_frames += 1
        else:
            if self.lyrics_transition_frames > 0:
                self.lyrics_transition_frames -= 1

        # Track direction to decide which button position to show.
        # Switch to lyrics position the moment frames increase; revert the moment they decrease.
        if self.lyrics_transition_frames > prev_lyrics_frames:
            self.lyrics_mode_active = True
        elif self.lyrics_transition_frames < prev_lyrics_frames:
            self.lyrics_mode_active = False

        # Total normalized progress (0.0 to 1.0 over 28 frames)
        t_total = self.lyrics_transition_frames / self.max_lyrics_transition_frames
        # Ensure we exit lyrics mode definitively when the transition is complete
        if t_total == 0:
            self.lyrics_mode_active = False
        
        # Art & Header transition (Locked to first 16 frames)
        art_t = min(1.0, self.lyrics_transition_frames / 16.0)
        
        # 1. Title & Artist (scrolling)
        # No lyrics: x=1, width=W-2. Lyrics: x=17, width=W-18
        text_x = int(1 + (16 * art_t))
        
        # Play indicator sliding logic
        # Normal mode: top-right (y=3), slides in via art_t
        # Lyrics mode: bottom-right (y=55), slides in fresh from right via t_total
        btn_target_x = 55
        btn_left_padding = 3
        btn_start_x = W + btn_left_padding

        if self.lyrics_mode_active:
            # Entering lyrics: button at bottom-right, slides in from right as t_total 0→1
            btn_target_x_lyrics = 56
            btn_y = 54
            btn_x = int(btn_target_x_lyrics + (btn_start_x - btn_target_x_lyrics) * (1.0 - t_total))
        else:
            # Normal mode: button always present at top-right.
            btn_y = 3
            btn_x = btn_target_x


        box_left = btn_x - btn_left_padding
        box_right = box_left + 12
        box_top = btn_y - 3
        box_bottom = btn_y + 9
        
        # Adjust text width to avoid overlap with the sliding box.
        # In normal mode use the TARGET box_left (btn_target_x - padding = 52) so the
        # title/artist never expands when the button is animating in from off-screen.
        if self.lyrics_mode_active:
            text_width = box_left - text_x - 1
        else:
            target_box_left = btn_target_x - btn_left_padding  # always 52
            text_width = target_box_left - text_x - 1
        
        # synchronized scroll update - now with displacement compensation and transition awareness
        self._update_scroll_animation(text_x, art_t, now)
        
        # y positions: 1px from top, 1px gap
        self._draw_text(draw, self.current_title, text_x, 1, text_width, is_title=True)
        self._draw_text(draw, self.current_artist, text_x, 7, text_width, is_title=False)

        # 2. Progress Bar
        # No lyrics: y=62, full 64px width. Lyrics: y=13, right of art.
        if art_t < 0.5:
            # Main bottom bar slides out twice as fast (within first 8 frames)
            bar_y = 62 + int(art_t * 4)
            if bar_y < 64:
                # x=0 for full width 64px
                self._draw_progress_bar(draw, progress_ms, duration_ms, x=0, y=bar_y)
        
        # Header progress bar animation (starts AFTER art_t reaches 1.0)
        # In lyrics mode the button is at y=55 (below the header), so the bar
        # can extend to the full available width rather than stopping at box_left.
        bar_width = W - text_x - 1 if t_total > 0 else text_width
        if self.lyrics_transition_frames > 16:
            target_green_w = round(bar_width * progress_ms / duration_ms) if duration_ms > 0 else 0
            if self.lyrics_transition_frames <= 22:
                # Phase 1: Green part "grows" in one frame at a time (Frames 17-22)
                p_green = (self.lyrics_transition_frames - 16) / 6.0
                current_green_w = int(target_green_w * p_green)
                if current_green_w > 0:
                    draw.rectangle((text_x, 14, text_x + current_green_w - 1, 15), fill=GREEN)
            else:
                # Phase 2: Grey part "fades" in (Frames 23-28)
                p_grey = (self.lyrics_transition_frames - 22) / 6.0
                grey_val = int(100 * p_grey)
                # Draw grey background first (fading in)
                draw.rectangle((text_x, 14, text_x + bar_width - 1, 15), fill=(grey_val, grey_val, grey_val))
                # Then green part on top (always full width for current progress)
                if target_green_w > 0:
                    draw.rectangle((text_x, 14, text_x + target_green_w - 1, 15), fill=GREEN)
        elif t_total == 1.0:
            self._draw_progress_bar(draw, progress_ms, duration_ms, x=text_x, y=14, width=bar_width)

        # 3. Play Indicator Background (behind Art, normal mode only)
        # Only pre-draw in normal mode so art can cleanly overlap it.
        # In lyrics mode the icon is at bottom-right (below art) and drawn last.
        if box_left < W and t_total == 0:
            draw.rectangle((box_left, box_top, box_right, box_bottom), fill=(0, 0, 0))

        # 4. CLIP and Art
        # CLIP LEFT: Prevent scrolling behind art
        if art_t > 0.5:
             draw.rectangle((0, 0, text_x - 1, 16), fill=(0, 0, 0))
        
        # CLIP RIGHT: 1px padding
        draw.rectangle((W - 1, 0, W - 1, 16), fill=(0, 0, 0))

        if self.current_art_img:
            # We no longer need the 'current_art_url == response.art_url' check here
            # because the slide only starts after they match.
            # No lyrics: 48x48 at (8, 14) [ends at 62]. Lyrics: 15x15 at (1, 1) [ends at 16].
            art_size = int(48 - (33 * art_t))
            art_x = int(8 - (7 * art_t))
            art_y = int(14 - (13 * art_t))
            
            # Use cached resized versions
            cached_map = self._art_cache.get(self.current_art_url, {})
            if art_size not in cached_map:
                cached_map[art_size] = self.current_art_img.resize((art_size, art_size), Image.LANCZOS)
                self._art_cache[self.current_art_url] = cached_map
            
            img.paste(cached_map[art_size], (art_x, art_y))

        # 5. Lyrics
        # Appear and fade in during the final phase (Starting at frame 23)
        if self.lyrics_transition_frames >= 23 and has_lyrics_now:
            p_lyrics = min(1.0, (self.lyrics_transition_frames - 22) / 6.0)
            c = int(255 * p_lyrics)
            self._draw_lyrics(img, draw, response.lyrics, progress_ms, y_offset=18, fill=(c, c, c))

        # 6. Play indicator Icon (drawn last - always on top of lyrics)
        if box_left < W and btn_x < W:
            # Show static play triangle for 2s after resume or track change, then animate
            PLAY_SHOW_DURATION = 2.0
            recently_resumed = response.is_playing and (now - self.play_show_time < PLAY_SHOW_DURATION)
            recently_changed = not self.slide_active and (now - self.slide_finish_time < PLAY_SHOW_DURATION)
            freeze_play = recently_resumed or recently_changed
            lyr_pad = 1 if t_total > 0 else 0
            draw.rectangle((box_left - lyr_pad, box_top - lyr_pad, box_right + lyr_pad, box_bottom + lyr_pad), fill=(0, 0, 0))
            self._draw_play_pause(draw, btn_x, btn_y, is_playing=response.is_playing, freeze=freeze_play)

        return img

    def _update_track(self, artist: str, title: str, now: float):
        if self.current_title != title or self.current_artist != artist:
            self.current_artist = artist
            self.current_title = title
            self.title_animation_cnt = 0
            self.artist_animation_cnt = 0
            self.title_animation_pos = 0.0
            self.artist_animation_pos = 0.0
            self.last_title_reset = self.last_artist_reset = now
            self._calculate_text_limits(now)

    def _calculate_text_limits(self, now: float):
        spacer = "     "
        stable_width = W - 18
        
        title_text = self.current_title or "Unknown Title"
        artist_text = self.current_artist or "Unknown Artist"
        
        title_p_width = self.font.getlength(title_text)
        artist_p_width = self.font.getlength(artist_text)
        
        self.title_limit = self.font.getlength(title_text + spacer) if title_p_width > stable_width else 0
        self.artist_limit = self.font.getlength(artist_text + spacer) if artist_p_width > stable_width else 0
        
        # Reset scrolling state for new track
        self.is_scrolling = False
        self.title_animation_pos = 0.0
        self.artist_animation_pos = 0.0
        self.last_scroll_end_time = now

    def _update_art(self, art_url: str):
        if not art_url:
            self.current_art_url = ""
            self.current_art_img = None
            return

        if self.current_art_url != art_url and self._fetching_art_url != art_url:
            self._fetching_art_url = art_url
            def fetcher():
                try:
                    img = self._fetch_image(art_url)
                    if img:
                        self.current_art_img = img
                        self.current_art_url = art_url
                        # Clear old art from cache (keep it lean)
                        if len(self._art_cache) > 2:
                             self._art_cache.clear()
                    else:
                        # Fetch failed, allow transition anyway
                        self.current_art_url = art_url
                except Exception:
                    self.current_art_url = art_url
                finally:
                    self._fetching_art_url = None
                
            threading.Thread(target=fetcher, daemon=True).start()

    def _fetch_image(self, url: str) -> Optional[Image.Image]:
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content)).convert("RGB")
            return img
        except Exception as e:
            print(f"Error fetching image {url}: {e}")
            return None

    def _update_scroll_animation(self, text_x: int, t_progress: float, now: float):
        speed = 15.0 # pixels per second
        
        # 1. State management for scrolling cycle
        if not self.is_scrolling:
            # Check if we should start the cycle (delay has passed)
            if (self.title_limit > 0 or self.artist_limit > 0) and (now - self.last_scroll_end_time >= self.scroll_delay):
                if 0.0 < t_progress < 1.0:
                    # Keep waiting until layout transition is finished
                    pass
                else:
                    self.is_scrolling = True
                    self.last_title_reset = now # Re-use as start of active scroll
        
        # 2. Calculate animation positions
        if self.is_scrolling:
            # Calculate positions based on absolute time since cycle started for maximum stability
            elapsed = now - self.last_title_reset
            
            # Update title pos
            if self.title_limit > 0:
                self.title_animation_pos = elapsed * speed
            else:
                self.title_animation_pos = 0.0
                
            # Update artist pos
            if self.artist_limit > 0:
                self.artist_animation_pos = elapsed * speed
            else:
                self.artist_animation_pos = 0.0

            # Check if both have finished their content
            title_done = (self.title_limit == 0 or self.title_animation_pos >= self.title_limit)
            artist_done = (self.artist_limit == 0 or self.artist_animation_pos >= self.artist_limit)
            
            if title_done and artist_done:
                self.is_scrolling = False
                self.title_animation_pos = 0.0
                self.artist_animation_pos = 0.0
                self.last_scroll_end_time = now
        else:
            # Not scrolling: Reset and hold at start
            self.title_animation_pos = 0.0
            self.artist_animation_pos = 0.0

        # Snapshot integer counts for rendering (using round for smoother transition)
        self.title_animation_cnt = int(round(self.title_animation_pos))
        self.artist_animation_cnt = int(round(self.artist_animation_pos))

    def _draw_text(self, draw: ImageDraw.Draw, text: str, x: int, y: int, width: int, is_title: bool):
        text = text or ("Unknown Title" if is_title else "Unknown Artist")
        spacer = "     "
        pixel_width = self.font.getlength(text)

        if pixel_width > width:
            animation_cnt = self.title_animation_cnt if is_title else self.artist_animation_cnt
            draw.text((x - animation_cnt, y), text + spacer + text, WHITE, font=self.font)
        else:
            draw.text((x, y), text, WHITE, font=self.font)

    def _draw_progress_bar(self, draw: ImageDraw.Draw, progress_ms: int, duration_ms: int, x: int = 1, y: int = 20, width: int = -1):
        bar_width = width if width > 0 else (W - (x * 2))
        draw.rectangle((x, y, x + bar_width - 1, y + 1), fill=(100, 100, 100))
        if duration_ms > 0:
            w = round(bar_width * progress_ms / duration_ms)
            if w > 0:
                draw.rectangle((x, y, x + min(w, bar_width) - 1, y + 1), fill=GREEN)

    def _draw_play_pause(self, draw: ImageDraw.Draw, x: int, y: int, is_playing: bool, freeze: bool = False):
        if not is_playing:
            # Two solid vertical bars (pause icon)
            draw.rectangle((x, y, x + 1, y + 6), fill=GREEN)
            draw.rectangle((x + 3, y, x + 4, y + 6), fill=GREEN)
        elif freeze:
            # Static play triangle (shown briefly after resume / track change)
            draw.polygon([(x, y), (x, y + 6), (x + 4, y + 3)], fill=GREEN)
        else:
            # 3 animated bars extending from center in both directions
            # Clamped to y..y+6 to match the pause icon footprint
            t = time.time()
            center_y = y + 3
            for i in range(3):
                freq = 12 + (i * 3)
                phase = i * 2
                half_h = 1.0 + 2.5 * (0.5 + 0.5 * math.sin(t * freq + phase))
                bar_top = max(y, int(center_y - half_h))
                bar_bot = min(y + 6, int(center_y + half_h))
                draw.rectangle((x + i * 2, bar_top, x + i * 2, bar_bot), fill=GREEN)

    def _draw_lyrics(self, img: Image.Image, draw: ImageDraw.Draw, lyrics: dict, progress_ms: int, y_offset: int = 24, fill=WHITE):
        lines = lyrics['lyrics']['lines']
        current_line = None
        for line in lines:
            if int(line['startTimeMs']) <= progress_ms:
                text = line['words'].strip()
                if text:
                    current_line = text
            else:
                break

        if not current_line or current_line == "♪":
            return

        raw_words = current_line.split()
        out = []
        cur_line = ""
        max_w = W - 2 # 1px padding on each side (x=1 to x=62)

        for word in raw_words:
            # 1. Try to add the whole word naturally
            test = f"{cur_line} {word}".strip()
            if self.font.getlength(test) <= max_w:
                cur_line = test
                continue
            
            # 2. Word doesn't fit. Flush current accumulation.
            if cur_line:
                out.append(cur_line)
                cur_line = ""
            
            # 3. Process the long word (it might need multiple breaks)
            rem = word
            while rem:
                if self.font.getlength(rem) <= max_w:
                    cur_line = rem
                    rem = ""
                    break
                
                # Check for existing hyphens to prioritize
                best_hyphen = -1
                for i in range(len(rem) - 1, 0, -1):
                    if rem[i] == '-' and self.font.getlength(rem[:i+1]) <= max_w:
                        best_hyphen = i + 1
                        break
                
                if best_hyphen != -1:
                    out.append(rem[:best_hyphen])
                    rem = rem[best_hyphen:]
                else:
                    # No existing hyphen fits. Add a new one to break.
                    found_break = False
                    for i in range(len(rem) - 1, 0, -1):
                        if self.font.getlength(rem[:i] + "-") <= max_w:
                            out.append(rem[:i] + "-")
                            rem = rem[i:]
                            found_break = True
                            break
                    if not found_break:
                        # Extreme fallback: too narrow to even add a hyphen
                        out.append(rem[0])
                        rem = rem[1:]

        if cur_line:
            out.append(cur_line)

        line_h = 6
        for i, line_str in enumerate(out):
            y = y_offset + (i * line_h)
            if y + line_h > H:
                break
            draw.text((1, y), line_str, fill=fill, font=self.font)
