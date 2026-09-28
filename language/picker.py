"""
language/picker.py
==================
Animated ASCII art language selector for REKOV terminal.

Features:
- Color-animated REKOV logo intro
- 7-language grid with native scripts + color codes
- Selection flash animation
- Horizontal sweep transition on pick
- Welcome message in selected language

Usage:
    from language.picker import show_language_picker
    lang_key = show_language_picker()   # returns e.g. "hi"
"""

import os
import sys
import time
import threading

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

# ─── ANSI helpers ─────────────────────────────────────────────────────────────
_R   = "\x1b[0m"
_B   = "\x1b[1m"
_D   = "\x1b[2m"
_CL  = "\x1b[2K"  # clear line
_CU  = "\x1b[1A"  # cursor up 1 line

def _col(code, t): return f"{code}{t}{_R}"
def _bold(t):      return f"{_B}{t}{_R}"
def _dim(t):       return f"{_D}{t}{_R}"

# ─── Language data (local copy so picker has no circular import) ───────────────
_LANGS = [
    ("en", "English",   "English",  "\x1b[36;1m",       "[EN]",  "en-IN"),
    ("hi", "Hindi",     "हिन्दी",    "\x1b[33;1m",       "[HI]",  "hi-IN"),
    ("bn", "Bengali",   "বাংলা",     "\x1b[32;1m",       "[BN]",  "bn-IN"),
    ("ml", "Malayalam", "മലയാളം",   "\x1b[35;1m",       "[ML]",  "ml-IN"),
    ("pa", "Punjabi",   "ਪੰਜਾਬੀ",   "\x1b[34;1m",       "[PA]",  "pa-IN"),
    ("te", "Telugu",    "తెలుగు",   "\x1b[38;5;208m",   "[TE]",  "te-IN"),
    ("ta", "Tamil",     "தமிழ்",    "\x1b[38;5;197m",   "[TA]",  "ta-IN"),
]
_LANG_BY_NUM = {str(i + 1): _LANGS[i] for i in range(len(_LANGS))}

_IS_WIN = sys.platform == "win32"


def _clear():
    os.system("cls" if _IS_WIN else "clear")


# ─── Animated intro logo ───────────────────────────────────────────────────────
_LOGO_LINES = [
    r"  ██████╗ ███████╗██╗  ██╗ ██████╗ ██╗   ██╗",
    r"  ██╔══██╗██╔════╝██║ ██╔╝██╔═══██╗██║   ██║",
    r"  ██████╔╝█████╗  █████╔╝ ██║   ██║██║   ██║",
    r"  ██╔══██╗██╔══╝  ██╔═██╗ ██║   ██║╚██╗ ██╔╝",
    r"  ██║  ██║███████╗██║  ██╗╚██████╔╝ ╚████╔╝ ",
    r"  ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝ ╚═════╝   ╚═══╝  ",
]

_LOGO_COLORS = [
    "\x1b[38;5;51m",   # bright cyan
    "\x1b[38;5;45m",
    "\x1b[38;5;39m",
    "\x1b[38;5;33m",
    "\x1b[38;5;27m",
    "\x1b[38;5;21m",   # deep blue
]


def _animate_logo(delay: float = 0.06):
    """Print the REKOV ASCII logo line by line with color fade."""
    for i, (line, col) in enumerate(zip(_LOGO_LINES, _LOGO_COLORS)):
        print(f"{col}{line}{_R}")
        time.sleep(delay)


# ─── Color-wave border ────────────────────────────────────────────────────────
_WAVE_COLS = [
    "\x1b[36;1m", "\x1b[33;1m", "\x1b[32;1m",
    "\x1b[35;1m", "\x1b[34;1m", "\x1b[38;5;208m", "\x1b[38;5;197m",
]

def _wave_bar(width: int = 62, frame: int = 0) -> str:
    chars = []
    for i in range(width):
        col = _WAVE_COLS[(i + frame) % len(_WAVE_COLS)]
        chars.append(f"{col}={_R}")
    return "  " + "".join(chars)


def _animate_wave_bar(steps: int = 7, delay: float = 0.05):
    for frame in range(steps):
        sys.stdout.write("\r" + _wave_bar(frame=frame))
        sys.stdout.flush()
        time.sleep(delay)
    print()  # newline after wave


# ─── Language grid ────────────────────────────────────────────────────────────
def _print_lang_grid(highlight: str | None = None, flash_on: bool = True):
    """
    Print the 7-language selection grid.
    highlight: key to flash (e.g. 'hi')
    flash_on:  True = show in color, False = dim (for flash effect)
    """
    print()
    for entry in _LANGS:
        key, name, native, color, flag, bcp = entry
        num = str(_LANGS.index(entry) + 1)

        is_hl = (key == highlight)
        if is_hl and not flash_on:
            row_col = "\x1b[2m"     # dim during flash-off
        elif is_hl:
            row_col = "\x1b[7m" + color  # reverse video in language color
        else:
            row_col = color

        num_str  = f"{row_col}  {num}{_R}"
        name_str = f"{row_col}  {name:<12}{_R}"
        nat_str  = f"{row_col}{native:<14}{_R}"
        bcp_str  = _dim(f"  {bcp}")

        marker = f" {_bold('<---')}" if is_hl else ""
        print(f"    {num_str}  {name_str}  {nat_str}{bcp_str}{marker}")
    print()


