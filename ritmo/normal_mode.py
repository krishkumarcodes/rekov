"""
ritmo/normal_mode.py
====================
RITMO Normal Mode — Guided form-style patient registration.
No AI. No internet required. Works fully offline.

Flow:
  1. Fill in patient details (name, phone, age, department)
  2. Confirm → book ticket (Supabase or local SQLite fallback)
  3. Show ticket with ASCII art box + Supabase sync status
  4. Optionally generate receipt + ASCII QR code
  5. Ask if user wants to register another patient

Usage (standalone):
  python ritmo/normal_mode.py

Or via interface.py → 3 → 1.
"""

import os
import sys
import io
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# ── ANSI ──────────────────────────────────────────────────────────────────────
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

# ── Departments ───────────────────────────────────────────────────────────────
DEPARTMENTS = {
    "1": ("dep_gen",   "General Medicine"),
    "2": ("dep_card",  "Cardiology"),
    "3": ("dep_neuro", "Neurology"),
    "4": ("dep_ortho", "Orthopedics"),
    "5": ("dep_ped",   "Pediatrics"),
    "6": ("dep_emg",   "Emergency"),
}


def _clear():
    os.system("cls" if sys.platform == "win32" else "clear")


def _banner():
    _clear()
    try:
        from rekov_credits import print_rekov_credits
        print_rekov_credits(compact=True, show_contributors=False)
    except Exception:
        pass
    print()
    print(teal("  ╔══════════════════════════════════════════════════════╗"))
    print(teal("  ║") + white("   RITMO  —  Normal Registration Mode                ") + teal("║"))
    print(teal("  ╚══════════════════════════════════════════════════════╝"))
    print()
    print(dim("  Fill in patient details. Press Enter to skip a field."))
    print(dim("  Type 'skip' at any time to cancel registration."))
    print(dim("  ─" * 28))
    print()


def _field(label: str, step: int, total: int, default: str = "", required=False) -> str | None:
    """
    Prompt for a single field.
    Returns None if user types 'skip' (cancels).
    Returns default if user presses Enter.
    """
    tag = f"[{step}/{total}]"
    prompt = f"  {dim(tag)} {cyan(label)}"
    if default:
        prompt += dim(f"  (default: {default})")
    prompt += "\n  > "

    while True:
        try:
            val = input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            return None

        if val.lower() in ("skip", "cancel", "exit", "quit"):
            return None

        if val:
            return val
        if default:
            return default
        if not required:
            return ""
        print(red(f"  ✗ '{label}' is required. Please enter a value."))


def _dept_picker(step: int, total: int) -> tuple | None:
    """
    Show department menu, return (dept_id, dept_name) or None if skipped.
    """
    print()
    print(f"  {dim(f'[{step}/{total}]')} {cyan('Department')}:")
    print()
    for k, (did, dname) in DEPARTMENTS.items():
        icon = "🚨" if did == "dep_emg" else "🏥"
        print(f"    {cyan(k)}  {icon}  {dname}")
    print()
    print(dim("  Enter number, or press Enter for General Medicine, or 'skip' to cancel."))
    print()

    while True:
        try:
            val = input("  > ").strip()
        except (KeyboardInterrupt, EOFError):
            return None

        if val.lower() in ("skip", "cancel", "exit", "quit"):
            return None
        if val == "":
            return DEPARTMENTS["1"]
        if val in DEPARTMENTS:
            return DEPARTMENTS[val]
        print(red(f"  ✗ Invalid choice '{val}'. Enter 1-6."))


def _confirm_box(name, phone, age, dept_name, notes) -> bool:
    """Print a review box and ask for confirmation."""
    print()
    print(magenta("  ┌─ PATIENT DETAILS ───────────────────────────────────────┐"))
    print(magenta(f"  │  Name       : {(name or '—'):<43}│"))
    print(magenta(f"  │  Phone      : {(phone or '—'):<43}│"))
    print(magenta(f"  │  Age        : {(age or '—'):<43}│"))
    print(magenta(f"  │  Department : {dept_name:<43}│"))
    if notes:
        print(magenta(f"  │  Notes      : {notes[:43]:<43}│"))
    print(magenta("  └─────────────────────────────────────────────────────────┘"))
    print()

    while True:
        try:
            choice = input(white("  Confirm and book?  [Y]es  [N]o / edit  [S]kip : ")).strip().lower()
        except (KeyboardInterrupt, EOFError):
            return False
        if choice in ("y", "yes", ""):
            return True
        if choice in ("n", "no"):
            return False
        if choice in ("s", "skip"):
            return False
        print(red("  Enter Y, N, or S."))


def _print_ticket_box(result: dict):
    """Print the booked ticket confirmation box."""
    tid    = result.get("ticket_id", "?")
    token  = result.get("token", "?")
    dept   = result.get("dept_name", "?")
    pname  = result.get("patient", "?")
    fee    = result.get("fee", 35.0)
    synced = result.get("supabase_synced", False)

    print()
    print(green("  ┌─ TICKET BOOKED ─────────────────────────────────────────┐"))
    print(green(f"  │  Token       : {token:<43}│"))
    print(green(f"  │  Ticket ID   : {tid:<43}│"))
    print(green(f"  │  Patient     : {pname:<43}│"))
    print(green(f"  │  Department  : {dept:<43}│"))
    print(green(f"  │  Fee         : ₹{fee:<42.2f}│"))
    print(green("  └─────────────────────────────────────────────────────────┘"))
    print()

    if synced:
        print(green("  ☁  Stored in Supabase ✓"))
        print(dim("  Ticket is accessible from any device."))
    else:
        print(yellow("  ⚠  Stored locally only (Supabase unreachable)"))
        print(dim("  Run Supabase migration SQL to enable cloud sync."))
    print()


