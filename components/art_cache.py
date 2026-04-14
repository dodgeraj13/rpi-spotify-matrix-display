from io import BytesIO
import threading
import requests
from PIL import Image
import colorsys
from collections import Counter

def get_dominant_color(img: Image.Image) -> tuple[int, int, int]:
    sample = img.resize((64, 64)).convert("RGB")
    pixels = list(sample.getdata())
    if not pixels: return (102, 240, 110)
    
    def bucket(p):
        return (p[0] // 16 * 16, p[1] // 16 * 16, p[2] // 16 * 16)
        
    bucket_counts = Counter(bucket(p) for p in pixels)
    
    valid_buckets = []
    for b_color, b_count in bucket_counts.items():
        r, g, b = b_color
        h, s, v = colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0)
        
        is_gray = s < 0.2 or v < 0.2
        if not is_gray:
            vibrancy = s * v
            is_brown = (0.04 <= h <= 0.15) and v < 0.6
            valid_buckets.append({
                'color': b_color,
                'count': b_count,
                'vibrancy': vibrancy,
                'brown': is_brown
            })
            
    if not valid_buckets:
        return (102, 240, 110)
        
    valid_buckets.sort(key=lambda x: x['count'], reverse=True)
    
    best_bucket = valid_buckets[0]
    
    if best_bucket['brown'] and len(valid_buckets) > 1:
        second_best = valid_buckets[1]
        if second_best['vibrancy'] > best_bucket['vibrancy']:
            best_bucket = second_best
            
    best_color = best_bucket['color']
        
    exact_pixels_in_bucket = [p for p in pixels if bucket(p) == best_color]
    if not exact_pixels_in_bucket:
        return (102, 240, 110)
        
    chosen_pixel = Counter(exact_pixels_in_bucket).most_common(1)[0][0]
    
    r, g, b = chosen_pixel
    h, s, v = colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0)
        
    if v < 0.6:
        factor = 0.6 / max(v, 0.01)
        r = min(255, int(r * factor))
        g = min(255, int(g * factor))
        b = min(255, int(b * factor))
        chosen_pixel = (r, g, b)
        
    return chosen_pixel

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
