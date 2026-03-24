import math

def ease_out_back(t: float, s: float = 1.70158) -> float:
    """Overshoots the target before returning to it (rubberband effect)."""
    if t >= 1.0: return 1.0
    if t <= 0.0: return 0.0
    t = t - 1
    return t * t * ((s + 1) * t + s) + 1

def ease_linear_back(t: float, linear_end: float = 0.8) -> float:
    """
    Linear for the first `linear_end` portion, then a smooth sine bounce.
    The bounce starts with the same velocity as the linear portion for maximum smoothness.
    """
    if t <= 0.0: return 0.0
    if t >= 1.0: return 1.0
    
    if t < linear_end:
        return t / linear_end
    else:
        # Bounce in the remaining time
        # To make it smooth, we match the velocity (1/linear_end) at the transition point.
        v = 1.0 / linear_end
        d = 1.0 - linear_end
        u = (t - linear_end) / d
        # Using sin(u*pi)/pi ensures f(0)=0, f(1)=0, and f'(0)=1
        # Then we scale it by (v*d) to match the initial velocity.
        return 1.0 + (v * d / math.pi) * math.sin(u * math.pi)
