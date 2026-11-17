import importlib
from pathlib import Path
import sys
import threading
import time
import types
import unittest
from unittest.mock import patch
from petcar.core import chat_agent as chat_module
from petcar.drivers import tts as tts_module
ROOT=Path(__file__).resolve().parents[1]
def load(name):
    modules={'flask_app':'petcar.api.flask_app','voice_io':'petcar.core.voice_io'}
    return importlib.import_module(modules[name])

class Skills:
    def __init__(self, events):
        self.events = events
    def list_tools_prompt(self): return ''
    def list_tool_specs(self): return []
    def execute(self, name, **args):
        self.events.append(('action', name, args))
        return '完成'

class Backend:
    def __init__(self, calls=()):
        self.calls = list(calls)
    def chat(self, messages, tools):
        if self.calls:
            return {'content':'<reply>好的。</reply>','tool_calls':self.calls.pop(0)}
        return {'content':'<reply>完成了。</reply><emotion>happy</emotion>'}

class DialogueTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.agent = chat_module.ChatAgent(backend=Backend(),skill_manager=Skills(self.events))
    def speak(self, text, emotion='neutral'):
        self.events.append(('speech-start',text))
        self.events.append(('speech-end',text))

    def test_shake_speech_finishes_before_action(self):
        response = self.agent.chat('请摇摇头',before_action=self.speak)
        self.assertEqual(response.reply,'好的，我来摇头。')
        self.assertTrue(response.reply_spoken)
        self.assertEqual([e[0] for e in self.events],['speech-start','speech-end','action'])
        self.assertEqual(self.events[-1][2],{'action':'shake'})

    def test_matching_is_pure_and_other_local_commands_ordered(self):
        self.agent._match_local_command('请点点头')
        self.assertFalse(self.events)
        for phrase in ('点点头','前进','向左看','拍照'):
            self.events.clear()
            self.agent.chat(phrase,before_action=self.speak)
            self.assertEqual([e[0] for e in self.events],['speech-start','speech-end','action'])

    def test_stop_executes_without_waiting_for_speech(self):
        response = self.agent.chat('停止',before_action=self.speak)
        self.assertEqual([e[0] for e in self.events],['action'])
        self.assertFalse(response.reply_spoken)

    def test_local_command_does_not_wait_for_busy_llm(self):
        self.agent._lock.acquire()
        finished = threading.Event()
        def command():
            self.agent.chat('请摇摇头',before_action=self.speak)
            finished.set()
        worker = threading.Thread(target=command,daemon=True)
        worker.start()
        try:
            self.assertTrue(finished.wait(0.5))
        finally:
            self.agent._lock.release()
            worker.join(timeout=1)
        self.assertEqual([e[0] for e in self.events],['speech-start','speech-end','action'])

    def test_speech_failure_does_not_start_action(self):
        def fail(*args): raise RuntimeError('playback failed')
        with self.assertRaises(RuntimeError):
            self.agent.chat('请摇摇头',before_action=fail)
        self.assertEqual(self.events,[])

    def test_model_generated_action_waits_for_speech(self):
        self.agent.backend = Backend([[{'name':'express','arguments':{'action':'shake'}}]])
        self.agent.chat('做一个动作',before_action=self.speak)
        self.assertEqual([e[0] for e in self.events],['speech-start','speech-end','action'])

    def test_weather_is_queried_before_final_answer(self):
        self.agent.backend = Backend([[{'name':'weather','arguments':{'city':'北京'}}]])
        self.agent.chat('北京的天气',before_action=self.speak)
        self.assertEqual([e[0] for e in self.events],['action'])

    def test_tts_cleans_tildes_and_serializes(self):
        driver = tts_module.TTSDriver.__new__(tts_module.TTSDriver)
        driver._speak_lock = threading.Lock()
        driver._stop_requested = threading.Event()
        driver._speaking = threading.Event()
        driver.mode = 'espeak'
        played = []
        def play(text):
            played.append(('start',text))
            time.sleep(0.02)
            played.append(('end',text))
        driver._speak_espeak = play
        threads = [threading.Thread(target=driver.speak,args=(text,)) for text in ('好的，我摇摇头~','你好吗？')]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual([e[0] for e in played],['start','end','start','end'])
        texts = [e[1] for e in played if e[0]=='start']
        self.assertIn('好的，我摇摇头',texts)
        self.assertIn('你好吗？',texts)

    def test_panel_chat_no_duplicate_speech(self):
        if not (ROOT / 'petcar').exists():
            self.skipTest('panel integration requires Raspberry Pi dependencies')
        api = load('flask_app')
        tts = types.SimpleNamespace(speak=self.speak)
        app = api.create_app(chat=self.agent,tts=tts)
        result = app.test_client().get('/api/chat',query_string={'text':'请摇摇头'})
        self.assertEqual(result.status_code,200)
        self.assertEqual([e[0] for e in self.events],['speech-start','speech-end','action'])

    def test_automatic_voice_reply_then_action_once(self):
        if not (ROOT / 'petcar').exists():
            self.skipTest('voice integration requires Raspberry Pi dependencies')
        voice = load('voice_io')
        phrases = iter(['请摇摇头','quit'])
        asr = types.SimpleNamespace(mode='whisper',paused=False,listen=lambda **kw: next(phrases))
        tts = types.SimpleNamespace(speak=self.speak,is_speaking=lambda:False)
        io = voice.VoiceIO(asr=asr,tts=tts,chat=self.agent)
        io._running = True
        with patch.object(voice.time,'sleep'):
            io._loop()
        self.assertEqual([e[0] for e in self.events],['speech-start','speech-end','action'])

    def test_panel_voice_test_reply_then_action_once(self):
        if not (ROOT / 'petcar').exists():
            self.skipTest('voice integration requires Raspberry Pi dependencies')
        api = load('flask_app')
        asr = types.SimpleNamespace(paused=False,abort_listen=lambda:None,
                                    release=lambda:None,last_debug={},
                                    listen=lambda **kw:'请摇摇头')
        app = api.create_app(chat=self.agent,tts=types.SimpleNamespace(speak=self.speak),asr=asr)
        client = app.test_client()
        self.assertEqual(client.post('/api/voice_test').status_code,200)
        deadline = time.monotonic()+2
        while not client.get('/api/voice_test/result').json['done'] and time.monotonic()<deadline:
            time.sleep(0.01)
        self.assertTrue(client.get('/api/voice_test/result').json['done'])
        self.assertEqual([e[0] for e in self.events],['speech-start','speech-end','speech-start','speech-end','action'])

if __name__ == '__main__':
    unittest.main()
