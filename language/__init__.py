"""
language/__init__.py
====================
Language module for REKOV.

Exports the most commonly needed symbols so callers can do:

    from language import LM, T, T_dept, speak, set_lang, show_language_picker

File layout:
    language/
    ├── __init__.py        (this file)
    ├── manager.py         LANGUAGES registry, LM singleton, T(), T_dept()
    ├── strings.py         All UI strings in 7 languages + department names
    ├── picker.py          Animated ASCII art language picker
    └── tts_engine.py      Unified TTS: ElevenLabs -> edge-tts -> silent
"""

from language.manager    import LM, T, T_dept, LANGUAGES, LANG_KEYS, get_active_lang, set_lang, detect_lang
from language.tts_engine import speak, speak_async, get_engine_info, TTS_ENGINE
from language.picker     import show_language_picker, switch_language_prompt

__all__ = [
    "LM",
    "T",
    "T_dept",
    "LANGUAGES",
    "LANG_KEYS",
    "get_active_lang",
    "set_lang",
    "detect_lang",
    "speak",
    "speak_async",
    "get_engine_info",
    "TTS_ENGINE",
    "show_language_picker",
    "switch_language_prompt",
]
