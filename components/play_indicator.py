import math
import time

class PlayIndicator:
    def __init__(self, x: int, y: int, width: int, height: int):
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    def draw(self, draw, state: str, color=(102, 240, 110)):
        draw.rectangle((self.x - 2, self.y - 2, 63, self.y + self.height + 2), fill=(0, 0, 0))
        if state == "Paused":
            draw.rectangle((self.x, self.y, self.x + 1, self.y + 6), fill=color)
            draw.rectangle((self.x + 3, self.y, self.x + 4, self.y + 6), fill=color)
        elif state == "Play":
            draw.polygon([(self.x, self.y), (self.x, self.y + 6), (self.x + 4, self.y + 3)], fill=color)
        elif state == "Active":
            t = time.time()
            for i in range(3):
                h = 1.0 + 2.5 * (0.5 + 0.5 * math.sin(t * (12 + i * 3) + i * 2))
                t_y = max(self.y, int(self.y + 3 - h))
                b_y = min(self.y + 6, int(self.y + 3 + h))
                draw.rectangle((self.x + i * 2, t_y, self.x + i * 2, b_y), fill=color)
