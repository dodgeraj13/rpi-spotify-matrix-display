from io import BytesIO
import threading
import time
import requests
from PIL import Image

W, H = 64, 64

class ArtCache:
    def __init__(self):
        self._cache = {}
        self._fetching_url = None

    def get(self, url, size=None):
        data = self._cache.get(url)
        if not data or 'orig' not in data: return None
        if size is None: return data['orig']
        if size not in data:
            data[size] = data['orig'].resize((size, size), Image.LANCZOS)
        return data[size]

    def fetch(self, url, safe_urls):
        if not url or url in self._cache or self._fetching_url == url: return
        self._fetching_url = url
        def _fetch():
            try:
                r = requests.get(url, timeout=10)
                r.raise_for_status()
                img = Image.open(BytesIO(r.content)).convert("RGB")
                width, height = img.size
                if width != height:
                    sz = min(width, height)
                    l, t = (width - sz) // 2, (height - sz) // 2
                    img = img.crop((l, t, l + sz, t + sz))
                self._cache[url] = {'orig': img}
                
                keys = list(self._cache.keys())
                for k in keys:
                    if len(self._cache) <= 4: break
                    if k not in safe_urls and k != url:
                        del self._cache[k]
            except Exception as e:
                print(f"Error fetching image {url}: {e}")
            finally:
                self._fetching_url = None
        threading.Thread(target=_fetch, daemon=True).start()

    @property
    def is_fetching(self):
        return self._fetching_url is not None

class ScrollManager:
    def __init__(self, font, scroll_delay):
        self.font = font
        self.scroll_delay = scroll_delay
        self.title_limit = 0
        self.artist_limit = 0
        self.title_pos = 0.0
        self.artist_pos = 0.0
        self.is_scrolling = False
        self.last_scroll_end = time.time()
        self.last_cycle_start = time.time()

    def update_limits(self, title, artist, stable_width):
        spacer = "     "
        t_w = self.font.getlength(title) if title else 0
        a_w = self.font.getlength(artist) if artist else 0
        
        self.title_limit = self.font.getlength(title + spacer) if t_w > stable_width else 0
        self.artist_limit = self.font.getlength(artist + spacer) if a_w > stable_width else 0
        
        self.is_scrolling = False
        self.title_pos = self.artist_pos = 0.0
        self.last_scroll_end = time.time()

    def update(self, t_progress, now):
        if not self.is_scrolling:
            if (self.title_limit > 0 or self.artist_limit > 0) and (now - self.last_scroll_end >= self.scroll_delay):
                if not (0.0 < t_progress < 1.0):
                    self.is_scrolling = True
                    self.last_cycle_start = now
        
        if self.is_scrolling:
            elapsed = now - self.last_cycle_start
            speed = 15.0
            
            if self.title_limit > 0:
                self.title_pos = min(elapsed * speed, self.title_limit)
            else:
                self.title_pos = 0.0
                
            if self.artist_limit > 0:
                self.artist_pos = min(elapsed * speed, self.artist_limit)
            else:
                self.artist_pos = 0.0
            
            t_done = self.title_limit == 0 or self.title_pos >= self.title_limit
            a_done = self.artist_limit == 0 or self.artist_pos >= self.artist_limit
            
            if t_done and a_done:
                self.is_scrolling = False
                self.title_pos = self.artist_pos = 0.0
                self.last_scroll_end = now
        else:
            self.title_pos = self.artist_pos = 0.0

        return int(round(self.title_pos)), int(round(self.artist_pos))

class TransitionManager:
    def __init__(self, target_fps: int):
        self.active = False
        self.frames = 0
        self.total_frames = 24
        self.target_fps = target_fps
        self.direction = 1
        self.snapshot = None
        self.finish_time = 0.0
        self.history = []

    def start(self, new_track_id, current_track_id, current_frame, black_screen):
        self.active = True
        self.frames = 0
        self.snapshot = current_frame or black_screen
        self.direction = 1
        
        if new_track_id in self.history and current_track_id in self.history:
            if self.history.index(new_track_id) < self.history.index(current_track_id):
                self.direction = -1

    def update_history(self, track_id):
        if track_id not in self.history:
            self.history.append(track_id)
            if len(self.history) > 20:
                self.history.pop(0)

    def generate_frame(self, target_frame, dt: float):
        progress = self.frames / self.total_frames
        offset = int(W * progress)
        comp = Image.new("RGB", (W, H), (0, 0, 0))
        
        if self.direction == 1:
            comp.paste(self.snapshot, (-offset, 0))
            comp.paste(target_frame, (W - offset, 0))
        else:
            comp.paste(self.snapshot, (offset, 0))
            comp.paste(target_frame, (-W + offset, 0))

        self.frames += dt * self.target_fps
        if self.frames >= self.total_frames:
            self.active = False
            self.finish_time = time.time()
            
        return comp
