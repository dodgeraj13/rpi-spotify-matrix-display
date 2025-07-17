import numpy as np, requests, math, time, threading
from PIL import Image, ImageFont, ImageDraw
from io import BytesIO

class SpotifyScreen:
    def __init__(self, config, modules, fullscreen):
        self.modules = modules

        self.font = ImageFont.truetype("fonts/tiny.otf", 5)

        self.canvas_width = 64
        self.canvas_height = 64
        self.title_color = (255,255,255)
        self.artist_color = (255,255,255)
        self.play_color = (102, 240, 110)

        self.full_screen_always = fullscreen

        self.current_art_url = ''
        self.current_art_img = None
        self.current_title = ''
        self.current_artist = ''

        self.title_animation_cnt = 0
        self.artist_animation_cnt = 0
        self.last_title_reset = math.floor(time.time())
        self.last_artist_reset = math.floor(time.time())
        self.scroll_delay = 4

        self.paused = True
        self.paused_time = math.floor(time.time())
        self.paused_delay = 5

        self.is_playing = False

        self.last_fetch_time = math.floor(time.time())
        self.fetch_interval = 1
        self.spotify_module = self.modules['spotify']

        self.response = None
        self.thread = threading.Thread(target=self.getCurrentPlaybackAsync)
        self.thread.start()

        self.previous_art_img = None
        self.slide_animation_progress = -1  # -1 means no animation
        self.slide_total_frames = 12  # how many frames the animation lasts

        self.pause_scale_animation_progress = -1
        self.pause_unscale_animation_progress = -1
        self.pause_scale_total_frames = 8

        self.current_title_for_slide = ''

    def getCurrentPlaybackAsync(self):
        # delay spotify fetches
        time.sleep(3)
        while True:
            self.response = self.spotify_module.getCurrentPlayback()
            time.sleep(1)

    def generate(self):
        if not self.spotify_module.queue.empty():
            self.response = self.spotify_module.queue.get()
            self.spotify_module.queue.queue.clear()
        return self.generateFrame(self.response)

    def generateFrame(self, response):
        if response is not None:
            (artist, title, art_url, self.is_playing, progress_ms, duration_ms, lyrics, is_previous) = response

            if self.full_screen_always:
                if self.current_art_url != art_url or self.current_title_for_slide != title:
                    self.previous_art_img = self.current_art_img
                    self.slide_animation_progress = 0

                    self.current_art_url = art_url
                    self.current_title_for_slide = title
                    
                    response = requests.get(self.current_art_url)
                    img = Image.open(BytesIO(response.content))
                    self.current_art_img = img.resize((self.canvas_width, self.canvas_height), resample=Image.LANCZOS)

                frame = Image.new("RGB", (self.canvas_width, self.canvas_height), (0,0,0))
                draw = ImageDraw.Draw(frame)

                if self.slide_animation_progress >= 0 and self.previous_art_img:
                    offset = int((self.slide_animation_progress / self.slide_total_frames) * self.canvas_width)
                    if is_previous:
                        # Reverse slide: current enters from left
                        frame.paste(self.previous_art_img, (offset, 0))
                        frame.paste(self.current_art_img, (-self.canvas_width + offset, 0))
                    else:
                        # Normal slide: current enters from right
                        frame.paste(self.previous_art_img, (-offset, 0))
                        frame.paste(self.current_art_img, (self.canvas_width - offset, 0))

                    self.slide_animation_progress += 1
                    if self.slide_animation_progress >= self.slide_total_frames:
                        self.slide_animation_progress = -1
                        self.previous_art_img = None
                else:
                    frame.paste(self.current_art_img, (0, 0))

                return (frame, self.is_playing)
            else:
                if not self.is_playing:
                    if not self.paused:
                        self.paused_time = math.floor(time.time())
                        self.paused = True
                else:
                    if self.paused and self.current_art_img and self.current_art_img.size == (self.canvas_width, self.canvas_height):
                        self.title_animation_cnt = 0
                        self.artist_animation_cnt = 0
                        self.last_title_reset = math.floor(time.time())
                        self.last_artist_reset = math.floor(time.time())
                        self.pause_unscale_animation_progress = 0
                        self.pause_scale_animation_progress = -1
                    self.paused_time = math.floor(time.time())
                    self.paused = False

                if (self.current_title != title or self.current_artist != artist):
                    self.current_artist = artist
                    self.current_title = title
                    self.title_animation_cnt = 0
                    self.artist_animation_cnt = 0
                    self.last_title_reset = math.floor(time.time())
                    self.last_artist_reset = math.floor(time.time())

                current_time = math.floor(time.time())
                show_fullscreen = current_time - self.paused_time >= self.paused_delay

                # show fullscreen album art after pause delay
                if show_fullscreen and self.current_art_img.size == (48, 48):
                    self.pause_scale_animation_progress = 0
                    response = requests.get(self.current_art_url)
                    img = Image.open(BytesIO(response.content))
                    self.current_art_img = img.resize((self.canvas_width, self.canvas_height), resample=Image.LANCZOS)
                elif not show_fullscreen:
                    if self.current_art_url != art_url or self.current_title_for_slide != title:
                        self.previous_art_img = self.current_art_img
                        self.slide_animation_progress = 0

                        self.current_art_url = art_url
                        self.current_title_for_slide = title

                        response = requests.get(self.current_art_url)
                        img = Image.open(BytesIO(response.content))
                        self.current_art_img = img.resize((48, 48), resample=Image.LANCZOS)
                    elif self.current_art_img.size == (self.canvas_width, self.canvas_height):
                        self.current_art_img = self.current_art_img.resize((48, 48), resample=Image.LANCZOS)

                frame = Image.new("RGB", (self.canvas_width, self.canvas_height), (0,0,0))
                draw = ImageDraw.Draw(frame)

                # exit early if fullscreen
                if self.current_art_img is not None:
                    if show_fullscreen or self.pause_unscale_animation_progress >= 0:
                        if self.pause_scale_animation_progress >= 0:
                            half = self.pause_scale_total_frames // 2
                            p = self.pause_scale_animation_progress

                            if p < half:
                                # Slide up before scaling
                                slide_progress = p / half
                                y = int(14 * (1 - slide_progress))
                                size = 48
                            else:
                                # Scale up
                                scale_progress = (p - half) / half
                                size = int(48 + (64 - 48) * scale_progress)
                                y = 0

                            resized = self.current_art_img.resize((size, size), resample=Image.LANCZOS)
                            x = (self.canvas_width - size) // 2
                            frame.paste(resized, (x, y))

                            self.pause_scale_animation_progress += 1
                            if self.pause_scale_animation_progress >= self.pause_scale_total_frames:
                                self.pause_scale_animation_progress = -1
                                response = requests.get(self.current_art_url)
                                img = Image.open(BytesIO(response.content))
                                self.current_art_img = img.resize((self.canvas_width, self.canvas_height), resample=Image.LANCZOS)

                            return (frame, self.is_playing)

                        elif self.pause_unscale_animation_progress >= 0:
                            half = self.pause_scale_total_frames // 2
                            p = self.pause_unscale_animation_progress

                            if p < half:
                                # Scale down
                                scale_progress = p / half
                                size = int(64 - (64 - 48) * scale_progress)
                                y = 0
                            else:
                                # Slide down
                                slide_progress = (p - half) / half
                                size = 48
                                y = int(14 * slide_progress)

                            resized = self.current_art_img.resize((size, size), resample=Image.LANCZOS)
                            x = (self.canvas_width - size) // 2
                            frame.paste(resized, (x, y))

                            self.pause_unscale_animation_progress += 1
                            if self.pause_unscale_animation_progress >= self.pause_scale_total_frames:
                                self.pause_unscale_animation_progress = -1
                                response = requests.get(self.current_art_url)
                                img = Image.open(BytesIO(response.content))
                                self.current_art_img = img.resize((48, 48), resample=Image.LANCZOS)

                            return (frame, self.is_playing)

                        else:
                            frame.paste(self.current_art_img, (0,0))
                            return (frame, self.is_playing)
                    else:
                        if self.slide_animation_progress >= 0 and self.previous_art_img:
                            offset = int((self.slide_animation_progress / self.slide_total_frames) * 56)  # 48 + margin
                            if is_previous:
                                # Slide right-to-left (reverse)
                                prev_x = 8 + offset
                                curr_x = 8 - (56 - offset)
                            else:
                                # Slide left-to-right (default)
                                prev_x = 8 - offset
                                curr_x = 8 + (56 - offset)

                            frame.paste(self.previous_art_img, (prev_x, 14))
                            frame.paste(self.current_art_img, (curr_x, 14))

                            self.slide_animation_progress += 1
                            if self.slide_animation_progress >= self.slide_total_frames:
                                self.slide_animation_progress = -1
                                self.previous_art_img = None
                        else:
                            frame.paste(self.current_art_img, (8,14))

                freeze_title = self.title_animation_cnt == 0 and self.artist_animation_cnt > 0
                freeze_artist = self.artist_animation_cnt == 0 and self.title_animation_cnt > 0

                title_len = self.font.getlength(self.current_title)
                artist_len = self.font.getlength(self.current_artist)

                text_length = self.canvas_width - 12
                x_offset = 1
                spacer = "     "

                if title_len > text_length:
                    draw.text((x_offset-self.title_animation_cnt, 1), self.current_title + spacer + self.current_title, self.title_color, font = self.font)
                    if current_time - self.last_title_reset >= self.scroll_delay:
                        self.title_animation_cnt += 1
                    if freeze_title or self.title_animation_cnt == self.font.getlength(self.current_title + spacer):
                        self.title_animation_cnt = 0
                        self.last_title_reset = math.floor(time.time())
                else:
                    draw.text((x_offset-self.title_animation_cnt, 1), self.current_title, self.title_color, font = self.font)

                if artist_len > text_length:
                    draw.text((x_offset-self.artist_animation_cnt, 7), self.current_artist + spacer + self.current_artist, self.artist_color, font = self.font)
                    if current_time - self.last_artist_reset >= self.scroll_delay:
                        self.artist_animation_cnt += 1
                    if freeze_artist or self.artist_animation_cnt == self.font.getlength(self.current_artist + spacer):
                        self.artist_animation_cnt = 0
                        self.last_artist_reset = math.floor(time.time())
                else:
                    draw.text((x_offset-self.artist_animation_cnt, 7), self.current_artist, self.artist_color, font = self.font)

                draw.rectangle((0,0,0,12), fill=(0,0,0))
                draw.rectangle((52,0,63,12), fill=(0,0,0))

                line_y = 63
                draw.rectangle((0,line_y-1,63,line_y), fill=(100,100,100))
                draw.rectangle((0,line_y-1,0+round(((progress_ms / duration_ms) * 100) // 1.57), line_y), fill=self.play_color)
                drawPlayPause(draw, self.is_playing, self.play_color)

                if lyrics and 'lyrics' in lyrics and 'lines' in lyrics['lyrics'] and self.slide_animation_progress <= 0 and self.pause_scale_animation_progress == -1:
                    lyric_lines = lyrics['lyrics']['lines']
                    current_time_ms = int(progress_ms)

                    # Find the latest lyric line up to current time
                    current_line = None
                    for line in lyric_lines:
                        if int(line['startTimeMs']) <= current_time_ms:
                            text = line['words'].strip()
                            if text:
                                current_line = text
                        else:
                            break

                    if current_line:
                        text_length = self.canvas_width - 6  # max width for wrapped text
                        words = current_line.split()
                        lines = []
                        current = ""

                        max_lines = 7
                        broke_early = False

                        for i, word in enumerate(words):
                            test = f"{current} {word}".strip()
                            if self.font.getlength(test) <= text_length:
                                current = test
                            else:
                                lines.append(current)
                                current = word
                                if len(lines) == max_lines - 1:
                                    # We have filled 6 lines, next is 7th
                                    # If we still have words remaining, break early
                                    if i < len(words) - 1:
                                        broke_early = True
                                    break

                        # Append the last line (7th)
                        if len(lines) < max_lines - 1:
                            # fewer than 6 lines so just append current
                            lines.append(current)
                        else:
                            # 7th line, truncate if broke_early (more text exists)
                            if broke_early:
                                ellipsis = ".."
                                while self.font.getlength(current + ellipsis) > text_length and current:
                                    current = current.rsplit(" ", 1)[0]
                                current = (current + ellipsis).strip()
                            lines.append(current)

                        # Center vertically in 48x48 box starting at y=14
                        line_height = 6  # adjust if needed based on your font
                        total_height = len(lines) * line_height
                        y_start = 14 + (48 - total_height) // 2

                        overlay = Image.new("RGBA", (64, 48), (0, 0, 0, 120))  # semi-transparent black
                        frame.paste(overlay, (0, 14), overlay)

                        for i, line in enumerate(lines):
                            text_width = self.font.getlength(line)
                            x = (self.canvas_width - text_width) // 2
                            y = y_start + i * line_height
                            draw.text((x, y), line, fill=self.title_color, font=self.font)
                
                return (frame, self.is_playing)
        else:
            #not active
            frame = Image.new("RGB", (self.canvas_width, self.canvas_height), (0,0,0))
            draw = ImageDraw.Draw(frame)

            self.current_art_url = ''
            self.is_playing = False
            self.title_animation_cnt = 0
            self.artist_animation_cnt = 0
            self.last_title_reset = math.floor(time.time())
            self.last_artist_reset = math.floor(time.time())
            self.paused = True
            self.paused_time = math.floor(time.time())

            return (None, self.is_playing)

def drawPlayPause(draw, is_playing, color):
    x = 10
    y = -16
    if not is_playing:
        draw.line((x+45,y+19,x+45,y+25), fill = color)
        draw.line((x+46,y+20,x+46,y+24), fill = color)
        draw.line((x+47,y+20,x+47,y+24), fill = color)
        draw.line((x+48,y+21,x+48,y+23), fill = color)
        draw.line((x+49,y+21,x+49,y+23), fill = color)
        draw.line((x+50,y+22,x+50,y+22), fill = color)
    else:
        draw.line((x+45,y+19,x+45,y+25), fill = color)
        draw.line((x+46,y+19,x+46,y+25), fill = color)
        draw.line((x+49,y+19,x+49,y+25), fill = color)
        draw.line((x+50,y+19,x+50,y+25), fill = color)
