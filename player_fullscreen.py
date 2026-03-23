from PIL import Image

W, H = 64, 64

class PlayerFullscreen:
    def __init__(self, font, art_cache):
        self.art_cache = art_cache

    def generate(self, response):
        img = Image.new("RGB", (W, H), (0, 0, 0))
        art = self.art_cache.get(response.art_url, 64)
        if art: img.paste(art, (0, 0))
        return img
