"""
ritmo/normal_mode.py
====================
RITMO Normal Mode -- Guided form-style patient registration.
No AI. No internet required. Works fully offline.

Multilingual: All prompts use T() from language.manager for
Hindi, Bengali, Malayalam, Punjabi, Telugu, Tamil, and English.

Flow:
  1. Fill in patient details (name, phone, age, department)
  2. Confirm -> book ticket (Supabase or local SQLite fallback)
  3. Show ticket with ASCII art box + Supabase sync status
  4. Optionally generate receipt + ASCII QR code
  5. Ask if user wants to register another patient

Usage (standalone):
  python ritmo/normal_mode.py

Or via interface.py -> 1 -> 1.
"""

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Ensure UTF-8 output on Windows (for native scripts)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# -- Language layer -----------------------------------------------------------
try:
    from language.manager import LM, T, T_dept, LANGUAGES
    _LANG_OK = True
except ImportError:
    _LANG_OK = False
    def T(k, fb=""): return fb or k
    def T_dept(k): return k
    class _FakeLM:
        active = "en"
        def colored(self, t): return t
        @property
        def flag(self): return "[EN]"
        @property
        def color(self): return "\x1b[36;1m"
    LM = _FakeLM()

# -- TTS (ElevenLabs / edge-tts) ----------------------------------------------
try:
    from language.tts_engine import speak_async as _speak
except Exception:
    def _speak(text, lang=None): pass  # silent fallback

# -- ANSI ---------------------------------------------------------------------
_RESET   = "\x1b[0m"
_TEAL    = "\x1b[38;5;43m"
_CYAN    = "\x1b[36;1m"
_GREEN   = "\x1b[32;1m"
_YELLOW  = "\x1b[33;1m"
_RED     = "\x1b[31;1m"
_WHITE   = "\x1b[97;1m"
_DIM     = "\x1b[2m"
_MAGENTA = "\x1b[35;1m"
_BLUE    = "\x1b[34;1m"

def _c(col, txt): return f"{col}{txt}{_RESET}"
def teal(t):    return _c(_TEAL,    t)
def cyan(t):    return _c(_CYAN,    t)
def green(t):   return _c(_GREEN,   t)
def yellow(t):  return _c(_YELLOW,  t)
def red(t):     return _c(_RED,     t)
def white(t):   return _c(_WHITE,   t)
def dim(t):     return _c(_DIM,     t)
def blue(t):    return _c(_BLUE,    t)
def magenta(t): return _c(_MAGENTA, t)

# -- Departments (ID -> (dept_id, en_name)) -----------------------------------
DEPARTMENTS = {
    "1":  ("dep_gen",   "General Medicine"),
    "2":  ("dep_card",  "Cardiology"),
    "3":  ("dep_neuro", "Neurology"),
    "4":  ("dep_ortho", "Orthopedics"),
    "5":  ("dep_ped",   "Pediatrics"),
    "6":  ("dep_emg",   "Emergency"),
    "7":  ("dep_derm",  "Dermatology"),
    "8":  ("dep_ent",   "ENT"),
    "9":  ("dep_eye",   "Ophthalmology"),
    "10": ("dep_psy",   "Psychiatry"),
    "11": ("dep_dent",  "Dental"),
    "12": ("dep_gyn",   "Gynaecology"),
}


def _clear():
    os.system("cls" if sys.platform == "win32" else "clear")


def _lang_badge() -> str:
    """Show current language badge in its color."""
    return f"  {LM.color}{LM.flag}{_RESET}"


def _banner():
    _clear()
    try:
        from rekov_credits import print_rekov_credits
        print_rekov_credits(compact=True, show_contributors=False)
    except Exception:
        pass
    print()
    lang_line = _lang_badge() + dim(f"  {LM.active.upper()} / {T('your_name', 'Normal Mode')}")
    print(teal("  +------------------------------------------------------------+"))
    print(teal("  |") + white("   RITMO  --  Normal Registration Mode                   ") + teal("|"))
    print(teal("  +------------------------------------------------------------+"))
    print()
    print(lang_line)
    print()
    print(dim(f"  {T('back_hint', 'Type 0 to go back.')}"))
    print(dim("  -" * 30))
    print()
    # Speak welcome greeting (non-blocking)
    _speak(T("welcome_short", "Welcome to REKOV. Please fill in the patient details."))


# -- Field input --------------------------------------------------------------
def _field(
    label: str, step: int, total: int, default: str = "", required=False
) -> str | None:
    tag = f"[{step}/{total}]"
    prompt = f"  {dim(tag)} {LM.color}{label}{_RESET}"
    if default:
        prompt += dim(f"  (default: {default})")
    prompt += "\n  > "

    while True:
        try:
            val = input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            return None

        if val == "0" or val.lower() in ("skip", "cancel", "exit", "quit", "back"):
            return None

        # Auto-detect language from typed input and switch if different
        if _LANG_OK and val:
            from language.manager import detect_lang
            detected = detect_lang(val)
            if detected and detected != LM.active and detected in LANGUAGES:
                print(dim(f"  [Language detected: {LANGUAGES[detected]['name']}. Switching...]"))
                LM.set(detected)

        if val:
            return val
        if default:
            return default
        if not required:
            return ""
        print(red(f"  '{label}' is required."))


