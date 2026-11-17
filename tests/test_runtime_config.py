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

class RuntimeSettingsTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.path=Path(self.folder.name)/'config_local.json'
        self.saved={f['attr']:getattr(config,f['attr']) for f in runtime_config.SCHEMA}
        self.patch_path=patch.object(runtime_config,'LOCAL_PATH',str(self.path))
        self.patch_path.start()
        self.patch_loaded=patch.object(runtime_config,'_LOADED',False)
        self.patch_loaded.start()

    def tearDown(self):
        for attr,value in self.saved.items(): setattr(config,attr,value)
        self.patch_loaded.stop()
        self.patch_path.stop()
        self.folder.cleanup()

    def test_upstream_settings_help_and_visibility_are_preserved(self):
        field=next(x for x in runtime_config.snapshot()['fields'] if x['key']=='ollama_model')
        self.assertIn('help',field)
        self.assertIn('desc',field)
        self.assertIn('when',field)

    def test_validated_settings_persist_and_reload(self):
        self.path.write_text('{"preserved":"yes"}',encoding='utf-8')
        result=runtime_config.update({'pet_name':'小坦','vad_silence_ms':600,'whisper_model':'base'})
        self.assertFalse(result['errors'])
        self.assertIn('whisper_model',result['restart'])
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['preserved'],'yes')
        config.PET_NAME='临时'
        runtime_config.load()
        self.assertEqual(config.PET_NAME,'小坦')

    def test_invalid_values_do_not_overwrite_configuration(self):
        original=config.VAD_SILENCE_MS
        result=runtime_config.update({'vad_silence_ms':-1,'llm_temperature':float('nan'),'unknown':'x'})
        self.assertEqual(len(result['errors']),3)
        self.assertEqual(config.VAD_SILENCE_MS,original)
        self.assertFalse(self.path.exists())

    def test_secret_is_not_returned_in_snapshot(self):
        runtime_config.update({'doubao_api_key':'test-secret-value'})
        field=next(x for x in runtime_config.snapshot()['fields'] if x['key']=='doubao_api_key')
        self.assertEqual(field['value'],'')
        self.assertNotIn('test-secret',field['masked'])
        runtime_config.update({'doubao_api_key':''})
        self.assertEqual(config.DOUBAO_API_KEY,'test-secret-value')

if __name__=='__main__': unittest.main()
