# Baseline of the previously deployed conservative controller.
class _ServoAxis:
    """Hysteresis and bounded corrections in reference-image pixels."""

    def reset(self):
        self.filtered = None
        self.active = False
        self.confirmed = 0
        self.direction = 0

    def __init__(self):
        self.reset()

    def update(self, error, gain):
        if abs(error) <= 12 or gain <= 0:
            self.reset()
            return 0.0
        direction = 1 if error > 0 else -1
        if direction != self.direction:
            self.reset()
            self.direction = direction
        self.filtered = error if self.filtered is None else 0.4 * error + 0.6 * self.filtered
        if not self.active:
            if abs(error) < 24:
                self.confirmed = 0
                return 0.0
            self.confirmed += 1
            if self.confirmed < 2:
                return 0.0
            self.active = True
        correction = max(0.0, abs(self.filtered) - 12) / 10.0 * gain
        correction = min(2.0, correction)
        return direction * correction if correction >= 0.3 else 0.0
