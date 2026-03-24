class ProgressBar:
    def __init__(self, x: int, y: int, width: int, height: int):
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    def draw(self, draw, progress_ms: int, duration_ms: int, bg_color=(100, 100, 100), fill_color=(102, 240, 110)):
        draw.rectangle((self.x, self.y, self.x + self.width - 1, self.y + self.height - 1), fill=bg_color)
        if duration_ms > 0:
            w = round(self.width * progress_ms / duration_ms)
            if w > 0:
                draw.rectangle((self.x, self.y, self.x + min(w, self.width) - 1, self.y + self.height - 1), fill=fill_color)
