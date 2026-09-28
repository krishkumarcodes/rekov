"""
language/manager.py
====================
Core language manager for REKOV.

Usage:
    from language.manager import LM, T, LANGUAGES, detect_lang

    LM.set("hi")          # switch to Hindi
    T("welcome")          # -> "REKOV अस्पताल प्रणाली में आपका स्वागत है"
    LM.active             # -> "hi"
    LM.stt_code()         # -> "hi-IN"
    LM.edge_voice()       # -> "hi-IN-SwaraNeural"
    LM.el_voice_id()      # -> ElevenLabs voice ID for Hindi
"""

import os
import json
import sys
from pathlib import Path

ROOT_DIR  = Path(__file__).resolve().parent.parent
DATA_DIR  = ROOT_DIR / "data"
SESS_FILE = DATA_DIR / "session_lang.json"

# ─────────────────────────────────────────────────────────────────────────────
#  LANGUAGE REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

# ANSI colors per language
_R = "\x1b[0m"

LANGUAGES: dict[str, dict] = {
    "en": {
        "name":       "English",
        "native":     "English",
        "code":       "en-IN",
        "edge_voice": "en-IN-NeerjaNeural",
        "el_voice":   "JBFqnCBsd6RMkjVDRZzb",   # ElevenLabs Rachel (EN, multilingual)
        "color":      "\x1b[36;1m",              # cyan
        "ansi":       "\x1b[36;1m",
        "flag":       "[EN]",
    },
    "hi": {
        "name":       "Hindi",
        "native":     "हिन्दी",
        "code":       "hi-IN",
        "edge_voice": "hi-IN-SwaraNeural",
        "el_voice":   "pNInz6obpgDQGcFmaJgB",   # ElevenLabs Adam (multilingual v2)
        "color":      "\x1b[33;1m",              # yellow
        "ansi":       "\x1b[33;1m",
        "flag":       "[HI]",
    },
    "bn": {
        "name":       "Bengali",
        "native":     "বাংলা",
        "code":       "bn-IN",
        "edge_voice": "bn-IN-TanishaaNeural",
        "el_voice":   "pNInz6obpgDQGcFmaJgB",
        "color":      "\x1b[32;1m",              # green
        "ansi":       "\x1b[32;1m",
        "flag":       "[BN]",
    },
    "ml": {
        "name":       "Malayalam",
        "native":     "മലയാളം",
        "code":       "ml-IN",
        "edge_voice": "ml-IN-MidhunNeural",
        "el_voice":   "pNInz6obpgDQGcFmaJgB",
        "color":      "\x1b[35;1m",              # magenta
        "ansi":       "\x1b[35;1m",
        "flag":       "[ML]",
    },
    "pa": {
        "name":       "Punjabi",
        "native":     "ਪੰਜਾਬੀ",
        "code":       "pa-IN",
        "edge_voice": "pa-IN-OjasNeural",
        "el_voice":   "pNInz6obpgDQGcFmaJgB",
        "color":      "\x1b[34;1m",              # blue
        "ansi":       "\x1b[34;1m",
        "flag":       "[PA]",
    },
    "te": {
        "name":       "Telugu",
        "native":     "తెలుగు",
        "code":       "te-IN",
        "edge_voice": "te-IN-MohanNeural",
        "el_voice":   "pNInz6obpgDQGcFmaJgB",
        "color":      "\x1b[38;5;208m",          # orange
        "ansi":       "\x1b[38;5;208m",
        "flag":       "[TE]",
    },
    "ta": {
        "name":       "Tamil",
        "native":     "தமிழ்",
        "code":       "ta-IN",
        "edge_voice": "ta-IN-PallaviNeural",
        "el_voice":   "pNInz6obpgDQGcFmaJgB",
        "color":      "\x1b[38;5;197m",          # hot pink
        "ansi":       "\x1b[38;5;197m",
        "flag":       "[TA]",
    },
}

LANG_KEYS = list(LANGUAGES.keys())  # ["en", "hi", "bn", "ml", "pa", "te", "ta"]

# ─────────────────────────────────────────────────────────────────────────────
#  AUTO-DETECT HELPER (for typed input)
# ─────────────────────────────────────────────────────────────────────────────

