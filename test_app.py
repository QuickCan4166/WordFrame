import os
import tempfile
import unittest
import base64
import io
import zipfile
from unittest.mock import patch
from types import SimpleNamespace
import json
from model_setup import ensure_model, MODEL_NAME
from pathlib import Path
os.environ['APPDATA'] = tempfile.mkdtemp(prefix='wordframe-test-')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from core import match_rules, alternatives, LiveMatcher
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtTest import QTest
from app import App, CONFIG, Listener

class Tests(unittest.TestCase):
    def setUp(self):
        CONFIG.unlink(missing_ok=True)
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
    def test_matching(self):
        cat = dict(word='cat')
        phrase = dict(word='hello world')
        self.assertIsNone(match_rules('catch caterpillar', [cat]))
        self.assertEqual(match_rules('A CAT!', [cat]), cat)
        self.assertEqual(match_rules('hello, WORLD', [phrase]), phrase)
        self.assertIsNone(match_rules('cat', [dict(word='cat', enabled=False)]))
        self.assertEqual(match_rules('cat hello world', [cat, phrase]), phrase)
        self.assertEqual(match_rules('hello world', [dict(word='hello'), phrase]), phrase)
    def test_comma_alternatives(self):
        rule = dict(word='Hello, hi, greetings, good morning')
        for text in ['hello!', 'HI there', 'greetings everyone', 'a good morning to you']:
            self.assertEqual(match_rules(text, [rule]), rule)
        self.assertIsNone(match_rules('high morning', [rule]))
        self.assertEqual(alternatives(' hello, , HI '), [('hello',), ('hi',)])
    def test_live_multiple_occurrences_and_final(self):
        rules = [dict(word='hello, hi'), dict(word='cat'), dict(word='good morning')]
        matcher = LiveMatcher()
        self.assertEqual([h.rule_index for h in matcher.feed('hello', rules)], [0])
        self.assertEqual(matcher.feed('hello', rules), [])
        self.assertEqual([h.rule_index for h in matcher.feed('hello cat', rules)], [1])
        self.assertEqual([h.rule_index for h in matcher.feed('hello cat hi good', rules)], [0])
        self.assertEqual([h.rule_index for h in matcher.feed('hello cat hi good morning', rules)], [2])
        self.assertEqual(matcher.feed('hello cat hi good morning', rules, final=True), [])
        self.assertEqual([h.rule_index for h in matcher.feed('hello', rules)], [0])
        self.assertEqual([h.rule_index for h in matcher.feed('hello hello', rules)], [0])
    def test_live_revisions_and_final_only(self):
        matcher = LiveMatcher()
        rules = [dict(word='hello'), dict(word='cat')]
        self.assertEqual(len(matcher.feed('hello', rules)), 1)
        self.assertEqual(matcher.feed('well hello', rules), [])
        self.assertEqual(matcher.feed('well hello there', rules), [])
        hits = matcher.feed('well hello there cat', rules, final=True)
        self.assertEqual([h.rule_index for h in hits], [1])
        self.assertEqual([h.rule_index for h in matcher.feed('hello cat hello', rules, final=True)], [0, 1, 0])
        matcher.feed('hello', rules)
        matcher.feed('', rules, final=True)
        self.assertEqual(len(matcher.feed('hello', rules)), 1)
    def test_listener_emits_partial_and_final(self):
        worker = Listener('mock-model', None)
        received = []
        worker.transcript.connect(lambda text, final: received.append((text, final)))
        class Stream:
            def __init__(self, **kwargs):
                self.callback = kwargs['callback']
                self.blocksize = kwargs['blocksize']
                self.assert_blocksize = self.blocksize == 800
            def __enter__(self):
                for _ in range(3):
                    self.callback(b'audio', 800, None, None)
                return self
            def __exit__(self, *args): pass
        class Recognizer:
            def __init__(self, *args): self.step = 0
            def AcceptWaveform(self, chunk):
                self.step += 1
                return self.step == 3
            def PartialResult(self):
                return json.dumps({'partial': 'hello' if self.step == 1 else 'hello cat'})
            def Result(self):
                worker.requestInterruption()
                # Direct run() isn't a running QThread; stop the loop via a test-controlled flag.
                worker.isInterruptionRequested = lambda: True
                return json.dumps({'text': 'hello cat'})
        sd = SimpleNamespace(query_devices=lambda *args: {'default_samplerate': 16000}, RawInputStream=Stream)
        vosk = SimpleNamespace(Model=lambda path: object(), KaldiRecognizer=Recognizer, SetLogLevel=lambda level: None)
        with patch.dict('sys.modules', {'sounddevice': sd, 'vosk': vosk}):
            worker.run()
        self.assertEqual(received, [('hello', False), ('hello cat', False), ('hello cat', True)])
    def test_live_display_no_timer_restart(self):
        app = App()
        paths = []
        for color in ['red', 'blue']:
            path = Path(os.environ['APPDATA']) / (color + '.png')
            image = QPixmap(10, 10); image.fill(QColor(color)); image.save(str(path))
            paths.append(str(path))
        app.rules = [dict(word='hello, hi', image=paths[0], duration=2), dict(word='cat', image=paths[1], duration=2)]
        app.detect_live('hello', False)
        self.assertEqual(app.output.pixmap.toImage().pixelColor(0, 0).name(), '#ff0000')
        QTest.qWait(100)
        remaining = app.timer.remainingTime()
        app.detect_live('hello there', False)
        self.assertLessEqual(app.timer.remainingTime(), remaining)
        app.detect_live('hello there cat', False)
        self.assertEqual(app.output.pixmap.toImage().pixelColor(0, 0).name(), '#0000ff')
        app.detect_live('hello there cat hi', False)
        self.assertEqual(app.output.pixmap.toImage().pixelColor(0, 0).name(), '#ff0000')
        app.detect_live('hello there cat hi', True)
        app.close()
    def test_display_save_clear(self):
        app = App()
        imagepath = Path(os.environ['APPDATA']) / 'test.png'
        image = QPixmap(100, 100)
        image.fill(QColor('red'))
        self.assertTrue(image.save(str(imagepath)))
        app.word.setText('hello')
        app.image_path = str(imagepath)
        app.duration.setValue(1)
        app.save_rule()
        self.assertEqual(len(app.rules), 1)
        self.assertTrue(CONFIG.exists())
        app.detect('well hello there')
        self.assertFalse(app.output.pixmap.isNull())
        self.assertFalse(app.preview.pixmap.isNull())
        QTest.qWait(1200)
        self.assertTrue(app.output.pixmap.isNull())
        app.duration.setValue(0)
        app.save_rule()
        app.detect('hello')
        self.assertFalse(app.timer.isActive())
        app.clear_output()
        self.assertTrue(app.preview.pixmap.isNull())
        app.close()
        restored = App()
        self.assertEqual(restored.rules[0]['word'], 'hello')
        restored.close()

