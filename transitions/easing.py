import math

# Transition timings (frames @ 60fps)
SLIDE_FRAMES = 36
BOUNCE_FRAMES = 26

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
        
        # We use an asymmetric bounce: quick overshoot, followed by a long, slow return.
        # This provides more "ease out" time as requested.
        # The peak of u*(1-u)*(1-0.8u) is ~0.163 at u~0.37.
        # Compared to the sine peak of 1/pi (~0.318), this allows a longer bounce
        # (32 frames vs 16) with nearly identical overshoot distance (~14% vs ~14%).
        return 1.0 + (v * d) * u * (1.0 - u) * (1.0 - 0.8 * u)
