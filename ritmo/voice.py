"""
ritmo/voice.py
==============
RITMO Voice Mode — Always-listening speech I/O loop.
Completely terminal-based, no ports needed.

STT options (pick at runtime):
  A — Google Web Speech (free, online, no key)
  B — Vosk              (100% offline, ~40MB model)
  C — Manual (keyboard) — type instead of speaking

TTS:
  edge-tts → async → saves temp MP3 → pygame plays it

Works standalone:
  python ritmo/voice.py
or via interface.py mode 3 → sub-mode 3.
"""

import os
import sys
import asyncio
import tempfile
import threading
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# ── ANSI (minimal, no dependency on ritmocli) ─────────────────────────────────
_RESET   = "\x1b[0m"
_TEAL    = "\x1b[38;5;43m"
_CYAN    = "\x1b[36;1m"
_GREEN   = "\x1b[32;1m"
_YELLOW  = "\x1b[33;1m"
_RED     = "\x1b[31;1m"
_WHITE   = "\x1b[97;1m"
_DIM     = "\x1b[2m"
_MAGENTA = "\x1b[35;1m"

def _t(col, txt): return f"{col}{txt}{_RESET}"
def teal(t):    return _t(_TEAL,    t)
def cyan(t):    return _t(_CYAN,    t)
def green(t):   return _t(_GREEN,   t)
def yellow(t):  return _t(_YELLOW,  t)
def red(t):     return _t(_RED,     t)
def white(t):   return _t(_WHITE,   t)
def dim(t):     return _t(_DIM,     t)
def magenta(t): return _t(_MAGENTA, t)


# ─────────────────────────────────────────────────────────────────────────────
#  DEPENDENCY AUTO-INSTALLER
# ─────────────────────────────────────────────────────────────────────────────

def _pip_install(*pkgs):
    import subprocess
    print(yellow(f"  [VOICE] Installing: {' '.join(pkgs)}..."))
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", *pkgs, "--quiet"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    print(green(f"  [VOICE] Installed: {' '.join(pkgs)}"))


def _ensure_edge_tts():
    try:
        import edge_tts
        return True
    except ImportError:
        _pip_install("edge-tts")
        return True


def _ensure_pygame():
    try:
        import pygame
        return True
    except ImportError:
        _pip_install("pygame")
        return True


def _ensure_speech_recognition():
    try:
        import speech_recognition
        return True
    except ImportError:
        _pip_install("SpeechRecognition", "PyAudio")
        return True


def _ensure_vosk():
    try:
        import vosk
        return True
    except ImportError:
        _pip_install("vosk")
        return True


# ─────────────────────────────────────────────────────────────────────────────
#  TTS — edge-tts + pygame playback
# ─────────────────────────────────────────────────────────────────────────────

VOICE_NAME = "en-IN-NeerjaNeural"   # Indian English female


async def _speak_async(text: str):
    _ensure_edge_tts()
    _ensure_pygame()
    import edge_tts
    import pygame

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tmp_path = f.name

    try:
        communicate = edge_tts.Communicate(text, VOICE_NAME)
        await communicate.save(tmp_path)

        pygame.mixer.init()
        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(80)
        pygame.mixer.music.unload()
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def speak(text: str):
    """Speak `text` aloud using edge-tts. Blocks until playback finishes."""
    if not text or not text.strip():
        return
    # Truncate very long replies before speaking (keep first 2 sentences)
    sentences = text.replace("—", ".").split(".")
    short = ". ".join(s.strip() for s in sentences[:2] if s.strip())
    asyncio.run(_speak_async(short or text[:160]))


# ─────────────────────────────────────────────────────────────────────────────
#  STT — Google / Vosk / Manual
# ─────────────────────────────────────────────────────────────────────────────