class FeatureTests(unittest.TestCase):
    def setUp(self):
        CONFIG.unlink(missing_ok=True)
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
    def test_gif_idle_and_trigger(self):
        gif = Path(os.environ['APPDATA']) / 'animated.gif'
        gif.write_bytes(base64.b64decode('R0lGODlhCgAKAIEAAP8AAAAAAAAAAAAAACH/C05FVFNDQVBFMi4wAwEAAAAh+QQACgAAACwAAAAACgAKAAAIEgABCBxIsKDBgwgTKlzIsGHCgAAh+QQBCgABACwAAAAACgAKAIEAAP8AAAAAAAAAAAAIEgABCBxIsKDBgwgTKlzIsGHCgAA7'))
        app = App()
        app.idle_path = str(gif)
        app.show_idle()
        self.assertIsNotNone(app.movie)
        QTest.qWait(30)
        first = app.output.pixmap.toImage().pixelColor(0, 0).name()
        QTest.qWait(100)
        second = app.output.pixmap.toImage().pixelColor(0, 0).name()
        self.assertNotEqual(first, second)
        self.assertEqual(app.preview.pixmap.cacheKey(), app.output.pixmap.cacheKey())
        imagepath = Path(os.environ['APPDATA']) / 'trigger.png'
        image = QPixmap(10, 10); image.fill(QColor('green')); image.save(str(imagepath))
        app.rules = [dict(word='test', image=str(imagepath), duration=1)]
        app.detect('test')
        self.assertIsNone(app.movie)
        QTest.qWait(1200)
        self.assertIsNotNone(app.movie)
        app.rules[0]['image'] = str(gif)
        app.detect('test')
        self.assertIsNotNone(app.movie)
        app.persist(); app.close()
        loaded = App()
        self.assertEqual(loaded.idle_path, str(gif))
        self.assertIsNotNone(loaded.movie)
        loaded.remove_idle()
        self.assertTrue(loaded.output.pixmap.isNull())
        loaded.close()
    def archive(self, malicious=False):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as z:
            z.writestr(MODEL_NAME+'/am/final.mdl', b'model fixture')
            z.writestr(MODEL_NAME+'/conf/mfcc.conf', b'configuration fixture')
            if malicious:
                z.writestr('../escape', b'unsafe')
        return data.getvalue()
    def response(self, content):
        result = io.BytesIO(content)
        result.headers = {'Content-Length': str(len(content))}
        return result
    def test_model_install_and_cache(self):
        with tempfile.TemporaryDirectory() as cache:
            with patch('model_setup.urllib.request.urlopen', return_value=self.response(self.archive())) as fetch:
                model = ensure_model(cache)
                self.assertTrue((Path(model)/'am/final.mdl').exists())
                self.assertEqual(ensure_model(cache), model)
                self.assertEqual(fetch.call_count, 1)
    def test_download_failure_and_cancel(self):
        with tempfile.TemporaryDirectory() as cache:
            with patch('model_setup.urllib.request.urlopen', side_effect=OSError('offline')):
                with self.assertRaises(OSError): ensure_model(cache)
            self.assertEqual(list(Path(cache).iterdir()), [])
            with patch('model_setup.urllib.request.urlopen', return_value=self.response(self.archive())):
                with self.assertRaises(InterruptedError): ensure_model(cache, cancelled=lambda: True)
            self.assertEqual(list(Path(cache).iterdir()), [])
    def test_unsafe_archive(self):
        with tempfile.TemporaryDirectory() as cache:
            with patch('model_setup.urllib.request.urlopen', return_value=self.response(self.archive(True))):
                with self.assertRaises(ValueError): ensure_model(cache)
            self.assertEqual(list(Path(cache).iterdir()), [])

if __name__ == '__main__':
    unittest.main()
