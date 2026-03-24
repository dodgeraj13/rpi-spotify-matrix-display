import time
from PIL import Image
from .easing import ease_out_back, ease_linear_back, SLIDE_FRAMES, BOUNCE_FRAMES
from PIL import ImageDraw

W, H = 64, 64

# Artwork coordinates for the standard player
ART_X, ART_Y, ART_W, ART_H = 8, 14, 48, 48

class PlayerTransition:
    def __init__(self, target_fps: int):
        self.active = False
        self.frames = 0
        self.total_frames = SLIDE_FRAMES + BOUNCE_FRAMES
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
        l_end = SLIDE_FRAMES / self.total_frames
        
        # Calculate linear and eased offsets
        o_l = int(W * min(1.0, progress / l_end))
        o_e = int(W * ease_linear_back(progress, l_end))
        
        # Directional variables: d is movement sign, t_base is target starting position
        d, t_base = (-1, W) if self.direction == 1 else (1, -W)
        
        comp = Image.new("RGB", (W, H), 0)
        
        # 1. Slide old track away linearly
        comp.paste(self.snapshot, (d * o_l, 0))
        
        # 2. Slide new track background linearly (black out artwork area to avoid ghosting)
        bg = target_frame.copy()
        ImageDraw.Draw(bg).rectangle((ART_X, ART_Y, ART_X + ART_W - 1, ART_Y + ART_H - 1), fill=0)
        comp.paste(bg, (t_base + d * o_l, 0))
        
        # 3. Slide artwork with rubberband effect
        art = target_frame.crop((ART_X, ART_Y, ART_X + ART_W, ART_Y + ART_H))
        comp.paste(art, (t_base + d * o_e + ART_X, ART_Y))

        self.frames += dt * self.target_fps
        if self.frames >= self.total_frames:
            self.active = False
            self.finish_time = time.time()
            
        return comp
