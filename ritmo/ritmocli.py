"""
ritmo/ritmocli.py — RITMO Terminal Chat
=========================================
Run RITMO directly from the terminal. That's it.

  python ritmo/ritmocli.py             (picks mode interactively)
  python ritmo/ritmocli.py --mode hf
  python ritmo/ritmocli.py --mode offline

Two chat modes:
  hf       — calls running REKOV backend (Qwen via HuggingFace API)
  offline  — runs local Qwen via ONNX Runtime (no internet after first download)
"""

import os
import sys
import json
import uuid
import time
import re
import textwrap
import argparse
from pathlib import Path

if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError: pass

# ── Paths ──────────────────────────────────────────────────────────────────────
RITMO_DIR   = Path(__file__).resolve().parent
ROOT_DIR    = RITMO_DIR.parent
CONFIG_PATH = ROOT_DIR / "config.json"

sys.path.insert(0, str(ROOT_DIR))

# ── Shared HF + ONNX layer ────────────────────────────────────────────────────
from huggfaceonnx import onnx as _onnx_mod
OFFLINE_MODELS = _onnx_mod.OFFLINE_MODELS
from ritmo.spinner import Spinner
from ritmo.booking import book_ticket_local
from ritmo.ticketflow import book_ticket, generate_receipt, get_ticket

# ── TTS (ElevenLabs / edge-tts) ──────────────────────────────────────────────
try:
    from language.tts_engine import speak_async as _speak
except Exception:
    def _speak(text, lang=None): pass  # silent fallback

# ── pull.py (real-time HF API) ────────────────────────────────────────────────
try:
    from ritmo.pull import RitmoPull, check_pull_status
    _HAS_PULL = True
except ImportError:
    _HAS_PULL = False
    RitmoPull = None

# ── ritmoscan.py (Supabase + offline DB lookup) ───────────────────────────────
try:
    from ritmo.ritmoscan import (
        scan_tickets, scan_departments, scan_doctors, scan_receipt,
        _get_creds as _scan_get_creds,
        _print_tickets, _print_departments, _print_doctors, _print_receipt,
    )
    _HAS_SCAN = True
except ImportError:
    _HAS_SCAN = False

# ── REKOV credits ─────────────────────────────────────────────────────────────
try:
    from rekov_credits import print_rekov_credits as _print_rekov_credits
    _HAS_CREDITS = True
except ImportError:
    _HAS_CREDITS = False
    def _print_rekov_credits(**_kw): pass

# ── Support checker ───────────────────────────────────────────────────────────
try:
    from ritmo import support as _support
    _HAS_SUPPORT = True
except ImportError:
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("support", str(RITMO_DIR / "support.py"))
        _support = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_support)
        _HAS_SUPPORT = True
    except Exception:
        _HAS_SUPPORT = False

# ── ANSI ──────────────────────────────────────────────────────────────────────
class C:
    TEAL    = "\x1b[38;5;43m"
    CYAN    = "\x1b[36;1m"
    GREEN   = "\x1b[32;1m"
    YELLOW  = "\x1b[33;1m"
    RED     = "\x1b[31;1m"
    BLUE    = "\x1b[34;1m"
    MAGENTA = "\x1b[35;1m"
    WHITE   = "\x1b[97;1m"
    DIM     = "\x1b[2m"
    RESET   = "\x1b[0m"

def _c(color, text): return f"{color}{text}{C.RESET}"
def green(t):   return _c(C.GREEN,   t)
def red(t):     return _c(C.RED,     t)
def yellow(t):  return _c(C.YELLOW,  t)
def cyan(t):    return _c(C.CYAN,    t)
def teal(t):    return _c(C.TEAL,    t)
def dim(t):     return _c(C.DIM,     t)
def white(t):   return _c(C.WHITE,   t)
def blue(t):    return _c(C.BLUE,    t)
def magenta(t): return _c(C.MAGENTA, t)

