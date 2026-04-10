import time
from PIL import Image
SLIDE_FRAMES = 80

W, H = 64, 64

class PlayerTransition:
    def __init__(self, target_fps: int):
        self.active = False
        self.frames = 0
        self.total_frames = SLIDE_FRAMES
        self.target_fps = target_fps
        self.direction = 1
        self.snapshot = None
        self.finish_time = 0.0
        self.history = []

    def start(self, new_track_id, current_track_id):
        self.active = True
        self.frames = 0
        self.direction = 1
        
        if new_track_id in self.history and current_track_id in self.history:
            if self.history.index(new_track_id) < self.history.index(current_track_id):
                self.direction = -1

    def update_history(self, track_id):
        if track_id not in self.history:
            self.history.append(track_id)
            if len(self.history) > 20:
                self.history.pop(0)

    def generate_frame(self, target_frame, old_frame, dt: float):
        progress = min(1.0, self.frames / self.total_frames)
        
        # Apply an ease-out quad curve
        eased_progress = 1 - (1 - progress) ** 2
        
        # Calculate offset using round instead of int to avoid 1px truncation errors near 1.0
        o_l = round(W * eased_progress)
        
        # Directional variables: d is movement sign, t_base is target starting position
        d, t_base = (-1, W) if self.direction == 1 else (1, -W)
        
        comp = Image.new("RGB", (W, H), 0)
        
        # 1. Slide old track away linearly
        comp.paste(old_frame, (d * o_l, 0))
        
        # 2. Slide new track linearly
        comp.paste(target_frame, (t_base + d * o_l, 0))

        self.frames += dt * self.target_fps
        if self.frames >= self.total_frames:
            self.active = False
            self.finish_time = time.time()
            
        return comp
