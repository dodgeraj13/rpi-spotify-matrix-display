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
            is_blue_purple = 0.45 <= h <= 0.82
            
            if is_brown:
                weight = 1.0
            elif is_blue_purple:
                weight = 1.5
            else:
                weight = 3.0
                
            valid_buckets.append({
                'color': b_color,
                'score': (b_count ** 0.1) * weight * vibrancy
            })
            
    if not valid_buckets:
        return (102, 240, 110)
        
    valid_buckets.sort(key=lambda x: x['score'], reverse=True)
    best_color = valid_buckets[0]['color']
        
    exact_pixels_in_bucket = [p for p in pixels if bucket(p) == best_color]
    if not exact_pixels_in_bucket:
        return (102, 240, 110)
        
    chosen_pixel = Counter(exact_pixels_in_bucket).most_common(1)[0][0]
    
    r, g, b = chosen_pixel
    h, s, v = colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0)
        
    if s < 0.2 or v < 0.4:
        return (102, 240, 110)
        
    if v < 0.6:
        factor = 0.6 / max(v, 0.01)
        r = min(255, int(r * factor))
        g = min(255, int(g * factor))
        b = min(255, int(b * factor))
        chosen_pixel = (r, g, b)
        
    return chosen_pixel
