import json
import os
import queue
import shutil
import sys
import uuid
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QLineEdit, QFileDialog, QSpinBox,
    QComboBox, QListWidget, QCheckBox, QMessageBox, QFrame)
from core import match_rules

DATA = Path(os.getenv('APPDATA') or Path.home()) / 'WordFrame'
DATA.mkdir(parents=True, exist_ok=True)
(DATA / 'images').mkdir(exist_ok=True)
CONFIG = DATA / 'settings.json'

STYLE = '''
QWidget { background: #101117; color: #e9eaf2; font-family: 'Segoe UI'; font-size: 13px; }
QLabel#title { font-size: 30px; font-weight: 700; }
QLabel#muted { color: #9397ad; }
QFrame#card { background: #191b25; border: 1px solid #2b2e3f; border-radius: 14px; }
QFrame#card QLabel { background: transparent; }
QPushButton { background: #292c3e; border: 1px solid #363a51; border-radius: 8px; padding: 11px 16px; font-weight: 600; }
QPushButton:hover { background: #383d56; }
QPushButton#primary { background: #7960ef; border: 1px solid #9a86ff; }
QPushButton#primary:hover { background: #8c76f7; }
QPushButton:disabled { color: #62677b; background: #202230; }
QLineEdit, QComboBox, QSpinBox { background: #11131b; border: 1px solid #34384e; border-radius: 7px; padding: 9px; }
QLineEdit:focus { border: 1px solid #9a86ff; }
QListWidget { background: #141620; border: 1px solid #303348; border-radius: 9px; padding: 5px; }
QListWidget::item { padding: 14px; border-radius: 7px; }
QListWidget::item:selected { background: #353052; }
QCheckBox { spacing: 8px; }
'''

