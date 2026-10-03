import os
import tempfile
import unittest
from pathlib import Path
os.environ['APPDATA'] = tempfile.mkdtemp(prefix='wordframe-test-')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from core import match_rules
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtTest import QTest
from app import App, CONFIG

class Tests(unittest.TestCase):
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

if __name__ == '__main__':
    unittest.main()
