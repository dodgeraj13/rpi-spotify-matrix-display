import math
import time
from PIL import Image, ImageDraw

W, H = 64, 64
WHITE = (255, 255, 255)
GREEN = (102, 240, 110)

class PlayerStandard:
    def __init__(self, font, art_cache):
        self.font = font
        self.art_cache = art_cache

    def generate(self, response, progress_ms, duration_ms, title_pos, artist_pos, title, artist, freeze):
        img = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        text_x = 1
        btn_x, btn_y = 55, 3
        text_width = 52 - text_x - 1
        
        box_left, box_right = btn_x - 3, btn_x + 9
        box_top, box_bottom = btn_y - 3, btn_y + 9

        self._draw_text(draw, title, text_x, 1, text_width, title_pos)
        self._draw_text(draw, artist, text_x, 7, text_width, artist_pos)

        bar_y = 62
        self._draw_progress_bar(draw, progress_ms, duration_ms, 0, bar_y, W)

        draw.rectangle((box_left, box_top, box_right, box_bottom), fill=(0, 0, 0))
        draw.rectangle((W - 1, 0, W - 1, 16), fill=(0, 0, 0))

        art_size = 48
        art = self.art_cache.get(response.art_url, art_size)
        if art:
            img.paste(art, (8, 14))

        if box_left < W and btn_x < W:
            draw.rectangle((box_left, box_top, box_right, box_bottom), fill=(0, 0, 0))
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
