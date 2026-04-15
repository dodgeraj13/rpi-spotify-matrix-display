from io import BytesIO
import threading
import requests
from PIL import Image
from .color_utils import get_dominant_color

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

    def get_color(self, url):
        data = self._cache.get(url)
        if not data or 'color' not in data: return (102, 240, 110)
        return data['color']

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
                color = get_dominant_color(img)
                self._cache[url] = {'orig': img, 'color': color}
                
                for k in list(self._cache.keys()):
                    if k not in safe_urls and k != url and len(self._cache) > 4:
                        del self._cache[k]
            except Exception as e:
                print(f"Error fetching image {url}: {e}")
            finally:
                self._fetching_url = None
        threading.Thread(target=_fetch, daemon=True).start()

    @property
    def is_fetching(self):
        return self._fetching_url is not None
