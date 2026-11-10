import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from petcar.drivers import asr
ROOT = Path(__file__).resolve().parents[1]

class SpeechTests(unittest.TestCase):
    def test_llm_memory_budget_and_reply_are_preserved(self):
        spec=importlib.util.spec_from_file_location('llm_candidate',ROOT/'petcar/core/llm_backends.py')
        llm=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(llm)
        requests_seen=[]
        def post(url,json,timeout):
            requests_seen.append(json)
            return types.SimpleNamespace(raise_for_status=lambda:None,
                        json=lambda:{'message':{'content':'你好，小坦。'}})
        fake=types.SimpleNamespace(post=post)
        with patch.dict(sys.modules,{'requests':fake}), patch.multiple(llm.config,create=True,LLM_NUM_PREDICT=96,LLM_TEMPERATURE=0.7,LLM_TIMEOUT=30):
            backend=llm.OllamaBackend(host='http://example.invalid',model='test')
            self.assertEqual(backend.chat([{'role':'user','content':'你好'}],[])['content'],'你好，小坦。')
        self.assertEqual(requests_seen[0]['options']['num_ctx'],2048)
        self.assertEqual(requests_seen[0]['options']['num_predict'],96)

    def test_fast_command_requires_clear_intent_and_confidence(self):
        def segment(text, confidence=-0.3, noise=0.0):
            return [types.SimpleNamespace(text=text,avg_logprob=confidence,no_speech_prob=noise)]
        self.assertTrue(asr.ASRDriver._clear_fast_command(segment('小坦请摇摇头。')))
        self.assertFalse(asr.ASRDriver._clear_fast_command(segment('不要摇头。')))
        self.assertFalse(asr.ASRDriver._clear_fast_command(segment('请摇摇头。',-1.1)))
        self.assertFalse(asr.ASRDriver._clear_fast_command(segment('请摇摇头。',noise=0.8)))
        self.assertFalse(asr.ASRDriver._clear_fast_command(segment('今天怎么样？')))

    def test_fast_path_and_quality_fallback(self):
        driver=asr.ASRDriver(mode='mock')
        seg=types.SimpleNamespace(text='请摇摇头。',avg_logprob=-0.3,no_speech_prob=0.0)
        calls=[]
        def transcribe(label, segments):
            def run(*args,**kwargs):
                calls.append(label)
                return iter(segments),None
            return run
        driver._fast_model=types.SimpleNamespace(transcribe=transcribe('fast',[seg]))
        driver._model=types.SimpleNamespace(transcribe=transcribe('base',[seg]))
        with patch.multiple(asr.config,create=True,WHISPER_LANG='zh',PET_NAME='小坦'):
            driver._transcribe_audio('sample.wav',2)
            self.assertEqual(calls,['fast'])
            self.assertEqual(driver.last_debug['decoder'],'fast-command')
            calls.clear(); seg.avg_logprob=-1.2
            driver._transcribe_audio('sample.wav',2)
            self.assertEqual(calls,['fast','base'])
            calls.clear()
            driver._transcribe_audio('sample.wav',8)
            self.assertEqual(calls,['base'])

    def test_short_conversation_needs_higher_confidence(self):
        def segment(text, confidence=-0.2):
            return [types.SimpleNamespace(text=text,avg_logprob=confidence,no_speech_prob=0.0)]
        self.assertTrue(asr.ASRDriver._clear_fast_utterance(segment('你好小坦。')))
        self.assertFalse(asr.ASRDriver._clear_fast_utterance(segment('今天怎么样？',-0.8)))
        self.assertFalse(asr.ASRDriver._clear_fast_utterance(segment('小坦小坦小坦。')))
        self.assertFalse(asr.ASRDriver._clear_fast_utterance(segment('不要摇头。')))

    def test_immediate_short_soft_speech_starts(self):
        gate = asr._SpeechGate(0.02, 100, 900)
        self.assertEqual(gate.feed(0.004), 'start')

    def test_quiet_noise_does_not_trigger(self):
        gate = asr._SpeechGate(0.02, 100, 900)
        for rms in [0.0005, 0.0008, 0.001, 0.0006] * 100:
            self.assertEqual(gate.feed(rms), 'waiting')
        self.assertEqual(gate.feed(0.003), 'start')

    def test_speech_does_not_raise_threshold(self):
        gate = asr._SpeechGate(0.02, 200, 900)
        self.assertEqual(gate.feed(0.05), 'waiting')
        self.assertEqual(gate.feed(0.05), 'start')
        self.assertEqual(gate.threshold, 0.003)

    def test_quiet_syllables_and_pause_are_preserved(self):
        gate = asr._SpeechGate(0.02, 100, 900)
        gate.feed(0.01)
        for _ in range(8):
            self.assertEqual(gate.feed(0.0), 'record')
        self.assertEqual(gate.feed(0.0025), 'record')
        for _ in range(8):
            self.assertEqual(gate.feed(0.0), 'record')
        self.assertEqual(gate.feed(0.0), 'done')

    def test_recording_keeps_first_syllable_and_decodes(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('numpy required for synthetic audio integration')
        import wave
        driver = asr.ASRDriver(mode='mock')
        driver.mode = 'whisper'
        decoded = []
        class Model:
            def transcribe(self, path, **kwargs):
                with wave.open(path) as f:
                    first = np.frombuffer(f.readframes(4800), dtype=np.int16)
                    self_test.assertGreater(np.abs(first.astype(float)).mean(), 0)
                decoded.append(kwargs)
                return iter([types.SimpleNamespace(text='你好，小坦', avg_logprob=-0.7)]), None
        self_test = self
        driver._model = Model()
        class Stream:
            def __init__(self, **kwargs):
                self.callback = kwargs['callback']
            def __enter__(self):
                voice = (np.sin(np.arange(4800) * 0.1) * 200).astype(np.int16).reshape(-1,1)
                silence = np.zeros((4800,1), dtype=np.int16)
                for block in [voice] * 4 + [silence] * 10:
                    self.callback(block, 4800, None, None)
            def __exit__(self, *args):
                pass
        sd = types.SimpleNamespace(check_input_settings=lambda **kw: None, InputStream=Stream)
        cfg = dict(VAD_THRESHOLD_MAX=0.02,VAD_SPEECH_MS=100,VAD_SILENCE_MS=900,
                   WHISPER_LANG='zh', PET_NAME='小坦')
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(sys.modules, {'sounddevice': sd}), patch.multiple(asr.config,create=True,**cfg), patch.object(asr.tempfile,'gettempdir',return_value=folder):
                self.assertEqual(driver._listen_whisper(6,force_auto=True),'你好，小坦')
                driver._abort.set()
                self.assertIsNone(driver._listen_whisper(6,force_auto=True))
        self.assertEqual(len(decoded), 1)
        self.assertIn('小坦',decoded[0]['initial_prompt'])


if __name__ == '__main__':
    unittest.main()