# -- Department picker --------------------------------------------------------
def _dept_picker(step: int, total: int) -> tuple | None:
    print()
    print(f"  {dim(f'[{step}/{total}]')} {LM.color}{T('your_dept', 'Department')}{_RESET}:")
    print()
    for k, (did, en_name) in DEPARTMENTS.items():
        local_name = T_dept(did) or en_name
        marker = "  [!]" if did == "dep_emg" else ""
        print(f"    {LM.color}{k:>3}{_RESET}  {local_name}{red(marker)}")
    print()
    print(dim(f"  Enter 1-12, press Enter for General Medicine, or 0 to go back."))
    print()

    while True:
        try:
            val = input("  > ").strip()
        except (KeyboardInterrupt, EOFError):
            return None

        if val == "0" or val.lower() in ("back", "skip", "cancel"):
            return None
        if val == "":
            return DEPARTMENTS["1"]
        if val in DEPARTMENTS:
            did, en_name = DEPARTMENTS[val]
            local_name   = T_dept(did) or en_name
            return did, local_name
        print(red(f"  Invalid '{val}'. Enter 1-12 or 0 to go back."))


# -- Confirm box --------------------------------------------------------------
def _confirm_box(name, phone, age, dept_name, notes) -> bool:
    print()
    print(magenta("  +-- " + T("your_name", "PATIENT DETAILS") + " " + "-" * 44 + "+"))
    print(magenta(f"  |  {T('your_name','Name'):<12}: {(name or '--'):<43}|"))
    print(magenta(f"  |  {T('your_phone','Phone'):<12}: {(phone or '--'):<43}|"))
    print(magenta(f"  |  {T('your_age','Age'):<12}: {(age or '--'):<43}|"))
    print(magenta(f"  |  {T('your_dept','Dept'):<12}: {dept_name:<43}|"))
    if notes:
        print(magenta(f"  |  Notes       : {notes[:43]:<43}|"))
    print(magenta("  +" + "-" * 62 + "+"))
    print()

    prompt_str = white(f"  {T('confirm', 'Confirm and book?')}  {T('yes_no_skip', '[Y/N/0]')} : ")
    while True:
        try:
            choice = input(prompt_str).strip().lower()
        except (KeyboardInterrupt, EOFError):
            return False
        if choice in ("y", "yes", ""):
            return True
        if choice in ("n", "no"):
            return False
        if choice in ("0", "s", "skip", "cancel"):
            return False
        print(red(f"  {T('invalid', 'Invalid input.')}"))


# -- Ticket box ---------------------------------------------------------------
def _print_ticket_box(result: dict):
    tid    = result.get("ticket_id", "?")
    token  = result.get("token", "?")
    dept   = result.get("dept_name", "?")
    pname  = result.get("patient", "?")
    fee    = result.get("fee", 35.0)
    synced = result.get("supabase_synced", False)

    print()
    print(green("  +-- TICKET BOOKED -----------------------------------------------+"))
    print(green(f"  |  Token       : {token:<45}|"))
    print(green(f"  |  Ticket ID   : {tid:<45}|"))
    print(green(f"  |  Patient     : {pname:<45}|"))
    print(green(f"  |  Department  : {dept:<45}|"))
    print(green(f"  |  Fee         : Rs.{fee:<43.2f}|"))
    print(green("  +" + "-" * 64 + "+"))
    print()

    if synced:
        print(green(f"  [OK] {T('stored_cloud', 'Stored in Supabase - accessible from any device.')}"))
    else:
        print(yellow(f"  [!]  {T('stored_local', 'Saved locally only (Supabase unreachable).')}"))
        print(dim("  Run migration SQL to enable cloud sync."))
    print()


# -- ASCII QR -----------------------------------------------------------------
def _print_ascii_qr(lines: list):
    if not lines:
        return
    w = len(lines[0]) + 4
    print("  +" + "-" * w + "+")
    for ln in lines:
        print("  |  " + ln + "  |")
    print("  +" + "-" * w + "+")


