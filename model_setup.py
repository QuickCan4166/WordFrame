"""Download and cache the official lightweight US English Vosk model."""
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

MODEL_NAME = 'vosk-model-small-en-us-0.15'
MODEL_URL = f'https://alphacephei.com/vosk/models/{MODEL_NAME}.zip'


def valid_model(path):
    path = Path(path)
    return (path / 'am' / 'final.mdl').is_file() and (path / 'conf' / 'mfcc.conf').is_file()


def ensure_model(cache, progress=lambda text: None, cancelled=lambda: False):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / MODEL_NAME
    if valid_model(target):
        return str(target)
    with tempfile.TemporaryDirectory(prefix='download-', dir=cache) as temp:
        stage = Path(temp)
        archive = stage / 'model.zip'
        progress('Downloading English speech model (about 40 MB)…')
        request = urllib.request.Request(MODEL_URL, headers={'User-Agent': 'WordFrame/2.0'})
        with urllib.request.urlopen(request, timeout=15) as response, archive.open('wb') as output:
            total = int(response.headers.get('Content-Length', 0))
            received = 0
            while True:
                if cancelled():
                    raise InterruptedError('Model setup cancelled')
                chunk = response.read(128 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > 100 * 1024 * 1024:
                    raise ValueError('Model download exceeds expected size')
                output.write(chunk)
                progress(f'Downloading speech model • {received / 1024 / 1024:.1f} MB' + (f' / {total / 1024 / 1024:.1f} MB' if total else ''))
            if total and received != total:
                raise ValueError('Download was incomplete. Please try again.')
        progress('Extracting speech model…')
        with zipfile.ZipFile(archive) as zipped:
            expanded = 0
            for entry in zipped.infolist():
                if cancelled():
                    raise InterruptedError('Model setup cancelled')
                resolved = (stage / entry.filename).resolve()
                if not resolved.is_relative_to(stage.resolve()) or entry.filename.startswith('/') or '\\' in entry.filename:
                    raise ValueError('Unsafe path in model archive')
                expanded += entry.file_size
                if expanded > 300 * 1024 * 1024:
                    raise ValueError('Model archive is unexpectedly large')
            for entry in zipped.infolist():
                if cancelled():
                    raise InterruptedError('Model setup cancelled')
                zipped.extract(entry, stage)
        extracted = stage / MODEL_NAME
        if not valid_model(extracted):
            raise ValueError('Downloaded model is missing required files')
        if target.exists():
            shutil.rmtree(target)
        extracted.replace(target)
    progress('Speech model ready')
    return str(target)
