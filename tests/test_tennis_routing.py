import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageChops
from petcar import config
from petcar.core import runtime_config
from petcar.core.emotion_engine import EmotionEngine
from petcar.drivers.oled import EXPRESSIONS, _draw_face, W, H, EYE_L_CX, EYE_R_CX, EYE_CY

ROOT=Path(__file__).resolve().parents[1]

class TennisRoutingTests(unittest.TestCase):
    def detector(self, dedicated, generic):
        tree=ast.parse((ROOT/'petcar/api/flask_app.py').read_text(encoding='utf-8'))
        function=next(x for x in ast.walk(tree) if isinstance(x,ast.FunctionDef) and x.name=='_tennis_with_fallback')
        namespace={'detect_tennis_ball':dedicated,'_generic_ball':generic}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'tennis_route','exec'),namespace)
        return namespace['_tennis_with_fallback']

    def test_dashboard_ball_button_uses_dedicated_route(self):
        tree = ast.parse((ROOT/'petcar/api/flask_app.py').read_text(encoding='utf-8'))
        registry = next(node for node in ast.walk(tree)
                        if isinstance(node, ast.Dict) and any(
                            isinstance(key, ast.Constant) and key.value == 'ball'
                            for key in node.keys))
        ball = next(value for key, value in zip(registry.keys, registry.values)
                    if isinstance(key, ast.Constant) and key.value == 'ball')
        route = next(value for key, value in zip(ball.keys, ball.values)
                     if isinstance(key, ast.Constant) and key.value == 'detect')
        self.assertIsInstance(route, ast.Name)
        self.assertEqual(route.id, '_tennis_with_fallback')

    def test_dedicated_tennis_detection_has_priority(self):
        calls=[]
        detector=self.detector(lambda f:[(1,2,30,30,.9,-1)],lambda f:calls.append(f))
        self.assertEqual(detector('frame'),[(1,2,30,30,.9)])
        self.assertFalse(calls)

    def test_generic_ball_model_is_fallback(self):
        detector=self.detector(lambda f:[],lambda f:[(3,4,20,20,.8)])
        self.assertEqual(detector('frame'),[(3,4,20,20,.8)])

if __name__=='__main__': unittest.main()