class Canvas(QWidget):
    def __init__(self):
        super().__init__()
        self.pixmap = QPixmap()
        self.background = '#000000'
        self.fit = 'Fit'
        self.setMinimumSize(240, 135)
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(self.background))
        if not self.pixmap.isNull():
            mode = Qt.AspectRatioMode.KeepAspectRatio if self.fit == 'Fit' else Qt.AspectRatioMode.KeepAspectRatioByExpanding
            scaled = self.pixmap.scaled(self.size(), mode, Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap((self.width()-scaled.width())//2, (self.height()-scaled.height())//2, scaled)

class Output(Canvas):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('WordFrame — OBS Output')
        self.resize(960, 540)
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F11:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
        elif event.key() == Qt.Key.Key_Escape:
            self.showNormal()

class Listener(QThread):
    transcript = Signal(str)
    status = Signal(str)
    failure = Signal(str)
    def __init__(self, model, device):
        super().__init__()
        self.model_path, self.device = model, device
    def run(self):
        try:
            import sounddevice as sd
            from vosk import Model, KaldiRecognizer, SetLogLevel
            SetLogLevel(-1)
            self.status.emit('Loading speech model…')
            model = Model(self.model_path)
            if self.isInterruptionRequested():
                return
            rate = int(sd.query_devices(self.device, 'input')['default_samplerate'])
            recognizer = KaldiRecognizer(model, rate)
            audio = queue.Queue(maxsize=32)
            def callback(data, frames, timing, status):
                try:
                    audio.put_nowait(bytes(data))
                except queue.Full:
                    pass
            with sd.RawInputStream(samplerate=rate, blocksize=4000, device=self.device,
                                   dtype='int16', channels=1, callback=callback):
                self.status.emit('Listening • microphone active')
                while not self.isInterruptionRequested():
                    try:
                        chunk = audio.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if recognizer.AcceptWaveform(chunk):
                        text = json.loads(recognizer.Result()).get('text', '')
                        if text:
                            self.transcript.emit(text)
        except Exception as error:
            self.failure.emit(str(error))

class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('WordFrame | Voice to visual')
        self.resize(1080, 760)
        self.rules, self.worker = [], None
        self.image_path = ''
        self.output = Output()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.clear_output)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        header = QHBoxLayout()
        titlebox = QVBoxLayout()
        titlebox.addWidget(self.label('WordFrame', 'title'))
        titlebox.addWidget(self.label('YOUR VOICE. A NEW VISUAL.', 'muted'))
        header.addLayout(titlebox)
        header.addStretch()
        header.addWidget(self.button('Open OBS output ↗', self.open_output, True))
        layout.addLayout(header)
        columns = QHBoxLayout()
        layout.addLayout(columns, 1)
        left = self.card(columns)
        left.addWidget(self.label('01 / IMAGE RULES', 'muted'))
        self.rule_list = QListWidget()
        self.rule_list.currentRowChanged.connect(self.select_rule)
        left.addWidget(self.rule_list, 1)
        self.word = QLineEdit()
        self.word.setPlaceholderText('Trigger word or phrase, e.g. hello')
        left.addWidget(self.word)
        self.file_label = self.label('No image selected', 'muted')
        left.addWidget(self.file_label)
        left.addWidget(self.button('Choose image…', self.choose_image))
        settings = QHBoxLayout()
        self.duration = QSpinBox()
        self.duration.setRange(0, 3600)
        self.duration.setSuffix(' sec')
        self.duration.setValue(5)
        self.enabled = QCheckBox('Enabled')
        self.enabled.setChecked(True)
        settings.addWidget(self.label('Display time'))
        settings.addWidget(self.duration)
        settings.addWidget(self.enabled)
        left.addLayout(settings)
        left.addWidget(self.label('0 seconds keeps the image until the next trigger.', 'muted'))
        actions = QHBoxLayout()
        actions.addWidget(self.button('Save rule', self.save_rule, True))
        actions.addWidget(self.button('New', self.new_rule))
        actions.addWidget(self.button('Delete', self.delete_rule))
        left.addLayout(actions)
        right = self.card(columns)
        right.addWidget(self.label('02 / LIVE OUTPUT', 'muted'))
        self.preview = Canvas()
        self.preview.setMinimumSize(380, 214)
        right.addWidget(self.preview, 1)
        viewopts = QHBoxLayout()
        self.fit = QComboBox()
        self.fit.addItems(['Fit', 'Fill'])
        self.fit.currentTextChanged.connect(self.view_changed)
        self.bg = QComboBox()
        self.bg.addItems(['Black', 'Green screen'])
        self.bg.currentTextChanged.connect(self.view_changed)
        viewopts.addWidget(self.fit)
        viewopts.addWidget(self.bg)
        viewopts.addWidget(self.button('Clear', self.clear_output))
        right.addLayout(viewopts)
        right.addWidget(self.label('03 / DETECTION', 'muted'))
        self.model = QLineEdit()
        self.model.setPlaceholderText('Select an extracted Vosk model folder')
        right.addWidget(self.model)
        right.addWidget(self.button('Choose speech model…', self.choose_model))
        self.devices = QComboBox()
        self.refresh_devices()
        right.addWidget(self.devices)
        controls = QHBoxLayout()
        self.listen_button = self.button('Start listening', self.toggle_listening, True)
        controls.addWidget(self.listen_button)
        controls.addWidget(self.button('Refresh mics', self.refresh_devices))
        right.addLayout(controls)
        self.test = QLineEdit()
        self.test.setPlaceholderText('Type a sentence and press Enter to test')
        self.test.returnPressed.connect(lambda: self.detect(self.test.text()))
        right.addWidget(self.test)
        self.heard = self.label('Transcript will appear here', 'muted')
        self.heard.setWordWrap(True)
        right.addWidget(self.heard)
        self.status = self.label('Ready • speech stays on your computer', 'muted')
        layout.addWidget(self.status)
        self.load()
    def label(self, text, name=''):
        widget = QLabel(text)
        widget.setObjectName(name)
        return widget
    def button(self, text, fn, primary=False):
        widget = QPushButton(text)
        if primary:
            widget.setObjectName('primary')
        widget.clicked.connect(fn)
        return widget
    def card(self, parent):
        frame = QFrame()
        frame.setObjectName('card')
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        parent.addWidget(frame, 1)
        return layout
    def notify(self, text):
        self.status.setText(text)
    def refresh_devices(self):
        self.devices.clear()
        self.devices.addItem('Default microphone', None)
        try:
            import sounddevice as sd
            for i, device in enumerate(sd.query_devices()):
                if device['max_input_channels']:
                    self.devices.addItem(device['name'], i)
        except Exception:
            self.devices.setToolTip('Microphone discovery unavailable. Install requirements and check audio devices.')
    def choose_model(self):
        path = QFileDialog.getExistingDirectory(self, 'Choose extracted Vosk model')
        if path:
            self.model.setText(path)
            self.persist()
    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose image', '', 'Images (*.png *.jpg *.jpeg *.webp *.bmp)')
        if path:
            if QPixmap(path).isNull():
                QMessageBox.warning(self, 'Invalid image', 'This image could not be opened.')
                return
            self.image_path = path
            self.file_label.setText(Path(path).name)
    def new_rule(self):
        self.rule_list.setCurrentRow(-1)
        self.word.clear()
        self.image_path = ''
        self.file_label.setText('No image selected')
        self.duration.setValue(5)
        self.enabled.setChecked(True)
    def select_rule(self, index):
        if 0 <= index < len(self.rules):
            rule = self.rules[index]
            self.word.setText(rule['word'])
            self.image_path = rule['image']
            self.file_label.setText(Path(self.image_path).name)
            self.duration.setValue(rule['duration'])
            self.enabled.setChecked(rule.get('enabled', True))
    def refresh_rules(self, selected=-1):
        self.rule_list.blockSignals(True)
        self.rule_list.clear()
        for rule in self.rules:
            self.rule_list.addItem(f"{'●' if rule.get('enabled', True) else '○'}  {rule['word']}    ·    {rule['duration']}s")
        self.rule_list.blockSignals(False)
        self.rule_list.setCurrentRow(selected)
    def save_rule(self):
        word = self.word.text().strip()
        from core import tokens
        if not tokens(word) or not self.image_path or QPixmap(self.image_path).isNull():
            QMessageBox.warning(self, 'Rule needs details', 'Enter a word or phrase and choose a readable image.')
            return
        index = self.rule_list.currentRow()
        if any(tokens(r['word']) == tokens(word) for i, r in enumerate(self.rules) if i != index):
            QMessageBox.warning(self, 'Duplicate trigger', 'A rule already uses this trigger.')
            return
        source = Path(self.image_path)
        if source.parent != DATA / 'images':
            destination = DATA / 'images' / (uuid.uuid4().hex + source.suffix.lower())
            shutil.copy2(source, destination)
            self.image_path = str(destination)
        rule = dict(word=word, image=self.image_path, duration=self.duration.value(), enabled=self.enabled.isChecked())
        if index >= 0:
            self.rules[index] = rule
        else:
            self.rules.append(rule)
            index = len(self.rules)-1
        self.persist()
        self.refresh_rules(index)
        self.notify('Rule saved • test it with a sentence below')
    def delete_rule(self):
        index = self.rule_list.currentRow()
        if index >= 0:
            self.rules.pop(index)
            self.persist()
            self.refresh_rules()
            self.new_rule()
    def view_changed(self):
        for canvas in (self.output, self.preview):
            canvas.fit = self.fit.currentText()
            canvas.background = '#00ff00' if self.bg.currentIndex() else '#000000'
            canvas.update()
        self.persist()
    def open_output(self):
        self.output.show()
        self.output.raise_()
    def clear_output(self):
        self.timer.stop()
        for canvas in (self.output, self.preview):
            canvas.pixmap = QPixmap()
            canvas.update()
    def detect(self, text):
        self.heard.setText('Heard: ' + text)
        rule = match_rules(text, self.rules)
        if not rule:
            self.notify('No matching rule in this sentence')
            return
        image = QPixmap(rule['image'])
        if image.isNull():
            self.notify('Image is missing or unreadable • choose it again')
            return
        for canvas in (self.output, self.preview):
            canvas.pixmap = image
            canvas.update()
        self.timer.stop()
        if rule['duration']:
            self.timer.start(rule['duration']*1000)
        self.notify('Triggered: ' + rule['word'])
    def toggle_listening(self):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.listen_button.setEnabled(False)
            self.notify('Stopping microphone…')
            return
        path = self.model.text().strip()
        if not (Path(path)/'am').is_dir():
            QMessageBox.warning(self, 'Speech model required', 'Download and extract a Vosk model, then select its folder containing am and conf. See README for the download link.')
            return
        self.worker = Listener(path, self.devices.currentData())
        self.worker.transcript.connect(self.detect)
        self.worker.status.connect(self.notify)
        self.worker.failure.connect(lambda error: self.notify('Microphone error: ' + error))
        self.worker.finished.connect(self.stopped)
        self.listen_button.setText('Stop listening')
        self.devices.setEnabled(False)
        self.worker.start()
        self.persist()
    def stopped(self):
        self.listen_button.setText('Start listening')
        self.listen_button.setEnabled(True)
        self.devices.setEnabled(True)
    def persist(self):
        settings = dict(rules=self.rules, model=self.model.text(), fit=self.fit.currentText(), background=self.bg.currentText())
        temp = CONFIG.with_suffix('.tmp')
        try:
            temp.write_text(json.dumps(settings, indent=2), encoding='utf-8')
            temp.replace(CONFIG)
        except OSError as error:
            self.notify('Could not save settings: ' + str(error))
    def load(self):
        try:
            settings = json.loads(CONFIG.read_text(encoding='utf-8'))
            self.rules = [r for r in settings.get('rules', []) if isinstance(r, dict) and all(k in r for k in ('word', 'image', 'duration')) and isinstance(r['word'], str) and isinstance(r['image'], str) and isinstance(r['duration'], int) and 0 <= r['duration'] <= 3600]
            self.model.setText(settings.get('model', ''))
            self.fit.setCurrentText(settings.get('fit', 'Fit'))
            self.bg.setCurrentText(settings.get('background', 'Black'))
            self.refresh_rules()
        except FileNotFoundError:
            pass
        except (ValueError, TypeError, OSError):
            self.notify('Settings could not be loaded. Add your rules again.')
    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.notify('Stopping microphone before closing…')
            event.ignore()
            QTimer.singleShot(200, self.close)
            return
        self.persist()
        self.output.close()
        event.accept()

if __name__ == '__main__':
    application = QApplication(sys.argv)
    application.setStyle('Fusion')
    application.setStyleSheet(STYLE)
    window = App()
    window.show()
    sys.exit(application.exec())
