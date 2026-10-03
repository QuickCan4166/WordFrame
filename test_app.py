import os
import tempfile
import unittest
import base64
import io
import zipfile
from unittest.mock import patch
from model_setup import ensure_model, MODEL_NAME
from pathlib import Path
os.environ['APPDATA'] = tempfile.mkdtemp(prefix='wordframe-test-')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from core import match_rules
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtTest import QTest
from app import App, CONFIG

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