class _GoogleSTT:
    """Online STT via Google Web Speech API (free, no key)."""
    name = "Google Web Speech"
    label = "A — Google Web Speech  (online, free, no API key)"

    def __init__(self):
        _ensure_speech_recognition()
        import speech_recognition as sr
        self._sr = sr
        self._r  = sr.Recognizer()

    def listen(self, timeout=6, phrase_limit=15) -> str:
        """Record from mic, return recognised text. Raises sr exceptions on failure."""
        sr = self._sr
        with sr.Microphone() as src:
            self._r.adjust_for_ambient_noise(src, duration=0.3)
            print(dim("  🎤  Speak now..."))
            audio = self._r.listen(src, timeout=timeout, phrase_time_limit=phrase_limit)
        text = self._r.recognize_google(audio)
        return text


class _VoskSTT:
    """Offline STT via Vosk (40MB model auto-downloaded)."""
    name = "Vosk Offline"
    label = "B — Vosk Offline STT   (no internet, ~40MB model download)"
    MODEL_DIR = ROOT_DIR / "data" / "vosk-model"

    def __init__(self):
        _ensure_vosk()
        import vosk
        import json
        if not self.MODEL_DIR.exists():
            self._download_model()
        self._model = vosk.Model(str(self.MODEL_DIR))
        self._json = json

    def _download_model(self):
        import urllib.request, zipfile
        MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
        zip_path = ROOT_DIR / "data" / "vosk-model.zip"
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        print(yellow("  [VOSK] Downloading ~40MB model (one-time)..."))
        urllib.request.urlretrieve(MODEL_URL, zip_path)
        print(yellow("  [VOSK] Extracting..."))
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(zip_path.parent)
        # Rename extracted folder
        for d in zip_path.parent.iterdir():
            if d.is_dir() and "vosk-model" in d.name and d != self.MODEL_DIR:
                d.rename(self.MODEL_DIR)
                break
        zip_path.unlink(missing_ok=True)
        print(green("  [VOSK] Model ready."))

    def listen(self, timeout=6, phrase_limit=15) -> str:
        import vosk
        try:
            import sounddevice as sd
        except ImportError:
            _pip_install("sounddevice")
            import sounddevice as sd

        RATE = 16000
        CHUNK = 4096
        rec = vosk.KaldiRecognizer(self._model, RATE)

        print(dim("  🎤  Speak now... (Vosk)"))
        frames = []
        silence_count = 0
        started = False

        def _cb(indata, f, t, s):
            nonlocal silence_count, started
            data = bytes(indata)
            frames.append(data)
            if rec.AcceptWaveform(data):
                started = True
            silence_count += 1

        with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16",
                               blocksize=CHUNK, callback=_cb):
            deadline = time.time() + timeout
            while time.time() < deadline:
                time.sleep(0.1)
                if started and silence_count > 20:
                    break

        all_audio = b"".join(frames)
        rec.AcceptWaveform(all_audio)
        result = self._json.loads(rec.FinalResult())
        text = result.get("text", "").strip()
        if not text:
            raise ValueError("No speech detected")
        return text


class _ManualSTT:
    """Keyboard fallback — user types instead of speaking."""
    name = "Manual (keyboard)"
    label = "C — Manual Keyboard    (type instead of speaking)"

    def listen(self, timeout=60, phrase_limit=None) -> str:
        try:
            text = input(cyan("  You  ▸  ")).strip()
        except EOFError:
            text = "quit"
        if not text:
            raise ValueError("Empty input")
        return text


_STT_OPTIONS = {
    "A": _GoogleSTT,
    "B": _VoskSTT,
    "C": _ManualSTT,
}