# ── Config ────────────────────────────────────────────────────────────────────
def _load_config() -> dict:
    for p in [CONFIG_PATH, ROOT_DIR / "rekov" / "config.json"]:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def _check_supabase_alive() -> tuple:
    """Quick ping to Supabase REST API. Returns (ok: bool, detail: str)."""
    cfg = _load_config()
    url = cfg.get("SUPABASE_URL") or cfg.get("supabase", {}).get("url")
    key = cfg.get("SUPABASE_KEY") or cfg.get("supabase", {}).get("key")
    if not url or not key:
        return False, "No Supabase credentials in config.json"
    try:
        import urllib.request, urllib.error
        req = urllib.request.Request(
            f"{url.rstrip('/')}/rest/v1/ritmohis?select=session_id&limit=1",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status < 300:
                return True, "Connected"
            return False, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, "ritmohis table not found — run the SQL migration"
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)

def _get_hf_token(cfg: dict) -> str:
    return (
        cfg.get("hf_token") or cfg.get("HF_TOKEN")
        or os.environ.get("HF_TOKEN") or os.environ.get("HF_API_TOKEN")
        or ""
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Shared display helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _banner(mode_label: str, mode_color):
    os.system("cls" if sys.platform == "win32" else "clear")
    _print_rekov_credits(compact=True, show_contributors=False)
    # Language badge
    try:
        from language.manager import LM as _bLM
        _lang_badge = f"{_bLM.color}{_bLM.flag}  {_bLM.name}  ({_bLM.native}){C.RESET}"
    except Exception:
        _lang_badge = "[EN]  English"
    print()
    print(teal("  +-- RITMO  --  Hospital AI Assistant  (CLI) -------------------+"))
    print(teal("  |  ") + white("   Powered by HuggingFace Qwen / ONNX Offline") + teal(" " * 20 + "|"))
    print(teal("  " + "+" + "-" * 64 + "+"))
    print()
    print(f"  Mode     : {mode_color(mode_label)}")
    print(f"  Language : {_lang_badge}")
    print(dim("  /quit  /clear  /history  /lang  /receipt  /support  /help"))
    print()
    if _HAS_SUPPORT:
        _support.print_inline_status()
    print()
    print(dim("  " + "-" * 53))
    print()

def _print_ritmo(text: str):
    prefix = teal("  RITMO ->  ")
    lines  = textwrap.wrap(text, 65)
    print()
    for i, line in enumerate(lines):
        print((prefix if i == 0 else " " * 12) + white(line))
    print()
    # Speak the reply in background (non-blocking)
    _speak(text)

def _print_action(action: str, data: dict):
    print()
    if action == "BOOK_TICKET":
        print(green("  +-- ACTION: BOOKING TICKET -------------------------------------------------+"))
        for k, v in data.items():
            print(green(f"  |  {k:<20} {str(v)}"))
        print(green("  +--------------------------------------------------------------------------+"))
    elif action == "GENERATE_RECEIPT":
        print(magenta("  +-- ACTION: GENERATING RECEIPT ---------------------------------------------+"))
        for k, v in data.items():
            print(magenta(f"  |  {k:<20} {str(v)}"))
        print(magenta("  +--------------------------------------------------------------------------+"))
    elif action == "EMERGENCY":
        print(red("  +-- !!! EMERGENCY TRIAGE !!!  ---------------------------------------------+"))
        print(red("  |  Routing to Emergency immediately -- PRIORITY MAX                       |"))
        print(red("  +--------------------------------------------------------------------------+"))
    print()

# ── Shared Ticket Booking + Receipt Flow ──────────────────────────────────────

_last_ticket = {}   # stash last booked ticket so /receipt can use it


def _do_booking(action_data: dict, logger=None) -> dict:
    """
    Full booking pipeline with clear Supabase sync status.
    Collects missing fields, books via ticketflow, prints status.
    """
    global _last_ticket
    pname = action_data.get("patient_name", "")
    if not pname or pname in ("Patient", "<name>", "unknown", ""):
        pname = input(cyan("  Patient name  : ")).strip() or "Patient"
    phone = action_data.get("phone", "")
    if not phone:
        phone = input(cyan("  Phone number  : ")).strip() or "0000000000"
    age = action_data.get("age", "")
    if not age:
        age = input(cyan("  Age           : ")).strip() or "30"

    action_data.update({"patient_name": pname, "phone": phone, "age": age})

    with Spinner("Booking ticket..."):
        result = book_ticket(action_data)

    print()
    if result["ok"]:
        print(green("  +-- TICKET BOOKED ------------------------------------------------------+"))
        print(green(f"  |  Token       : {result['token']:<52}|"))
        print(green(f"  |  Ticket ID   : {result['ticket_id']:<52}|"))
        print(green(f"  |  Patient     : {result['patient']:<52}|"))
        print(green(f"  |  Department  : {result['dept_name']:<52}|"))
        print(green(f"  |  Fee         : Rs.{result['fee']:<49.2f}|"))
        print(green("  +----------------------------------------------------------------------+"))
        print()

        # Clear Supabase sync status
        if result["supabase_synced"]:
            print(green("  [CLOUD]  Stored in Supabase  [OK]") + dim("  (accessible from any device)"))
        else:
            print(yellow("  [!]     Stored locally only") + dim("  (Supabase unreachable -- saved to SQLite)"))
        print()
        print(dim("  Type your next message, or say 'generate receipt' to get a receipt."))
        print()
        # Speak booking confirmation
        _speak(f"Ticket booked. Token {result['token']} for {result['dept_name']}.")
    else:
        print(red(f"  [FAIL] Booking failed: {result['message']}"))
        print()
        _speak("Booking failed. Please try again.")

    _last_ticket = result
    if logger:
        logger.action("BOOK_TICKET", {
            "ticket_id": result.get("ticket_id"),
            "supabase_synced": result.get("supabase_synced"),
        })
    return result


def _do_receipt(ticket_data: dict = None, logger=None) -> dict:
    """
    Generate receipt + QR for the last booked ticket.
    Shows ASCII QR, storage URL, clear sync status.
    """
    global _last_ticket
    data = ticket_data or _last_ticket
    if not data or not data.get("ticket_id"):
        print(yellow("  No ticket to generate receipt for."))
        print(dim("  Book a ticket first, then ask for a receipt."))
        return {"ok": False}

    with Spinner("Generating receipt + QR code..."):
        receipt = generate_receipt(data)

    print()
    if receipt["ok"]:
        tid    = data.get("ticket_id", "?")
        token  = data.get("token", "?")
        pname  = data.get("patient", "?")
        pub_url = receipt.get("public_url", "")
        store_url = receipt.get("storage_url", "")
        html_path = receipt.get("html_path", "")

        print(magenta("  +-- RECEIPT GENERATED -----------------------------------------------+"))
        print(magenta(f"  |  Ticket  : {tid:<51}|"))
        print(magenta(f"  |  Token   : {token:<51}|"))
        print(magenta(f"  |  Patient : {pname:<51}|"))
        print(magenta("  +-------------------------------------------------------------------+"))
        print()

        # Storage sync status
        if store_url:
            print(green("  [CLOUD]  Uploaded to Supabase Storage  [OK]"))
            print(f"  {dim('Receipt URL  :')} {cyan(store_url)}")
        else:
            print(yellow("  [!]  Saved locally (Supabase Storage unreachable)"))
            print(f"  {dim('Local file   :')} {cyan(html_path)}")
        print()

        # ASCII QR code in terminal -- plain print, no extra file handles
        ascii_lines = receipt.get("ascii_qr_lines", [])
        if ascii_lines:
            w = len(ascii_lines[0]) + 4
            print("  +" + "-" * w + "+")
            for ln in ascii_lines:
                print("  |  " + ln + "  |")
            print("  +" + "-" * w + "+")
            print(dim("  Scan QR to open receipt from any device."))
            print()

        # Public URL hint
        if pub_url:
            print(dim("  Public link:"))
            print(f"  {cyan(pub_url[:80])}{'...' if len(pub_url) > 80 else ''}")
            print()

        # Open receipt in browser
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
        # Speak receipt ready
        _speak("Receipt is ready. Scan the QR code or check your browser.")
    else:
        print(red(f"  [FAIL] Receipt generation failed: {receipt.get('message', '?')}"))
        print()
        _speak("Receipt generation failed. Please try again.")

    if logger:
        logger.action("GENERATE_RECEIPT", {
            "ticket_id": data.get("ticket_id"),
            "receipt_synced": receipt.get("receipt_synced"),
            "storage_url": receipt.get("storage_url"),
        })
    return receipt


def _user_prompt() -> str:
    try:
        return input(cyan("  You   ->  ")).strip()
    except (KeyboardInterrupt, EOFError):
        return "/quit"

def _parse_action(reply: str) -> tuple:
    """Extract [BOOK_TICKET] / [EMERGENCY] / [GENERATE_RECEIPT] from model reply.
    
    Handles model quirks:
    - Sanitises literal placeholders like ticket_id=<ticket_id> → ignored
    - Only triggers on the FIRST action found (prevents duplicates)
    - Strips angle-bracket placeholders from parsed data
    """
    text = reply.upper()
    if "[EMERGENCY]" in text:
        return "EMERGENCY", {}
    
    # Only match the first action found to prevent repeated triggers
    positions = {}
    for tag in ("[BOOK_TICKET]", "[GENERATE_RECEIPT]"):
        idx = reply.find(tag)
        if idx != -1:
            positions[tag] = idx
    if not positions:
        return None, {}
    
    first_tag = min(positions, key=positions.get)
    
    # Parse key=value pairs from that line only
    line = reply[positions[first_tag]:]
    line = line.split("\n")[0]  # only first line after the tag
    data = {}
    for part in line.split():
        if "=" in part:
            k, _, v = part.partition("=")
            k = k.strip("[]").lower()
            # Skip template placeholders like <ticket_id>, <name>, <id>
            if v.startswith("<") and v.endswith(">"):
                continue
            if v not in ("", "None", "null"):
                data[k] = v
    
    return first_tag.strip("[]"), data


def _handle_common_cmd(cmd: str, history: list, mode_fn, logger=None) -> bool:
    """Handle /commands shared across both modes. Returns True if handled."""
    if cmd.lower() in ("/quit", "/q", "quit", "exit"):
        if logger:
            logger.end_session("ended")
        print()
        print(dim("  Goodbye. Stay healthy!"))
        _speak("Goodbye. Stay healthy!")
        sys.exit(0)

    if cmd.lower() == "/clear":
        if logger:
            logger.end_session("abandoned")
        history.clear()
        mode_fn()
        return True

    if cmd.lower() == "/history":
        print()
        if not history:
            print(dim("  No history yet."))
        else:
            for turn in history:
                role  = "You  " if turn["role"] == "user" else "RITMO"
                color = cyan if turn["role"] == "user" else teal
                print(f"  {color(role)} ->  {turn['content']}")
        print()
        return True

    if cmd.lower() == "/help":
        print()
        cmds = [
            ("/quit",      "exit RITMO"),
            ("/clear",     "start new session"),
            ("/history",   "show conversation history"),
            ("/receipt",   "generate receipt + QR for last booked ticket"),
            ("/support",   "config + setup diagnostics"),
            ("/scan",      "lookup tickets/patients/depts in Supabase"),
            ("/awake",     "show Keep-Alive System Stats"),
            ("/help",      "show this help"),
        ]
        for c, d in cmds:
            print(f"  {cyan(c):<22}  {dim(d)}")
        print()
        return True

    if cmd.lower() in ("/support", "/check", "/status"):
        print()
        if _HAS_SUPPORT:
            _support.run_full_check(verbose=True, ping_hf=False)
        else:
            print(yellow("  ritmo/support.py not found."))
        print()
        return True

    if cmd.lower() == "/awake":
        print()
        print(teal("  ╔══════════════════════════════════════════════════════╗"))
        print(teal("  ║") + white("   AWAKE SYSTEM MONITOR                           ") + teal("║"))
        print(teal("  ╚══════════════════════════════════════════════════════╝"))
        print(dim("  Watermarks & Dev: ") + cyan("pheonix14"))
        print(dim("  Repo: ") + "https://github.com/pheonix14/rekov")
        print()
        try:
            from awake.stats import get_stats
            st = get_stats()
            print(f"  Uptime:         {st.get('uptime_human')}")
            print(f"  Total Packets:  {st.get('total_packets')}")
            sb = st.get('supabase', {})
            rd = st.get('render', {})
            print(f"  Supabase Pings: {sb.get('total')} ({sb.get('success')} OK)")
            print(f"  Render Pings:   {rd.get('total')} ({rd.get('success')} OK)")
        except ImportError:
            print(yellow("  Awake module not available."))
        print()
        return True

    if cmd.lower() == "/receipt":
        _do_receipt(logger=logger)
        return True

    if cmd.lower().startswith("/scan"):
        _handle_scan_cmd(cmd)
        return True

    if cmd.lower() in ("/lang", "/language"):
        try:
            from language.picker  import switch_language_prompt
            from language.manager import LM as _cLM, set_lang
            new_key = switch_language_prompt(current=_cLM.active)
            set_lang(new_key)
            from language.manager import LM as _cLM2
            print()
            print(green(f"  Language set to: {_cLM2.flag}  {_cLM2.name}  ({_cLM2.native})"))
            print()
        except Exception as _le:
            print(yellow(f"  [LANG] Could not switch language: {_le}"))
        return True

    return False


def _handle_scan_cmd(cmd: str):
    """Parse and run /scan sub-commands inside chat."""
    if not _HAS_SCAN:
        print(yellow("  ritmoscan.py not available."))
        return
    from ritmo.ritmoscan import _load_config as _sc_cfg
    creds = _scan_get_creds(_sc_cfg())
    parts = cmd.strip().split()
    sub   = parts[1].lower() if len(parts) > 1 else "help"
    arg   = " ".join(parts[2:]) if len(parts) > 2 else ""

    print()
    if sub in ("tickets", "queue"):
        r = scan_tickets(creds, limit=15)
        _print_tickets(r.get("data", []), r.get("source", "?"))
    elif sub == "patient":
        r = scan_tickets(creds, patient=arg, limit=15)
        if r.get("supabase_error"):
            print(warn(f"Supabase offline — showing local: {r['supabase_error']}"))
        _print_tickets(r.get("data", []), r.get("source", "?"))
    elif sub == "ticket":
        r = scan_tickets(creds, token=arg, limit=5)
        _print_tickets(r.get("data", []), r.get("source", "?"))
    elif sub in ("dept", "departments"):
        from ritmo.ritmoscan import scan_departments
        r = scan_departments(creds)
        _print_departments(r.get("data", []), r.get("source", "?"))
    elif sub in ("doctor", "doctors"):
        r = scan_doctors(creds, name=arg)
        _print_doctors(r.get("data", []), r.get("source", "?"))
    elif sub == "receipt":
        r = scan_receipt(creds, arg)
        _print_receipt(r)
    else:
        print(dim("  /scan tickets               — recent queue"))
        print(dim("  /scan patient <name>        — search by patient"))
        print(dim("  /scan ticket <ID>           — lookup by ticket ID"))
        print(dim("  /scan dept                  — list departments"))
        print(dim("  /scan doctor <name>         — search doctors"))
        print(dim("  /scan receipt <ticket_id>   — fetch PDF receipt URL"))
        print()


# ═══════════════════════════════════════════════════════════════════════════════
#  HuggingFace chat (Independent Online Mode)
# ═══════════════════════════════════════════════════════════════════════════════

def run_hf_mode():
    _banner("Online Mode  (Direct HuggingFace Inference API)", blue)

    cfg   = _load_config()
    token = _get_hf_token(cfg)
    
    if not token:
        print(red("  [ERR] No HF token found. Online mode requires a HuggingFace token."))
        print(dim("  Set 'hf_token' in config.json or use Offline mode."))
        sys.exit(1)

    rp = RitmoPull(token=token)
    
    try:
        from ritmo.ritmolog import RitmoLogger
        logger = RitmoLogger(mode="online", model=rp.model)
        session_id = logger.session_id
    except ImportError:
        logger = None
        session_id = rp.session_id

    print()
    sb_ok, sb_detail = _check_supabase_alive()
    sb_icon = green("CLOUD SYNC ON") if sb_ok else red("CLOUD SYNC OFF")
    print(f"  Session  : {cyan(session_id[:8])}")
    print(f"  Storage  : {sb_icon}  {dim('(' + sb_detail + ')')}")

    # Language info
    try:
        from language.manager import LM as _hfLM
        _hf_lang_badge = f"{_hfLM.color}{_hfLM.flag}  {_hfLM.name}  ({_hfLM.native}){C.RESET}"
        _hf_lang_name  = _hfLM.name
    except Exception:
        _hf_lang_badge = "[EN]  English"
        _hf_lang_name  = "English"

    print(f"  Language : {_hf_lang_badge}")
    if sb_ok:
        print(dim("  Chat history will be saved to Supabase [ritmohis] for 7 days."))
    else:
        print(dim("  Chat history saved locally (base/logs/ritmo_sessions.jsonl)."))
    print()
    print(teal("  RITMO -> ") + white(f"Hello! I am RITMO, your hospital assistant."))
    print("          " + white(f"I will respond in {_hf_lang_name}. How can I help you today?"))
    print()

    while True:
        user_input = _user_prompt()
        if not user_input:
            continue
        if _handle_common_cmd(user_input, rp.conversation, run_hf_mode, logger):
            continue

        # Inject language context into user message so AI responds in right lang
        try:
            from language.manager import LM as _hfLM2
            _hf_lang2 = _hfLM2.name
        except Exception:
            _hf_lang2 = "English"
        lang_ctx = f"[Respond in {_hf_lang2}. Understand input in any language.] "
        user_input_with_lang = lang_ctx + user_input

        if logger:
            logger.message("user", user_input)

        with Spinner("Sending to HuggingFace..."):
            reply, ms, source, action, action_data = rp.send(user_input_with_lang)

        # Re-parse action just in case it wasn't caught
        if not action:
            action, action_data = _parse_action(reply)
            
        display = re.sub(r"\[BOOK_TICKET\][^\n]*", "", reply).strip()
        display = re.sub(r"\[GENERATE_RECEIPT\][^\n]*", "", display).strip()
        display = re.sub(r"\[EMERGENCY\][^\n]*", "", display).strip()

        _print_ritmo(display or reply)
        print(dim(f"  ({ms / 1000.0:.1f}s | {rp.model})"))

        if logger:
            logger.message("assistant", reply)

        if action:
            _print_action(action, action_data)
            if action == "BOOK_TICKET":
                _do_booking(action_data, logger)
            elif action == "GENERATE_RECEIPT":
                _do_receipt(logger=logger)
            elif action == "EMERGENCY":
                _do_booking({"dept_id": "dep_emg", **action_data}, logger)


# ═══════════════════════════════════════════════════════════════════════════════
#  Offline chat
# ═══════════════════════════════════════════════════════════════════════════════

def _pick_offline_model() -> str:
    print()
    print(white("  Select offline model  (ONNX — no PyTorch needed):"))
    print()
    for key, m in OFFLINE_MODELS.items():
        print(f"    {cyan(key)}  {m['label']}")
    print()
    while True:
        choice = input(white("  Choose [1/2/3] (default=1): ")).strip() or "1"
        if choice in OFFLINE_MODELS:
            return OFFLINE_MODELS[choice]["id"]
        print(red(f"  Invalid: '{choice}'. Enter 1, 2, or 3."))


def run_offline_mode():
    _banner("Offline Mode  (local Qwen via ONNX — no internet needed)", green)

    # Install deps if missing
    if not _onnx_mod.check_onnx_deps():
        print(yellow("  optimum[onnxruntime] not found."))
        if input(yellow("  Install now? [Y/n]: ")).strip().lower() != "n":
            _onnx_mod.install_onnx_deps()
        else:
            print(red("  Cannot run offline mode without ONNX Runtime."))
            sys.exit(1)

    model_id   = _pick_offline_model()
    short_name = model_id.split("/")[-1]

    print()
    print(blue(f"  Loading {short_name} (ONNX)..."))
    models_cache = ROOT_DIR / "base" / "models"
    onnx_cache   = models_cache / (short_name + "-onnx")

    if onnx_cache.exists():
        print(dim(f"  Cache: base/models/{short_name}-onnx"))
    else:
        print(yellow(f"  First run — downloading + exporting to ONNX..."))
        print(dim("  One-time only. Future loads take seconds."))
        print()

    try:
        cfg   = _load_config()
        token = _get_hf_token(cfg)
        with Spinner(f"Loading {short_name} into RAM (ONNX)..."):
            tokenizer, model = _onnx_mod.load_model(model_id, models_cache, token=token)
        print(green(f"  {short_name} loaded successfully."))
    except RuntimeError as e:
        print(red(f"  {e}"))
        print(dim("  Run: python ritmo/support.py --fix"))
        sys.exit(1)

    print()
    print(dim("  " + "─" * 53))
    print(dim(f"  Model: {short_name}   |   /quit to exit"))
    print(dim("  " + "─" * 53))
    print()
    
    try:
        from ritmo.ritmolog import RitmoLogger
        logger = RitmoLogger(mode="offline", model=short_name)
        session_id = logger.session_id
    except ImportError:
        import uuid
        logger = None
        session_id = str(uuid.uuid4())
        
    sb_ok, sb_detail = _check_supabase_alive()
    sb_icon = green("[CLOUD] SYNC ON") if sb_ok else red("[!] CLOUD SYNC OFF")
    print(f"  Session : {cyan(session_id[:8])}")
    print(f"  Storage : {sb_icon}  {dim('(' + sb_detail + ')')}")
    if sb_ok:
        print(dim("  Chat history will be saved to Supabase [ritmohis] for 7 days."))
    else:
        print(dim("  Chat history saved locally only (base/logs/ritmo_sessions.jsonl)."))
    print()

    from ritmo.pull import get_system_prompt
    conversation: list = [{"role": "system", "content": get_system_prompt()}]
    greeting = "Hello! I am RITMO, your hospital assistant. What health issue can I help you with today?"
    _print_ritmo(greeting)
    conversation.append({"role": "assistant", "content": greeting})

    while True:
        user_input = _user_prompt()
        if not user_input:
            continue

        if user_input.lower() == "/model":
            print(dim(f"  Model: {model_id}")); print(); continue

        if _handle_common_cmd(user_input, conversation, run_offline_mode, logger):
            continue

        if logger:
            logger.message("user", user_input)

        conversation.append({"role": "user", "content": user_input})

        t0 = time.time()
        with Spinner(f"{short_name} is thinking..."):
            reply   = _onnx_mod.generate(tokenizer, model, conversation)
        elapsed = time.time() - t0

        reply = re.sub(r"<\|[^|]+\|>", "", reply).strip()
        conversation.append({"role": "assistant", "content": reply})

        print(" " * 55, end="\r")

        # Strip action tokens from display text
        display = re.sub(r"\[BOOK_TICKET\][^\n]*", "", reply).strip()
        display = re.sub(r"\[GENERATE_RECEIPT\][^\n]*", "", display).strip()
        display = re.sub(r"\[EMERGENCY\][^\n]*", "", display).strip()
        _print_ritmo(display or reply)
        print(dim(f"  ({elapsed:.1f}s | {short_name})"))

        action, action_data = _parse_action(reply)
        
        if logger:
            logger.message("assistant", reply)

        if action:
            _print_action(action, action_data)
            if action == "BOOK_TICKET":
                _do_booking(action_data, logger)
            elif action == "GENERATE_RECEIPT":
                _do_receipt(logger=logger)
            elif action == "EMERGENCY":
                _do_booking({"dept_id": "dep_emg", **action_data}, logger)


# ═══════════════════════════════════════════════════════════════════════════════
#  Mode selector
# ═══════════════════════════════════════════════════════════════════════════════

def _pick_mode() -> str:
    os.system("cls" if sys.platform == "win32" else "clear")
    _print_rekov_credits(show_contributors=False, fetch_live=False)
    print()
    print(teal("  ╔══════════════════════════════════════════════════════╗"))
    print(teal("  ║") + white("   RITMO  CLI  —  Mode Select                         ") + teal("║"))
    print(teal("  ╚══════════════════════════════════════════════════════╝"))
    print()

    if _HAS_SUPPORT:
        status = _support.print_inline_status()
        print()
        hf_ok  = status.get("hf_ready", False)
        off_ok = status.get("offline_ready", False)
    else:
        hf_ok = off_ok = True

    print(dim("  " + "─" * 53)); print()
    print(f"  {blue('1')}  ->  {white('Online Mode')}    [{green('READY') if hf_ok else yellow('needs config')}]")
    print(dim("       Fast HF API inference (Requires Internet & HF Token)"))
    print()
    print(f"  {green('2')}  ->  {white('Offline Mode')}   [{green('READY') if off_ok else yellow('needs download')}]")
    print(dim("       Runs local Qwen via ONNX (no internet after download)"))
    print()
    print(dim("  " + "─" * 53)); print()

    while True:
        try:
            choice = input(white("  Enter choice [1/2]: ")).strip()
        except (KeyboardInterrupt, EOFError):
            print(); sys.exit(0)
        if choice == "1": return "hf"
        if choice == "2": return "offline"
        print(red(f"  Invalid: '{choice}'. Enter 1 or 2."))


# ═══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="RITMO CLI — REKOV Hospital AI Chat",
    )
    parser.add_argument("--mode", choices=["hf", "offline"], default=None,
                        help="hf = HuggingFace API  |  offline = local ONNX")
    args = parser.parse_args()

    mode = args.mode or _pick_mode()

    if mode == "hf":
        run_hf_mode()
    else:
        run_offline_mode()


if __name__ == "__main__":
    main()
