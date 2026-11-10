import ast
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = np = None


@unittest.skipIf(cv2 is None, 'OpenCV required')
class ScreenDetectionTests(unittest.TestCase):
    def test_ssd_normalizes_and_filters_sparse_categories(self):
        from petcar.drivers import detectors

        class Interpreter:
            def __init__(self, **kwargs):
                pass
            def allocate_tensors(self):
                pass
            def get_input_details(self):
                return [{'shape': [1, 300, 300, 3], 'index': 0, 'dtype': np.uint8}]
            def get_output_details(self):
                return [{'index': i} for i in (1, 2, 3)]
            def set_tensor(self, *args):
                pass
            def invoke(self):
                pass
            def get_tensor(self, index):
                return {1: np.array([[[.1, .1, .8, .8]] * 4]),
                        2: np.array([[71, 72, 76, 11]]),
                        3: np.array([[.9, .9, .9, .9]])}[index]

        module = types.ModuleType('tflite_runtime.interpreter')
        module.Interpreter = Interpreter
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'detect.tflite').touch()
            missing = {11, 25, 28, 29, 44, 65, 67, 68, 70, 82}
            names = iter(detectors.COCO_CLASSES)
            labels = ['???' if i in missing else next(names) for i in range(90)]
            for prefix in (None, '', '???\n'):
                label_path = Path(tmp, 'labelmap.txt')
                if prefix is None:
                    label_path.unlink(missing_ok=True)
                else:
                    label_path.write_text(prefix + '\n'.join(labels))
                with self.subTest(prefix=prefix), patch.object(detectors, 'MODEL_DIR', tmp), patch.dict(sys.modules, {'tflite_runtime.interpreter': module}):
                    model = detectors.TFLiteSSD()
                    frame = np.zeros((480, 640, 3), dtype=np.uint8)
                    self.assertEqual([d[-1] for d in model.detect(frame)], [62, 63, 67])
                    self.assertEqual([d[-1] for d in model.detect(frame, {67})], [67])


class ScreenRoutingTests(unittest.TestCase):
    def test_screen_button_includes_tv_laptop_and_phone(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / 'petcar/api/flask_app.py').read_text(encoding='utf-8'))
        registry = next(n for n in ast.walk(tree) if isinstance(n, ast.Dict)
                        and any(isinstance(k, ast.Constant) and k.value == 'tv' for k in n.keys))
        entry = next(v for k, v in zip(registry.keys, registry.values) if isinstance(k, ast.Constant) and k.value == 'tv')
        call = next(v for k, v in zip(entry.keys, entry.values) if isinstance(k, ast.Constant) and k.value == 'detect')
        self.assertEqual(ast.literal_eval(call.args[0]), {62, 63, 67})


if __name__ == '__main__':
    unittest.main()