def pick_stt_engine() -> object:
    """Let user pick STT engine at startup."""
    print()
    print(teal("  ╔══════════════════════════════════════════════════════╗"))
    print(teal("  ║") + white("   RITMO Voice — Select STT Engine                   ") + teal("║"))
    print(teal("  ╚══════════════════════════════════════════════════════╝"))
    print()
    for key, cls in _STT_OPTIONS.items():
        print(f"    {cyan(key)}  {cls.label}")
    print()
    while True:
        try:
            choice = input(white("  Choose [A/B/C]: ")).strip().upper() or "A"
        except (KeyboardInterrupt, EOFError):
            print(); sys.exit(0)
        if choice in _STT_OPTIONS:
            cls = _STT_OPTIONS[choice]
            print(green(f"  [OK] STT: {cls.name}"))
            return cls()
        print(red(f"  Invalid '{choice}'. Enter A, B, or C."))


# ─────────────────────────────────────────────────────────────────────────────
#  VOICE LOOP
# ─────────────────────────────────────────────────────────────────────────────

def _collect_field_voice(prompt: str, stt, fallback: str = "") -> str:
    """Speak prompt, listen for response. Falls back to manual keyboard."""
    speak(prompt)
    print(dim(f"  [Listening for: {prompt[:40]}...]"))
    for attempt in range(3):
        try:
            text = stt.listen(timeout=8)
            print(f"  You  ▸  {white(text)}")
            return text
        except Exception:
            if attempt < 2:
                speak("Sorry, I didn't catch that. Please repeat.")
            else:
                speak("I'll skip that. You can type it instead.")
                try:
                    text = input(cyan("  (type here) : ")).strip()
                    return text or fallback
                except Exception:
                    return fallback
    return fallback


