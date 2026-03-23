import math
import time
from PIL import Image, ImageDraw

W, H = 64, 64
WHITE = (255, 255, 255)
GREEN = (102, 240, 110)

class PlayerLyrics:
    def __init__(self, font, art_cache):
        self.font = font
        self.art_cache = art_cache

    def generate(self, response, progress_ms, duration_ms, title_pos, artist_pos, title, artist, freeze, lyrics_frames, max_lyrics_frames, has_lyrics_now):
        img = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        t_total = lyrics_frames / max_lyrics_frames
        art_t = min(1.0, lyrics_frames / 16.0)
        
        text_x = int(1 + (16 * art_t))
        btn_start_x = W + 3
        
        btn_x = int(56 + (btn_start_x - 56) * (1.0 - t_total))
        btn_y = 54
        text_width = btn_x - 3 - text_x - 1
            
        box_left, box_right = btn_x - 3, btn_x + 9
        box_top, box_bottom = btn_y - 3, btn_y + 9

        self._draw_text(draw, title, text_x, 1, text_width, title_pos)
        self._draw_text(draw, artist, text_x, 7, text_width, artist_pos)

        if art_t < 0.5:
            bar_y = 62 + int(art_t * 4)
            if bar_y < 64:
                self._draw_progress_bar(draw, progress_ms, duration_ms, 0, bar_y, W)

        bar_width = W - text_x - 1 if t_total > 0 else text_width
        if lyrics_frames > 16:
            green_w = round(bar_width * progress_ms / duration_ms) if duration_ms > 0 else 0
            if lyrics_frames <= 22:
                green_w = int(green_w * ((lyrics_frames - 16) / 6.0))
                if green_w > 0: draw.rectangle((text_x, 14, text_x + green_w - 1, 15), fill=GREEN)
            else:
                grey = int(100 * ((lyrics_frames - 22) / 6.0))
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

        if lyrics_frames >= 23 and has_lyrics_now:
            c = int(255 * min(1.0, (lyrics_frames - 22) / 6.0))
            self._draw_lyrics(draw, response.lyrics, progress_ms, 18, (c, c, c))

        if box_left < W and btn_x < W:
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