def _print_ascii_qr(lines: list):
    """Print QR code as ASCII art — handles Windows cp1252 via UTF-8 stdout."""
    if not lines:
        return
    try:
        utf8_out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
        w = len(lines[0]) + 4
        utf8_out.write(f"  \u250c{chr(0x2500)*w}\u2510\n")
        for ln in lines:
            utf8_out.write(f"  \u2502  {ln}  \u2502\n")
        utf8_out.write(f"  \u2514{chr(0x2500)*w}\u2518\n")
        utf8_out.flush()
    except Exception:
        # Pure ASCII fallback
        for ln in lines:
            print("  |  " + ln.encode("ascii", errors="replace").decode() + "  |")


def _do_receipt_prompt(result: dict):
    """Ask if user wants a receipt and generate it."""
    print()
    try:
        choice = input(white("  Generate receipt + QR code?  [Y/n]: ")).strip().lower()
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
        print(red(f"  ✗ Receipt failed: {e}"))
        return

    if not receipt.get("ok"):
        print(red(f"  ✗ {receipt.get('message', 'Receipt generation failed')}"))
        return

    store_url = receipt.get("storage_url")
    html_path = receipt.get("html_path", "")

    print()
    print(magenta("  ┌─ RECEIPT GENERATED ─────────────────────────────────────┐"))
    print(magenta(f"  │  Ticket  : {result.get('ticket_id','?'):<43}│"))
    print(magenta(f"  │  Token   : {result.get('token','?'):<43}│"))
    print(magenta(f"  │  Patient : {result.get('patient','?'):<43}│"))
    print(magenta("  └─────────────────────────────────────────────────────────┘"))
    print()

    if store_url:
        print(green("  ☁  Uploaded to Supabase Storage ✓"))
        print(f"  {dim('Receipt URL  :')} {cyan(store_url)}")
    else:
        print(yellow("  ⚠  Saved locally (Supabase Storage unreachable)"))
        print(f"  {dim('Local file   :')} {cyan(html_path)}")
    print()

    # ASCII QR
    ascii_lines = receipt.get("ascii_qr_lines", [])
    if ascii_lines:
        _print_ascii_qr(ascii_lines)
        print(dim("  " + "Scan QR to open receipt from any device".center(len(ascii_lines[0]) + 8)))
        print()

    # Public URL
    pub_url = receipt.get("public_url", "")
    if pub_url:
        print(dim("  Public link:"))
        print(f"  {cyan(pub_url[:80])}{'...' if len(pub_url) > 80 else ''}")
        print()

    # Open in browser
    try:
        if sys.platform == "win32":
            os.startfile(html_path)
        elif sys.platform == "darwin":
            os.system(f'open "{html_path}"')
        else:
            os.system(f'xdg-open "{html_path}"')
        print(dim("  Receipt opened in your browser automatically."))
    except Exception:
        print(dim(f"  Open manually: {html_path}"))
    print()


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN NORMAL MODE LOOP
# ─────────────────────────────────────────────────────────────────────────────

def run_normal_mode():
    """
    Run the full guided patient registration loop.
    Loops asking if the user wants to register another patient.
    """
    from ritmo.ticketflow import book_ticket

    while True:
        _banner()

        # ── Step 1 — Patient name ─────────────────────────────────────────────
        name = _field("Patient Name", 1, 5, required=True)
        if name is None:
            print(yellow("\n  Registration cancelled. Goodbye!"))
            return

        # ── Step 2 — Phone ────────────────────────────────────────────────────
        print()
        phone = _field("Phone Number", 2, 5, default="")
        if phone is None:
            print(yellow("\n  Registration cancelled."))
            return

        # ── Step 3 — Age ──────────────────────────────────────────────────────
        print()
        age = _field("Age", 3, 5, default="")
        if age is None:
            print(yellow("\n  Registration cancelled."))
            return

        # ── Step 4 — Department ───────────────────────────────────────────────
        dept_result = _dept_picker(4, 5)
        if dept_result is None:
            print(yellow("\n  Registration cancelled."))
            return
        dept_id, dept_name = dept_result

        # ── Step 5 — Notes ────────────────────────────────────────────────────
        print()
        notes = _field("Notes / Chief Complaint (optional)", 5, 5, default="")
        if notes is None:
            print(yellow("\n  Registration cancelled."))
            return

        # ── Confirm ───────────────────────────────────────────────────────────
        confirmed = _confirm_box(name, phone, age, dept_name, notes)
        if not confirmed:
            print(yellow("  Going back to form..."))
            continue   # re-show form

        # ── Book ──────────────────────────────────────────────────────────────
        print()
        print(dim("  Booking ticket..."))
        try:
            from ritmo.spinner import Spinner
            with Spinner("Saving ticket..."):
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
            print(red(f"  ✗ Booking failed: {result.get('message', 'Unknown error')}"))
            print()
        else:
            _print_ticket_box(result)
            _do_receipt_prompt(result)

        # ── Register another? ─────────────────────────────────────────────────
        try:
            again = input(white("  Register another patient?  [Y/n]: ")).strip().lower()
        except (KeyboardInterrupt, EOFError):
            again = "n"

        if again in ("n", "no"):
            print()
            print(dim("  Exiting Normal Mode. Goodbye!"))
            print()
            return


if __name__ == "__main__":
    run_normal_mode()
