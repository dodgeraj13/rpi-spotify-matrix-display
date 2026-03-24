import time
from PIL import Image

W, H = 64, 64

class PlayerTransition:
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
