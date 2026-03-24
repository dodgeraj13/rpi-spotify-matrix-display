class ResizeTransition:
    @staticmethod
    def apply(element, start_w: int, start_h: int, end_w: int, end_h: int, progress: float):
        """Resizes an element by changing its width and height."""
        element.width = int(start_w + (end_w - start_w) * progress)
        element.height = int(start_h + (end_h - start_h) * progress)
