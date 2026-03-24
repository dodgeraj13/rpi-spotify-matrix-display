class SlideTransition:
    @staticmethod
    def apply(element, start_x: int, start_y: int, end_x: int, end_y: int, progress: float):
        """Moves an element in a direction by interpolating x and y."""
        element.x = int(start_x + (end_x - start_x) * progress)
        element.y = int(start_y + (end_y - start_y) * progress)
