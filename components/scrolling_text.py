import time

class ScrollingText:
    def __init__(self, x: int, y: int, width: int, height: int, scroll_speed: float, scroll_delay: float, font):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.scroll_speed = scroll_speed
        self.scroll_delay = scroll_delay
        self.font = font
        self.text = ""
        self.base_text_width = 0
        self.full_text_width = 0
        self.pos = 0.0
        self.is_scrolling = False
        self.last_scroll_end = time.time()
        self.last_cycle_start = time.time()
        self.sync_group = []
        self.was_needs_scroll = False

    @property
    def text_width(self):
        return self.full_text_width if self.base_text_width > self.width else 0

    def update_text(self, text: str):
        if self.text != text:
            self.text = text
            if text:
                self.base_text_width = self.font.getlength(text)
                self.full_text_width = self.font.getlength(text + "     ")
            else:
                self.base_text_width = 0
                self.full_text_width = 0
            self.is_scrolling = False
            self.pos = 0.0
            self.last_scroll_end = time.time()

    def update(self, now: float):
        needs_scroll = self.text_width > 0
        if needs_scroll and not self.was_needs_scroll:
            self.last_scroll_end = now
        self.was_needs_scroll = needs_scroll

        if not self.is_scrolling:
            if needs_scroll and (now - self.last_scroll_end >= self.scroll_delay):
                can_start = True
                for other in self.sync_group:
                    if other.text_width > 0 and (other.is_scrolling or now - other.last_scroll_end < self.scroll_delay):
                        can_start = False
                if can_start:
                    self.start_scroll(now)
                    for other in self.sync_group:
                        other.start_scroll(now)
        
        if self.is_scrolling:
            elapsed = now - self.last_cycle_start
            self.pos = min(elapsed * self.scroll_speed, self.text_width) if self.text_width > 0 else 0.0
            
            done = self.text_width == 0 or self.pos >= self.text_width
            if done:
                self.end_scroll(now)
        else:
            self.pos = 0.0

    def start_scroll(self, now):
        self.is_scrolling = True
        self.last_cycle_start = now

    def end_scroll(self, now):
        self.is_scrolling = False
        self.pos = 0.0
        self.last_scroll_end = now

    def add_sync(self, other):
        if other not in self.sync_group:
            self.sync_group.append(other)
            other.sync_group.append(self)

    def draw(self, draw, color=(255, 255, 255)):
        if not self.text: return
        offset = int(round(self.pos))
        if self.text_width > 0:
            draw.text((self.x - offset, self.y), self.text + "     " + self.text, fill=color, font=self.font)
        else:
            draw.text((self.x, self.y), self.text, fill=color, font=self.font)