def run_voice_loop(ai_reply_fn, stt_engine=None):
    """
    Main voice loop.

    ai_reply_fn(text: str) -> (reply: str, action: str|None, action_data: dict)

    Runs until user says "quit", "exit", or "goodbye".
    """
    from ritmo.ticketflow import book_ticket, generate_receipt

    if stt_engine is None:
        stt_engine = pick_stt_engine()

    os.system("cls" if sys.platform == "win32" else "clear")
    print()
    print(teal("  ╔══════════════════════════════════════════════════════╗"))
    print(teal("  ║") + white("   RITMO  —  Voice Mode  🎤                          ") + teal("║"))
    print(teal("  ╚══════════════════════════════════════════════════════╝"))
    print()
    print(dim("  Say 'quit' or 'goodbye' to exit."))
    print(dim("  Commands also accepted via keyboard (/receipt /quit)."))
    print(dim("  ─" * 28))
    print()

    greeting = "RITMO Voice Mode is active. How can I help you today?"
    print(f"  RITMO ▸  {white(greeting)}")
    speak(greeting)

    _last_ticket = {}

    while True:
        # ── Listen ────────────────────────────────────────────────────────────
        print()
        print(dim(f"  [{stt_engine.name}]  🎤  Listening..."))
        try:
            user_text = stt_engine.listen(timeout=7)
        except KeyboardInterrupt:
            break
        except Exception:
            # Timeout / no speech — just keep listening
            continue

        if not user_text.strip():
            continue

        print(f"  You   ▸  {cyan(user_text)}")

        # Quit keywords
        if user_text.lower().strip() in ("quit", "exit", "bye", "goodbye", "stop"):
            farewell = "Goodbye! Stay healthy."
            print(f"  RITMO ▸  {white(farewell)}")
            speak(farewell)
            break

        # /receipt keyboard shortcut
        if user_text.strip().lower() == "/receipt" and _last_ticket:
            from ritmo.ritmocli import _do_receipt
            _do_receipt(_last_ticket)
            continue

        # ── AI reply ──────────────────────────────────────────────────────────
        print(dim("  RITMO ▸  thinking..."))
        try:
            reply, action, action_data = ai_reply_fn(user_text)
        except Exception as e:
            err = f"Sorry, I encountered an error: {str(e)[:60]}"
            print(f"  RITMO ▸  {red(err)}")
            speak(err)
            continue

        # Strip action tags from spoken reply
        import re
        clean_reply = re.sub(r"\[(BOOK_TICKET|GENERATE_RECEIPT|EMERGENCY)\][^\n]*", "", reply).strip()
        if not clean_reply:
            clean_reply = reply[:200]

        print(f"  RITMO ▸  {white(clean_reply)}")
        speak(clean_reply)

        # ── Handle actions via voice ──────────────────────────────────────────
        if action == "BOOK_TICKET":
            pname = action_data.get("patient_name", "")
            if not pname or "<" in pname:
                pname = _collect_field_voice("What is the patient's full name?", stt_engine, "Patient")
            phone = action_data.get("phone", "")
            if not phone:
                phone = _collect_field_voice("Please say the phone number.", stt_engine, "0000000000")
            age = action_data.get("age", "")
            if not age:
                age = _collect_field_voice("What is the patient's age?", stt_engine, "30")

            action_data.update({"patient_name": pname, "phone": phone, "age": age})

            speak(f"Booking ticket for {pname}. Please wait.")
            from ritmo.ticketflow import book_ticket
            result = book_ticket(action_data)

            if result["ok"]:
                token = result["token"]
                dept  = result["dept_name"]
                synced = result.get("supabase_synced", False)
                msg = f"Done! Your token number is {token} for {dept}."
                if synced:
                    msg += " Ticket stored in Supabase."
                print(green(f"  [BOOKED] Token: {token} | Dept: {dept} | {'☁ Supabase' if synced else '⚠ Local only'}"))
                speak(msg)
                _last_ticket = result

                # Ask about receipt
                speak("Would you like me to generate a receipt?")
                print(dim("  Listening for yes/no..."))
                try:
                    yn = stt_engine.listen(timeout=6)
                    if any(w in yn.lower() for w in ("yes", "yeah", "sure", "please", "ok", "generate")):
                        speak("Generating your receipt now.")
                        receipt = generate_receipt(result)
                        if receipt["ok"]:
                            msg2 = "Receipt generated."
                            if receipt.get("storage_url"):
                                msg2 += " It has been uploaded to Supabase. You can scan the QR code."
                            else:
                                msg2 += " It is saved locally and has been opened in your browser."
                            speak(msg2)
                            try:
                                if sys.platform == "win32":
                                    os.startfile(receipt["html_path"])
                            except Exception:
                                pass
                            # Print ASCII QR
                            lines = receipt.get("ascii_qr_lines", [])
                            if lines:
                                import io
                                utf8_out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
                                w = len(lines[0]) + 4
                                utf8_out.write(f"  \u250c{chr(0x2500)*w}\u2510\n")
                                for ln in lines:
                                    utf8_out.write(f"  \u2502  {ln}  \u2502\n")
                                utf8_out.write(f"  \u2514{chr(0x2500)*w}\u2518\n")
                                utf8_out.flush()
                except Exception:
                    pass
            else:
                speak("I'm sorry, the booking failed. Please try again.")

        elif action == "GENERATE_RECEIPT":
            if _last_ticket:
                speak("Generating receipt. One moment.")
                receipt = generate_receipt(_last_ticket)
                if receipt["ok"]:
                    speak("Receipt is ready and has been opened in your browser.")
                    try:
                        if sys.platform == "win32":
                            os.startfile(receipt["html_path"])
                    except Exception:
                        pass
            else:
                speak("Please book a ticket first, then I can generate a receipt.")

        elif action == "EMERGENCY":
            speak("Emergency detected! Routing to emergency department immediately.")
            action_data["dept_id"] = "dep_emg"
            result = book_ticket(action_data)
            if result["ok"]:
                speak(f"Emergency ticket created. Token {result['token']}. Please proceed to emergency immediately.")
                _last_ticket = result


# ─────────────────────────────────────────────────────────────────────────────
#  Standalone test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    def _dummy_ai(text):
        # Simple echo for testing without AI
        return f"You said: {text}", None, {}

    run_voice_loop(_dummy_ai)