# -- Receipt prompt -----------------------------------------------------------
def _do_receipt_prompt(result: dict):
    print()
    try:
        q = T("receipt_q", "Generate receipt + QR code?")
        choice = input(white(f"  {q}  [Y/n]: ")).strip().lower()
    except (KeyboardInterrupt, EOFError):
        return
    if choice in ("n", "no"):
        return

    print()
    print(dim("  Generating receipt..."))

    try:
        from ritmo.ticketflow import generate_receipt
        receipt = generate_receipt(result)
    except Exception as e:
        print(red(f"  Receipt failed: {e}"))
        return

    if not receipt.get("ok"):
        print(red(f"  {receipt.get('message', 'Receipt generation failed')}"))
        return

    store_url = receipt.get("storage_url")
    html_path = receipt.get("html_path", "")

    print()
    print(magenta("  +-- RECEIPT GENERATED ----------------------------------------+"))
    print(magenta(f"  |  Ticket  : {result.get('ticket_id', '?'):<49}|"))
    print(magenta(f"  |  Token   : {result.get('token', '?'):<49}|"))
    print(magenta(f"  |  Patient : {result.get('patient', '?'):<49}|"))
    print(magenta("  +" + "-" * 62 + "+"))
    print()

    if store_url:
        print(green(f"  [OK] {T('stored_cloud', 'Uploaded to Supabase Storage')}"))
        print(f"  {dim('Receipt URL  :')} {cyan(store_url)}")
    else:
        print(yellow(f"  [!]  {T('stored_local', 'Saved locally only (Supabase unreachable)')}"))
        print(f"  {dim('Local file   :')} {cyan(html_path)}")
    print()

    # ASCII QR
    ascii_lines = receipt.get("ascii_qr_lines", [])
    if ascii_lines:
        _print_ascii_qr(ascii_lines)
        print()
        print(dim("  Scan QR to open receipt from any device."))
        print()

    # Public URL
    pub_url = receipt.get("public_url", "")
    if pub_url:
        print(dim("  Public link:"))
        print(f"  {cyan(pub_url[:80])}{'...' if len(pub_url) > 80 else ''}")
        print()

    # Open in browser
    try:
        if html_path and os.path.isfile(html_path):
            if sys.platform == "win32":
                os.startfile(html_path)
            elif sys.platform == "darwin":
                os.system(f'open "{html_path}"')
            else:
                os.system(f'xdg-open "{html_path}"')
            print(dim("  Receipt opened in browser."))
        else:
            print(dim(f"  Open manually: {html_path}"))
    except Exception:
        print(dim(f"  Open manually: {html_path}"))
    _speak(T("receipt_ready", "Receipt is ready."))
    print()


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN NORMAL MODE LOOP
# ─────────────────────────────────────────────────────────────────────────────

def run_normal_mode():
    """
    Run the full guided patient registration loop (multilingual).
    Returns when user chooses to stop or types 0 to go back.
    """
    from ritmo.ticketflow import book_ticket

    while True:
        _banner()

        # Step 1 -- Patient name
        name = _field(T("your_name", "Patient Name"), 1, 5, required=True)
        if name is None:
            print(yellow(f"\n  {T('cancelled', 'Registration cancelled.')}"))
            return

        # Step 2 -- Phone
        print()
        phone = _field(T("your_phone", "Phone Number (optional)"), 2, 5, default="")
        if phone is None:
            print(yellow(f"\n  {T('cancelled', 'Registration cancelled.')}"))
            return

        # Step 3 -- Age
        print()
        age = _field(T("your_age", "Age (optional)"), 3, 5, default="")
        if age is None:
            print(yellow(f"\n  {T('cancelled', 'Registration cancelled.')}"))
            return

        # Step 4 -- Department
        dept_result = _dept_picker(4, 5)
        if dept_result is None:
            print(yellow(f"\n  {T('cancelled', 'Registration cancelled.')}"))
            return
        dept_id, dept_name = dept_result

        # Step 5 -- Notes
        print()
        notes = _field(T("your_notes", "Notes / Chief Complaint (optional)"), 5, 5, default="")
        if notes is None:
            print(yellow(f"\n  {T('cancelled', 'Registration cancelled.')}"))
            return

        # Confirm
        confirmed = _confirm_box(name, phone, age, dept_name, notes)
        if not confirmed:
            print(yellow("  Going back to form..."))
            continue

        # Book
        print()
        print(dim(f"  {T('booking_wait', 'Booking ticket...')}"))
        try:
            from ritmo.spinner import Spinner
            with Spinner(T("booking_wait", "Saving ticket...")):
                result = book_ticket({
                    "dept_id":      dept_id,
                    "patient_name": name,
                    "phone":        phone,
                    "age":          age,
                })
        except ImportError:
            result = book_ticket({
                "dept_id":      dept_id,
                "patient_name": name,
                "phone":        phone,
                "age":          age,
            })

        if not result.get("ok"):
            print(red(f"  Booking failed: {result.get('message', 'Unknown error')}"))
            print()
            _speak("Booking failed. Please try again.")
        else:
            _print_ticket_box(result)
            # Speak ticket confirmation
            _speak(f"{T('ticket_booked', 'Ticket booked.')} {T('your_token', 'Token')} {result.get('token', '')}.")
            _do_receipt_prompt(result)

        # Register another?
        print()
        try:
            q = T("another", "Register another patient?")
            again = input(white(f"  {q}  [Y/n]: ")).strip().lower()
        except (KeyboardInterrupt, EOFError):
            again = "n"

        if again in ("n", "no", "0"):
            print()
            print(dim(f"  {T('goodbye', 'Thank you. Goodbye!')}"))
            _speak(T("goodbye", "Thank you. Goodbye!"))
            print()
            return


if __name__ == "__main__":
    run_normal_mode()
