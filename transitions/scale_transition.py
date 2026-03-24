class ScaleTransition:
    @staticmethod
    def apply(element, start_x: int, start_y: int, start_w: int, start_h: int, end_x: int, end_y: int, end_w: int, end_h: int, progress: float):
        """Moves element to new x,y and shrinks or grows the size."""
        element.x = int(start_x + (end_x - start_x) * progress)
        element.y = int(start_y + (end_y - start_y) * progress)
        element.width = int(start_w + (end_w - start_w) * progress)
        element.height = int(start_h + (end_h - start_h) * progress)
