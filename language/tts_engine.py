"""
language/tts_engine.py
=======================
Unified TTS engine for REKOV.

Priority:
  1. ElevenLabs (eleven_multilingual_v2) — if API key set in config.json
  2. edge-tts (free, Microsoft Azure neural voices) — always available
  3. Silent fallback — if both fail, print text only

Usage:
    from language.tts_engine import speak, TTS_ENGINE

    speak("Hello, how are you?", lang="en")
    speak("आप कैसे हैं?", lang="hi")

TTS_ENGINE will be "elevenlabs" or "edge-tts" or "silent".
"""

import os
import sys
import json
import asyncio
import tempfile
import threading
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# ─── Config loader ────────────────────────────────────────────────────────────
def _load_config() -> dict:
    for path in [ROOT_DIR / "config.json", ROOT_DIR / "base" / "config.json"]:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}

_cfg = _load_config()
_EL_KEY: str  = (
    _cfg.get("elevenlabs_key") or
    _cfg.get("ELEVENLABS_KEY") or
    os.environ.get("ELEVENLABS_API_KEY", "")
)

# ─── ANSI helpers ─────────────────────────────────────────────────────────────
_R  = "\x1b[0m"
_D  = "\x1b[2m"
_Y  = "\x1b[33;1m"
_G  = "\x1b[32;1m"

# ─── Language voice registry (matches language/manager.py) ────────────────────
_EDGE_VOICES = {
    "en": "en-IN-NeerjaNeural",
    "hi": "hi-IN-SwaraNeural",
    "bn": "bn-IN-TanishaaNeural",
    "ml": "ml-IN-MidhunNeural",
    "pa": "pa-IN-OjasNeural",
    "te": "te-IN-MohanNeural",
    "ta": "ta-IN-PallaviNeural",
}

_EL_VOICE_IDS = {
    "en": "JBFqnCBsd6RMkjVDRZzb",   # Rachel (EN, natural)
    "hi": "pNInz6obpgDQGcFmaJgB",   # Adam (multilingual v2)
    "bn": "pNInz6obpgDQGcFmaJgB",
    "ml": "pNInz6obpgDQGcFmaJgB",
    "pa": "pNInz6obpgDQGcFmaJgB",
    "te": "pNInz6obpgDQGcFmaJgB",
    "ta": "pNInz6obpgDQGcFmaJgB",
}

# ─── pip auto-installer ───────────────────────────────────────────────────────
def _pip(*pkgs):
    import subprocess
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", *pkgs, "--quiet"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  ELEVENLABS TTS
# ─────────────────────────────────────────────────────────────────────────────
def _elevenlabs_available() -> bool:
    if not _EL_KEY:
        return False
    try:
        import elevenlabs   # noqa
        return True
    except ImportError:
        try:
            _pip("elevenlabs")
            import elevenlabs   # noqa
            return True
        except Exception:
            return False


def _speak_elevenlabs(text: str, lang: str = "en"):
    """
    Speak text using ElevenLabs eleven_multilingual_v2.
    Plays via pygame after saving to temp MP3.
    """
    try:
        import elevenlabs
        from elevenlabs.client import ElevenLabs as _EL
    except ImportError:
        raise RuntimeError("elevenlabs not installed")

    try:
        import pygame
    except ImportError:
        _pip("pygame")
        import pygame

    client   = _EL(api_key=_EL_KEY)
    voice_id = _EL_VOICE_IDS.get(lang, _EL_VOICE_IDS["en"])

    audio_gen = client.text_to_speech.convert(
        text=text[:300],           # ElevenLabs free tier: 10k chars/mo; keep short
        voice_id=voice_id,
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
    )

    # audio_gen is a generator of bytes chunks
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tmp = f.name
        for chunk in audio_gen:
            f.write(chunk)

    try:
        pygame.mixer.init()
        pygame.mixer.music.load(tmp)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(80)
        pygame.mixer.music.unload()
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  EDGE-TTS FALLBACK
# ─────────────────────────────────────────────────────────────────────────────
def _ensure_edge_tts():
    try:
        import edge_tts   # noqa
    except ImportError:
        _pip("edge-tts")


def _ensure_pygame():
    try:
        import pygame   # noqa
    except ImportError:
        _pip("pygame")


async def _speak_edge_async(text: str, voice: str):
    import edge_tts
    import pygame

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tmp = f.name

    try:
        comm = edge_tts.Communicate(text, voice)
        await comm.save(tmp)

        pygame.mixer.init()
        pygame.mixer.music.load(tmp)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(80)
        pygame.mixer.music.unload()
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass


def _speak_edge(text: str, lang: str = "en"):
    """Speak text using edge-tts (free Microsoft neural voices)."""
    _ensure_edge_tts()
    _ensure_pygame()
    voice = _EDGE_VOICES.get(lang, _EDGE_VOICES["en"])
    # Truncate to ~2 sentences
    sentences = text.replace("—", ".").split(".")
    short = ". ".join(s.strip() for s in sentences[:2] if s.strip())
    asyncio.run(_speak_edge_async(short or text[:200], voice))


# ─────────────────────────────────────────────────────────────────────────────
#  DETERMINE ACTIVE ENGINE AT IMPORT TIME
# ─────────────────────────────────────────────────────────────────────────────
def _resolve_engine() -> str:
    if _elevenlabs_available():
        return "elevenlabs"
    try:
        _ensure_edge_tts()
        return "edge-tts"
    except Exception:
        return "silent"


TTS_ENGINE: str = _resolve_engine()


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────
def speak(text: str, lang: str | None = None):
    """
    Speak text in the given language (or active session language if None).
    Blocks until playback finishes.

    Args:
        text: Text to speak.
        lang: Language key ("en", "hi", "bn", etc.) or None to use session lang.
    """
    if not text or not text.strip():
        return

    # Resolve lang
    if lang is None:
        try:
            from language.manager import LM
            lang = LM.active
        except Exception:
            lang = "en"

    if TTS_ENGINE == "elevenlabs":
        try:
            _speak_elevenlabs(text, lang)
            return
        except Exception as e:
            print(f"  {_Y}[TTS] ElevenLabs failed ({e}) — using edge-tts{_R}")

    if TTS_ENGINE in ("edge-tts", "elevenlabs"):  # fallback if EL failed
        try:
            _speak_edge(text, lang)
            return
        except Exception as e:
            print(f"  {_Y}[TTS] edge-tts failed ({e}) — silent mode{_R}")

    # Silent fallback — just print
    print(f"  {_D}[TTS-SILENT] {text}{_R}")


def speak_async(text: str, lang: str | None = None):
    """Non-blocking speak — fires TTS in background thread."""
    t = threading.Thread(target=speak, args=(text, lang), daemon=True)
    t.start()
    return t


def get_engine_info() -> str:
    """Return a human-readable description of the active TTS engine."""
    if TTS_ENGINE == "elevenlabs":
        return "ElevenLabs (eleven_multilingual_v2 — premium AI voice)"
    elif TTS_ENGINE == "edge-tts":
        return "Microsoft edge-tts (free, 7-language neural voices)"
    else:
        return "Silent (no TTS engine available)"
