import ast
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


class DetectionRefreshTests(unittest.TestCase):
    def make_detector(self, model):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / 'petcar/api/flask_app.py').read_text(encoding='utf-8'))
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_dnn_all')
        namespace = {
            '_dnn_cache': {'m': model, 'frame': None, 'raw': [], 'frame_id': -1, 'count': 0},
            '_dnn_lock': threading.Lock(),
            # Force identifier reuse, reproducing the old cache failure.
            'id': lambda frame: 123,
        }
        exec(compile(ast.Module(body=[fn], type_ignores=[]), 'detection_cache', 'exec'), namespace)
        return namespace['_dnn_all']

    def test_new_frames_follow_moving_object_despite_reused_identifier(self):
        model = Mock()
        model.detect.side_effect = lambda frame: [(frame.x, 20, 30, 40, .9, 67)]
        detect = self.make_detector(model)
        for x in (10, 100, 220, 40):
            self.assertEqual(detect(SimpleNamespace(x=x))[0][0], x)
        self.assertEqual(model.detect.call_count, 4)

    def test_same_frame_shares_inference(self):
        model = Mock()
        model.detect.return_value = [(10, 20, 30, 40, .9, 67)]
        detect = self.make_detector(model)
        frame = object()
        self.assertEqual(detect(frame), detect(frame))
        model.detect.assert_called_once_with(frame)

    def test_removed_object_or_failed_inference_clears_old_box(self):
        for missing_result in ([], RuntimeError('camera frame unavailable')):
            with self.subTest(result=missing_result):
                model = Mock()
                model.detect.side_effect = [[(10, 20, 30, 40, .9, 67)], missing_result]
                detect = self.make_detector(model)
                self.assertTrue(detect(object()))
                self.assertEqual(detect(object()), [])


if __name__ == '__main__':
    unittest.main()
