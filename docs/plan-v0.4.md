# Cadux v0.4 — Polish & Capabilities Plan

> **For Hermes:** Implement task-by-task. QR deep link flow is now working.

**Goal:** Add icon, about menu, message metadata, GPS, media support, and TTS to Cadux.

**Current state:** QR → cadux:// intent → config loaded → green dot ✅

---

## Task 1: Custom App Icon

**Objective:** Replace default Flet icon with Cadux-themed icon in Hermes style.

**Files:**
- Create: `assets/icon.png` (1024x1024, Cadux caduceus + Hermes wing motif)
- Modify: `flet build apk` picks it up automatically from assets/

**Verification:** Rebuild, install, check app drawer icon.

---

## Task 2: About / Version Menu

**Objective:** Add version + credits in the navigation drawer.

**Files:** `src/main.py`

**Approach:** Add version text at bottom of drawer. Read version from `pyproject.toml`.

```python
import tomllib
with open("pyproject.toml", "rb") as f:
    _version = tomllib.load(f)["project"]["version"]
# In drawer: ft.Text(f"Cadux v{_version}", size=11, color=ft.Colors.OUTLINE)
```

---

## Task 3: Message Metadata Tagging

**Objective:** Tag outgoing messages so Hermes knows they come from Cadux and can adjust response style.

**Files:** `src/ws_client.py`

**Current payload:**
```python
{"message": text}
```

**New payload:**
```python
{
    "message": text,
    "metadata": {
        "source": "cadux",
        "version": "0.3.0",
        "capabilities": {
            "tts": True,        # read aloud supported
            "display_width": 360,  # approximate char width
            "images": True,     # can display images
            "voice_input": True # voice-to-text active
        },
        "gps": {"lat": None, "lng": None, "accuracy": "none"}
    }
}
```

---

## Task 4: GPS Location Support

**Objective:** Allow Cadux to send location with messages.

**Files:** `src/chat_ui.py`, `src/ws_client.py`, `src/main.py`

**Approach:**
- Settings: GPS mode: `none | general (~city) | precise`
- First use: system permission prompt
- Use Flet `geolocator` or platform channels
- Attach to message metadata

**Verification:** "Find a coffee shop near me" → Hermes receives GPS.

---

## Task 5: Media Support (Images, Documents, URLs)

**Objective:** Send images (camera/gallery), document files, and URLs.

**Files:** `src/chat_ui.py`, `src/ws_client.py`

**Approach:**
- Input bar: add camera 📷 and attachment 📎 buttons
- Camera: Flet `ImageCapture` or file picker with camera source
- Documents: file picker
- URLs: auto-detected in text input
- Send as multipart or base64 in message metadata

---

## Task 6: Voice-to-Text (Audio Input)

**Objective:** Record and transcribe voice messages on-device or via Hermes.

**Approach:**
- First pass: send audio file to Hermes API for transcription
- Later: on-device transcription via Android speech recognition
- Toggle in input bar: 🎤 button

---

## Task 7: Text-to-Speech (Cadux Reads Aloud)

**Objective:** Cadux speaks responses aloud.

**Approach:**
- Use Android TTS engine (Flet/Flutter plugin)
- Toggle in drawer or per-message
- Metadata sent so Hermes avoids complex formatting when TTS is on
