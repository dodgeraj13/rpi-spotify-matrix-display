from PIL import Image

W, H = 64, 64

class PlayerFullscreen:
    @staticmethod
    def generate(response, components):
        img = Image.new("RGB", (W, H), (0, 0, 0))
        orig_x, orig_y, orig_w, orig_h = components.album_art.x, components.album_art.y, components.album_art.width, components.album_art.height
        components.album_art.x = 0
        components.album_art.y = 0
        components.album_art.width = W
        components.album_art.height = H
        
        components.album_art.draw(img, response.art_url)
        
        components.album_art.x, components.album_art.y, components.album_art.width, components.album_art.height = orig_x, orig_y, orig_w, orig_h
        
        return img
