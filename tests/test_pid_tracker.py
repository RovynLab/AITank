import unittest
from unittest.mock import patch
from collections import deque
from types import SimpleNamespace
from petcar.core.pid_tracker import PIDTracker, _ServoAxis
from tracking_baseline import _ServoAxis as StableAxis


class TrackingTests(unittest.TestCase):
    def test_center_noise_and_single_outlier_do_not_move(self):
        axis = _ServoAxis()
        for error in [0, 5, -8, 13, 18, -17, 25, 10, 19, 23] * 20:
            self.assertEqual(axis.update(error, 0.56), 0)

    def test_reversal_requires_confirmation_and_clears_old_error(self):
        axis = _ServoAxis()
        self.assertEqual(axis.update(100, 0.56), 0)
        self.assertGreater(axis.update(100, 0.56), 0)
        self.assertEqual(axis.update(-100, 0.56), 0)
        self.assertLess(axis.update(-100, 0.56), 0)
        self.assertEqual(axis.update(8, 0.56), 0)
        self.assertEqual(axis.update(22, 0.56), 0)

    def test_delayed_stationary_target_settles(self):
        for initial in (-200, -60, 60, 200):
            for gain in (0.56, 0.8):
                axis = _ServoAxis()
                error = initial
                delay = deque([0.0, 0.0])
                commands = []
                for i in range(120):
                    error -= delay.popleft() * 10
                    noise = (0, 3, -3, 2, -2)[i % 5]
                    command = axis.update(error + noise, gain)
                    commands.append(command)
                    delay.append(command)
                self.assertLess(abs(error), 24)
                self.assertTrue(all(abs(v) <= 4 for v in commands))
                self.assertEqual(commands[-20:], [0] * 20)

    def test_faster_acquisition_and_continuous_moving_target(self):
        def simulate(axis, interval, speed):
            error = 200.0
            due = deque()
            next_sample = 0
            settled_at = None
            late_errors = []
            for tick in range(600):
                now = tick / 100.0
                error += speed / 100.0
                while due and due[0][0] <= now:
                    error -= due.popleft()[1] * 10
                if now + 1e-8 >= next_sample:
                    command = axis.update(error, 0.56)
                    due.append((now + 0.15, command))
                    next_sample += interval
                if settled_at is None and abs(error) < 24:
                    settled_at = now
                if now >= 3:
                    late_errors.append(abs(error))
            return settled_at, sum(late_errors) / len(late_errors)
        old_time, _ = simulate(StableAxis(), 0.2, 0)
        new_time, _ = simulate(_ServoAxis(), 0.12, 0)
        self.assertLess(new_time, old_time * 0.75)
        _, old_lag = simulate(StableAxis(), 0.2, 60)
        _, new_lag = simulate(_ServoAxis(), 0.12, 60)
        self.assertLess(new_lag, old_lag * 0.8)
        print(f'Acquisition: {old_time:.2f}s -> {new_time:.2f}s; moving lag: {old_lag:.1f}px -> {new_lag:.1f}px')

    def test_loop_resolution_loss_and_limits(self):
        for width, height in ((640, 480), (1280, 720)):
            camera = SimpleNamespace(is_open=True)
            ptz = SimpleNamespace(h_cur=90.0, v_cur=90.0)
            moves = []
            def rotate(angle):
                moves.append(angle)
                ptz.h_cur = angle
            ptz.h_rotate = rotate
            ptz.v_rotate = lambda a: self.fail('centered vertical axis moved')
            tracker = PIDTracker(camera, ptz, lambda: {})
            tracker.pid_x.kp = 10  # Even oversized panel inputs stay bounded.
            tracker.running = True
            sequence = iter([40, 40, None, 40, 40, 0, 15, -15])
            camera.latest_frame = lambda: SimpleNamespace(shape=(height,width,3))
            def find(frame):
                try:
                    error = next(sequence)
                except StopIteration:
                    tracker.running = False
                    return None
                if error is None:
                    return None
                return ((width/2 + error*width/640, height/2), (0,0,60,60))
            tracker._find_target = find
            with patch('petcar.core.pid_tracker.time.sleep'):
                tracker._loop()
            self.assertEqual(len(moves), 2)
            self.assertGreaterEqual(ptz.h_cur, 86)
            tracker.stop()
            self.assertEqual(tracker.out_x, 0)


if __name__ == '__main__':
    unittest.main()