def detect_lang(text: str) -> str | None:
    """
    Auto-detect the language of typed text.
    Returns a 2-letter key from LANGUAGES, or None if uncertain.
    Uses langdetect (pure Python, offline).
    Falls back gracefully if not installed.
    """
    if not text or len(text.strip()) < 3:
        return None
    try:
        from langdetect import detect as _detect
        code = _detect(text)   # returns ISO-639-1 like 'hi', 'ta', 'en', etc.
        # langdetect returns 'hi', 'te', 'ta', 'ml', 'bn', 'pa', 'en'
        return code if code in LANGUAGES else None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  LANGUAGE MANAGER
# ─────────────────────────────────────────────────────────────────────────────

class LanguageManager:
    """
    Holds the active session language.
    Persists to data/session_lang.json so the session remembers choice across restarts.
    """

    def __init__(self, default: str = "en"):
        self.active: str = default
        self._load()

    # -- Persistence ----------------------------------------------------------

    def _load(self):
        """Load from disk if available."""
        try:
            if SESS_FILE.exists():
                saved = json.loads(SESS_FILE.read_text(encoding="utf-8"))
                lang  = saved.get("lang", "en")
                if lang in LANGUAGES:
                    self.active = lang
        except Exception:
            pass

    def _save(self):
        """Persist active language to disk."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            SESS_FILE.write_text(
                json.dumps({"lang": self.active}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    # -- Language setters -----------------------------------------------------

    def set(self, lang_key: str):
        """Set active language. lang_key must be in LANGUAGES."""
        if lang_key in LANGUAGES:
            self.active = lang_key
            self._save()
        else:
            raise ValueError(f"Unknown language key: {lang_key!r}. Choose from {LANG_KEYS}")

    def reset(self):
        """Reset to English."""
        self.set("en")

    # -- Accessors ------------------------------------------------------------

    @property
    def info(self) -> dict:
        return LANGUAGES[self.active]

    @property
    def name(self) -> str:
        return LANGUAGES[self.active]["name"]

    @property
    def native(self) -> str:
        return LANGUAGES[self.active]["native"]

    @property
    def color(self) -> str:
        return LANGUAGES[self.active]["color"]

    @property
    def flag(self) -> str:
        return LANGUAGES[self.active]["flag"]

    def stt_code(self) -> str:
        """BCP-47 code for Google STT (e.g. 'hi-IN')."""
        return LANGUAGES[self.active]["code"]

    def edge_voice(self) -> str:
        """edge-tts voice name for this language."""
        return LANGUAGES[self.active]["edge_voice"]

    def el_voice_id(self) -> str:
        """ElevenLabs voice ID for this language."""
        return LANGUAGES[self.active]["el_voice"]

    def colored(self, text: str) -> str:
        """Wrap text in this language's ANSI color."""
        return f"{self.color}{text}\x1b[0m"


# ─────────────────────────────────────────────────────────────────────────────
#  GLOBAL SINGLETON + TRANSLATE SHORTCUT
# ─────────────────────────────────────────────────────────────────────────────

# Module-level singleton used everywhere via `from language.manager import LM, T`
LM = LanguageManager()


def T(key: str, fallback: str = "") -> str:
    """
    Translate a string key to the active language.
    Falls back to English if key not found in active language.
    Falls back to `fallback` if not even in English.
    """
    from language.strings import STRINGS
    lang_dict = STRINGS.get(LM.active, {})
    en_dict   = STRINGS.get("en", {})
    return lang_dict.get(key) or en_dict.get(key) or fallback or key


def T_dept(dept_id: str) -> str:
    """Get localized department name by dept ID."""
    from language.strings import DEPT_NAMES
    lang_map = DEPT_NAMES.get(LM.active, {})
    en_map   = DEPT_NAMES.get("en", {})
    return lang_map.get(dept_id) or en_map.get(dept_id) or dept_id


def get_active_lang() -> str:
    """Return the active language key (e.g. 'hi')."""
    return LM.active


def set_lang(key: str):
    """Set active language globally."""
    LM.set(key)
