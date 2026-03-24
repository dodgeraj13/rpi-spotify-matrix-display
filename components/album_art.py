class AlbumArt:
    def __init__(self, x: int, y: int, width: int, height: int, cache):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.cache = cache

    def draw(self, img, url: str):
        if not url: return
        art = self.cache.get(url, self.width)
        if art:
            img.paste(art, (self.x, self.y))