# ─── Sweep transition ─────────────────────────────────────────────────────────
def _sweep_transition(color: str, width: int = 64, delay: float = 0.012):
    """Print a horizontal scan bar that sweeps left to right."""
    for i in range(width + 1):
        bar = color + "=" * i + _R + _dim("=" * (width - i))
        sys.stdout.write(f"\r  {bar}")
        sys.stdout.flush()
        time.sleep(delay)
    print()


# ─── Flash animation ─────────────────────────────────────────────────────────
def _flash_selection(key: str, flashes: int = 4, delay: float = 0.12):
    """Flash the selected language row on/off."""
    for i in range(flashes * 2):
        _clear()
        _print_header()
        _print_lang_grid(highlight=key, flash_on=(i % 2 == 0))
        time.sleep(delay)


# ─── Header block ─────────────────────────────────────────────────────────────
def _print_header():
    """Print the compact header (used during flash too)."""
    print()
    for i, (line, col) in enumerate(zip(_LOGO_LINES, _LOGO_COLORS)):
        print(f"{col}{line}{_R}")
    print()
    _animate_wave_bar(steps=1, delay=0)   # static bar (no animation during flash)
    print()
    print(_bold("  " + " LANGUAGE  /  BHASHA  SELECTOR ".center(62, "=")))
    print(_dim("  " + "=" * 62))
    print()


# ─── Main picker ──────────────────────────────────────────────────────────────
def show_language_picker(skip_animation: bool = False) -> str:
    """
    Show the animated language picker.
    Returns selected language key (e.g. "hi").
    Always returns a valid key from LANGUAGES.
    """
    # Ensure UTF-8 output on Windows
    if _IS_WIN:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    _clear()
    print()

    if not skip_animation:
        _animate_logo(delay=0.055)
    else:
        for i, (line, col) in enumerate(zip(_LOGO_LINES, _LOGO_COLORS)):
            print(f"{col}{line}{_R}")

    print()
    _animate_wave_bar(steps=14, delay=0.04)
    print()
    print(_bold("  " + " LANGUAGE  /  BHASHA  SELECTOR ".center(62, "=")))
    print(_dim("  " + "=" * 62))
    print()
    print(_dim("  Select your language for typing and voice interaction."))
    print(_dim("  Apni bhasha chunein — typing aur voice dono ke liye."))
    print()

    _print_lang_grid()

    print(_dim("  " + "-" * 62))
    print()
    print("  " + _dim("Type number ") + _bold("[1-7]") + _dim(" or press Enter for English:"))
    print()

    # -- Input loop --
    while True:
        try:
            raw = input("  > ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return "en"

        if raw == "" or raw.lower() in ("en", "english"):
            chosen = "en"
        elif raw in _LANG_BY_NUM:
            chosen = _LANG_BY_NUM[raw][0]
        elif raw.lower() in [l[0] for l in _LANGS]:
            chosen = raw.lower()
        else:
            print(_col("\x1b[31;1m", f"  Invalid choice '{raw}'. Enter 1-7 or press Enter."))
            continue

        # ── Transition animation ────────────────────────────────────────────
        info = next(l for l in _LANGS if l[0] == chosen)
        _, name, native, color, flag, bcp = info

        # Flash rows
        _flash_selection(chosen, flashes=3, delay=0.10)

        # Sweep bar in language color
        _clear()
        _print_header()
        _print_lang_grid(highlight=chosen, flash_on=True)
        print()
        _sweep_transition(color, width=64, delay=0.010)
        print()

        # Welcome message in chosen language
        from language.strings import STRINGS
        welcome = STRINGS.get(chosen, {}).get("welcome", f"Welcome — {name}")

        print()
        print(f"  {color}{_bold(flag)}  {welcome}{_R}")
        print()
        print(_dim(f"  Language set: {name}  ({native})  [{bcp}]"))
        print()
        time.sleep(0.8)

        return chosen


# ─── Compact inline switcher (used mid-session via /lang) ─────────────────────
def switch_language_prompt(current: str = "en") -> str:
    """
    Compact mid-session language switcher (no full-screen animation).
    Returns new language key.
    """
    print()
    print(_bold("  -- Language Switch --"))
    print()
    for entry in _LANGS:
        key, name, native, color, flag, bcp = entry
        num = str(_LANGS.index(entry) + 1)
        marker = _bold("  <-- current") if key == current else ""
        print(f"    {color}{num}{_R}  {color}{name:<12}{_R}  {native:<14}  {_dim(bcp)}{marker}")
    print()

    while True:
        try:
            raw = input("  New language [1-7] or Enter to keep current: ").strip()
        except (KeyboardInterrupt, EOFError):
            return current

        if raw == "":
            return current
        if raw in _LANG_BY_NUM:
            chosen = _LANG_BY_NUM[raw][0]
            info   = next(l for l in _LANGS if l[0] == chosen)
            _, name, native, color, flag, bcp = info
            from language.strings import STRINGS
            welcome = STRINGS.get(chosen, {}).get("welcome", f"Welcome — {name}")
            print()
            print(f"  {color}{_bold(flag)}  {welcome}{_R}")
            print()
            return chosen
        print(_col("\x1b[31;1m", f"  Invalid. Enter 1-7 or press Enter."))


if __name__ == "__main__":
    # Standalone demo
    key = show_language_picker()
    print(f"\nSelected: {key}")
