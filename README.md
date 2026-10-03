# WordFrame
A dark desktop voice-to-image app with a separate, clean output window for OBS.

## Windows quick start
1. Install 64-bit Python 3.11 or 3.12 from https://www.python.org/downloads/windows/ .
2. Extract this entire ZIP to a folder. Double-click `Start-WordFrame.bat`. First launch installs dependencies and needs internet.
3. Enter a trigger word or phrase, choose a PNG/JPEG/WebP/BMP, choose its duration, and click **Save rule**. Images are copied into your user data folder so moving the original won't break the rule.
4. Type a sentence into the test field and press Enter. No speech model is needed for testing.
5. For microphone detection, download a small model for your language from https://alphacephei.com/vosk/models (for example `vosk-model-small-en-us-0.15`). Extract it, then use **Choose speech model** to select the actual folder containing `am` and `conf`, not its parent. Choose your microphone and click **Start listening**.
6. Click **Open OBS output**. The window title is `WordFrame — OBS Output`.

## OBS virtual camera
1. Add a **Window Capture** source in OBS and select the WordFrame output window. Capture its client area (turn off Capture Cursor; crop any window borders if your capture method includes them).
2. Fit the source to your OBS canvas. Keep the output window open and unminimized. Its initial content area is 960×540, a 16:9 ratio; resizing it changes the output aspect ratio.
3. Click **Start Virtual Camera** in OBS. Select **OBS Virtual Camera** in the receiving application.
4. Optional: choose **Green screen** in WordFrame, then add a Chroma Key filter to its OBS source for an overlay. Black is the default background.
Official guide: https://obsproject.com/kb/virtual-camera-guide

## Behavior
- Case-insensitive whole-word and whole-phrase matching. `cat` won't match `catch`.
- Triggers fire when a completed speech segment is recognized, typically after a short pause. Speech recognition may mishear unusual words, background music, or noise. Speak clearly; use headphones to avoid feedback.
- If several rules match one segment, the last matching phrase wins. At the same starting position, the longer phrase wins.
- A new trigger immediately replaces the current image and restarts its timer. 0 seconds keeps it visible until the next trigger or Clear.
- Fit preserves the full image with letterboxing; Fill crops to fill the window.
- F11 toggles fullscreen in the output window. Escape returns to windowed mode.
- Rules can be edited, disabled, and deleted. Settings and copied images are stored in `%APPDATA%\WordFrame` on Windows (or `~/WordFrame` elsewhere).
- All recognition is local once dependencies and the model are installed. No account or API key; no audio or transcript files are recorded. Transcripts appear in the control window only.
- Static images only; animated GIF playback, screen OCR, and chat monitoring are not included. OBS provides the virtual camera, not WordFrame directly.

## Other systems / developers
Python 3.11–3.12 recommended. `python -m pip install -r requirements.txt`, then `python app.py` from this folder. Linux also needs an operational desktop and PortAudio (often `libportaudio2`).
Run verification with `QT_QPA_PLATFORM=offscreen python test_app.py`.

## Validation
Automated checks cover whole-word/phrase matching, case handling, multiple trigger priority, disabled rules, rule persistence, image loading into both preview and output, and timed clearing. Microphone hardware, model accuracy, Windows launcher, and actual OBS capture must be checked on your own PC.
