from PIL import Image, ImageDraw

W, H = 64, 64

class PlayerStandard:
    @staticmethod
    def generate(response, progress_ms, duration_ms, show_play, components):
        img = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        components.title_scroll.x = 1
        components.title_scroll.y = 1
        components.title_scroll.width = 52

        components.artist_scroll.x = 1
        components.artist_scroll.y = 7
        components.artist_scroll.width = 52

        components.progress_bar.x = 0
        components.progress_bar.y = 62
        components.progress_bar.width = 64
        components.progress_bar.height = 2

        components.album_art.x, components.album_art.y, components.album_art.width, components.album_art.height = 8, 14, 48, 48
        
        components.play_indicator.x, components.play_indicator.y = 56, 3
        components.play_indicator.width, components.play_indicator.height = 4, 6

        components.title_scroll.draw(draw)
        components.artist_scroll.draw(draw)
        components.progress_bar.draw(draw, progress_ms, duration_ms)
        
        draw.rectangle((53, 0, 63, 12), fill=(0, 0, 0))
        draw.rectangle((W - 1, 0, W - 1, 16), fill=(0, 0, 0))

        components.album_art.draw(img, response.art_url)

        draw.rectangle((55, 0, 63, 12), fill=(0, 0, 0))
        state = "Paused" if not response.is_playing else ("Play" if show_play else "Active")
        components.play_indicator.draw(draw, state)

        return img
