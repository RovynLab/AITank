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

class ExpressionTests(unittest.TestCase):
    def render(self,name):
        img=Image.new('1',(W,H),0)
        _draw_face(ImageDraw.Draw(img),EXPRESSIONS[name])
        return img

    def test_all_faces_render_and_thinking_is_distinct(self):
        for name in EXPRESSIONS: self.assertIsNotNone(self.render(name).getbbox())
        difference=ImageChops.difference(self.render('thinking'),self.render('confused'))
        self.assertGreater(sum(difference.getdata()),100)

    def test_confused_keeps_two_complete_round_eyes(self):
        image=self.render('confused')
        crops=[image.crop((x-8,EYE_CY-8,x+9,EYE_CY+9)) for x in (EYE_L_CX,EYE_R_CX)]
        self.assertEqual(crops[0].getbbox(),(0,0,17,17))
        self.assertIsNone(ImageChops.difference(*crops).getbbox())

    def test_thinking_overlay_never_replaces_laugh_eyes(self):
        class Capture:
            def show_custom_face(self,face,offset_y=0): self.face=face
        capture=Capture()
        engine=EmotionEngine(capture)
        engine.set_emotion('laugh')
        engine.start_think()
        for frame in range(8):
            engine._anim_frame=frame
            engine._render()
            self.assertEqual(capture.face['left_eye'],'arc')
            self.assertEqual(capture.face['right_eye'],'arc')

if __name__=='__main__': unittest.main()
