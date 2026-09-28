"""
ritmo/ritmoscan.py
===================
RITMO — Supabase Database Lookup with Offline Backup.

Scans Supabase (and local SQLite as fallback) for RITMO-relevant data:
  - Tickets / queue entries
  - Departments
  - Doctors
  - Receipts / PDF URLs

Why two sources?
  ONLINE  — Supabase REST API (live, authoritative)
  OFFLINE — local SQLite at base/data/local.db (works without internet,
             data may be hours old; synced by the backend sync service)

Usage:
  python ritmo/ritmoscan.py --tickets                  # all tickets
  python ritmo/ritmoscan.py --ticket T4AF1             # by token
  python ritmo/ritmoscan.py --patient "John"           # search by name
  python ritmo/ritmoscan.py --dept                     # list departments
  python ritmo/ritmoscan.py --doctor "Dr. Smith"       # search doctors
  python ritmo/ritmoscan.py --receipt T001             # fetch receipt/PDF URL
  python ritmo/ritmoscan.py --status                   # connection status
  python ritmo/ritmoscan.py --scan-all                 # full audit of all tables

Called by: ritmo/ritmocli.py (/scan command inside chat)
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
import argparse
from pathlib import Path
from typing import Optional

# ── Paths ─────────────────────────────────────────────────────────────────────
RITMO_DIR = Path(__file__).resolve().parent
ROOT_DIR  = RITMO_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

# ── ANSI ──────────────────────────────────────────────────────────────────────
GREEN   = "\x1b[32;1m"
RED     = "\x1b[31;1m"
YELLOW  = "\x1b[33;1m"
CYAN    = "\x1b[36;1m"
TEAL    = "\x1b[38;5;43m"
WHITE   = "\x1b[97;1m"
DIM     = "\x1b[2m"
RESET   = "\x1b[0m"

def _c(code, t): return f"{code}{t}{RESET}"
def ok(t):   return _c(GREEN,  f"  [OK]   {t}")
def err(t):  return _c(RED,    f"  [FAIL] {t}")
def warn(t): return _c(YELLOW, f"  [WARN] {t}")
def info(t): return _c(CYAN,   f"  [INFO] {t}")
def dim(t):  return _c(DIM,    f"  {t}")
def hdr(t):  return _c(WHITE,  f"\n  ── {t} ──")


# ═══════════════════════════════════════════════════════════════════════════════
#  Config / credentials
# ═══════════════════════════════════════════════════════════════════════════════

def _load_config() -> dict:
    for p in [ROOT_DIR / "config.json", ROOT_DIR / "rekov" / "config.json"]:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def _get_creds(cfg: dict = None) -> dict:
    cfg  = cfg or _load_config()
    sb   = cfg.get("supabase", {}) if isinstance(cfg.get("supabase"), dict) else {}
    url  = sb.get("url") or cfg.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL", "")
    key  = sb.get("key") or cfg.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY", "")
    return {"url": url.rstrip("/"), "key": key}


# ═══════════════════════════════════════════════════════════════════════════════
#  Supabase REST helper
# ═══════════════════════════════════════════════════════════════════════════════

def _sb_get(creds: dict, table: str, params: str = "", timeout: int = 10) -> dict:
    """
    GET from a Supabase REST table.
    params: URL-encoded filter string e.g. "patient_name=ilike.*John*&limit=20"
    Returns {"ok": bool, "data": list, "error": str|None, "ms": int}
    """
    result = {"ok": False, "data": [], "error": None, "ms": 0, "source": "supabase"}
    if not creds["url"] or not creds["key"]:
        result["error"] = "Supabase credentials missing"
        return result

    url = f"{creds['url']}/rest/v1/{table}?select=*"
    if params:
        url += "&" + params.lstrip("&")
    headers = {
        "apikey":        creds["key"],
        "Authorization": f"Bearer {creds['key']}",
        "Accept":        "application/json",
        "User-Agent":    "REKOV-RitmoScan/1.0",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        t0  = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ms   = int((time.time() - t0) * 1000)
            data = json.loads(r.read().decode())
            result.update({"ok": True, "data": data if isinstance(data, list) else [data], "ms": ms})
    except urllib.error.HTTPError as e:
        result["error"] = f"HTTP {e.code}"
    except Exception as ex:
        result["error"] = str(ex)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Offline backup — local SQLite via SQLAlchemy
# ═══════════════════════════════════════════════════════════════════════════════

def _offline_query(query_fn) -> dict:
    """
    Run query_fn(session) → list of dicts against local SQLite.
    Returns {"ok": bool, "data": list, "error": str|None, "source": "offline"}
    """
    try:
        from base.database import SessionLocal
        db = SessionLocal()
        try:
            data = query_fn(db)
            return {"ok": True, "data": data, "error": None, "source": "offline"}
        finally:
            db.close()
    except Exception as ex:
        return {"ok": False, "data": [], "error": str(ex), "source": "offline"}


def _row_to_dict(row) -> dict:
    """Convert SQLAlchemy model instance to plain dict."""
    try:
        return {c.name: getattr(row, c.name) for c in row.__table__.columns}
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════════════════════
#  Lookup functions
# ═══════════════════════════════════════════════════════════════════════════════

def scan_tickets(
    creds: dict,
    token: str = "",
    patient: str = "",
    status_filter: str = "",
    limit: int = 20,
) -> dict:
    """
    Scan tickets table.
      token   — filter by token_number (e.g. "T4AF1")
      patient — ILIKE search on patient_name
      status  — WAITING | IN_CONSULTATION | COMPLETED | CANCELLED
    Falls back to local SQLite if Supabase fails.
    """
    params = f"limit={limit}&order=created_at.desc"
    if token:
        params += f"&ticket_number=eq.{token}"
    if patient:
        params += f"&patient_name=ilike.*{patient}*"
    if status_filter:
        params += f"&status=eq.{status_filter}"

    result = _sb_get(creds, "tickets", params)

    if not result["ok"]:
        # Offline fallback
        def _q(db):
            from base.models import TicketModel
            from sqlalchemy import or_
            q = db.query(TicketModel)
            if token:
                q = q.filter(TicketModel.ticket_id == token)
            if patient:
                q = q.filter(TicketModel.patient_name.ilike(f"%{patient}%"))
            if status_filter:
                q = q.filter(TicketModel.status == status_filter)
            return [_row_to_dict(r) for r in q.order_by(TicketModel.created_at.desc()).limit(limit)]

        fallback = _offline_query(_q)
        if fallback["ok"]:
            fallback["supabase_error"] = result["error"]
            return fallback

    return result


def scan_departments(creds: dict) -> dict:
    """Fetch all departments from Supabase (or offline from config)."""
    result = _sb_get(creds, "departments", "order=name.asc")
    if not result["ok"] or not result["data"]:
        # Offline: use hardcoded known departments from REKOV
        result["data"] = [
            {"id": "dep_gen",   "name": "General",      "room": "R-101"},
            {"id": "dep_card",  "name": "Cardiology",   "room": "R-201"},
            {"id": "dep_neuro", "name": "Neurology",    "room": "R-301"},
            {"id": "dep_orth",  "name": "Orthopedics",  "room": "R-401"},
            {"id": "dep_peds",  "name": "Pediatrics",   "room": "R-501"},
            {"id": "dep_emg",   "name": "Emergency",    "room": "R-001"},
        ]
        result["source"]  = "offline_config"
        result["ok"]      = True
    return result


def scan_doctors(creds: dict, name: str = "", dept: str = "") -> dict:
    """Search doctors by name or department."""
    params = "limit=50"
    if name:
        params += f"&name=ilike.*{name}*"
    if dept:
        params += f"&department_id=eq.{dept}"

    result = _sb_get(creds, "doctors", params)
    if not result["ok"] or not result["data"]:
        # Offline: pull from local doctor_credentials
        def _q(db):
            from base.models import DoctorCredentials
            q = db.query(DoctorCredentials)
            if name:
                q = q.filter(DoctorCredentials.username.ilike(f"%{name}%"))
            return [_row_to_dict(r) for r in q.limit(50)]
        fallback = _offline_query(_q)
        if fallback["ok"] and fallback["data"]:
            fallback["supabase_error"] = result.get("error")
            return fallback
    return result


def scan_receipt(creds: dict, ticket_id: str) -> dict:
    """
    Find the PDF receipt URL for a given ticket_id.
    Returns {"ok": bool, "pdf_url": str|None, "data": dict, "source": str}
    """
    result = _sb_get(creds, "tickets", f"ticket_id=eq.{ticket_id}&select=ticket_id,patient_name,receipt_pdf_url,status")
    pdf_url = None
    row     = {}

    if result["ok"] and result["data"]:
        row     = result["data"][0]
        pdf_url = row.get("receipt_pdf_url")
        if not pdf_url:
            result["warn"] = "Ticket found but no receipt PDF — may not have been generated yet"
    elif not result["ok"]:
        # Offline fallback
        def _q(db):
            from base.models import TicketModel
            t = db.query(TicketModel).filter(TicketModel.ticket_id == ticket_id).first()
            return [_row_to_dict(t)] if t else []
        fallback = _offline_query(_q)
        if fallback["ok"] and fallback["data"]:
            row     = fallback["data"][0]
            pdf_url = row.get("receipt_pdf_url")
            result  = fallback

    result["pdf_url"] = pdf_url
    result["data"]    = row
    return result


def scan_all(creds: dict, verbose: bool = True) -> dict:
    """Full audit scan of all REKOV tables — counts rows and reports health."""
    report = {}
    tables = ["tickets", "departments", "doctors", "bot_sessions", "mobile_sessions"]
    print(hdr("RitmoScan — Full Table Audit"))
    for table in tables:
        r = _sb_get(creds, table, "limit=1")
        if r["ok"]:
            # Get real count
            count_result = _sb_get(creds, table, "select=count")
            count_str = str(len(r["data"]))
            print(ok(f"{table:<22} reachable  ({count_str} row sample in {r['ms']}ms)"))
            report[table] = {"ok": True, "ms": r["ms"]}
        else:
            print(err(f"{table:<22} {r['error']}"))
            report[table] = {"ok": False, "error": r["error"]}

    # Local SQLite
    try:
        from base.database import engine
        from sqlalchemy import inspect
        insp   = inspect(engine)
        tables = insp.get_table_names()
        print(ok(f"{'local SQLite':<22} {len(tables)} tables"))
        report["local_sqlite"] = {"ok": True, "tables": tables}
    except Exception as ex:
        print(warn(f"local SQLite not accessible: {ex}"))
        report["local_sqlite"] = {"ok": False, "error": str(ex)}

    return report


# ═══════════════════════════════════════════════════════════════════════════════
#  Display helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _print_tickets(rows: list, source: str):
    if not rows:
        print(warn("No tickets found."))
        return
    print(hdr(f"Tickets  ({len(rows)} results — source: {source})"))
    print()
    for r in rows:
        ts     = str(r.get("created_at", ""))[:16]
        status = r.get("status", "?")
        sc     = GREEN if status == "COMPLETED" else (RED if status == "CANCELLED" else YELLOW)
        print(
            f"  {TEAL}{r.get('ticket_id','?'):<12}{RESET}"
            f"  {sc}{status:<20}{RESET}"
            f"  {r.get('patient_name','?'):<18}"
            f"  {DIM}{r.get('department_name', r.get('department_id','?')):<15}{RESET}"
            f"  {DIM}{ts}{RESET}"
        )
    print()


def _print_departments(rows: list, source: str):
    print(hdr(f"Departments  ({len(rows)} — source: {source})"))
    print()
    for r in rows:
        print(
            f"  {CYAN}{r.get('id', r.get('department_id','?')):<12}{RESET}"
            f"  {r.get('name','?'):<20}"
            f"  {DIM}Room: {r.get('room','?')}{RESET}"
        )
    print()


def _print_doctors(rows: list, source: str):
    print(hdr(f"Doctors  ({len(rows)} — source: {source})"))
    print()
    for r in rows:
        print(
            f"  {TEAL}{r.get('doctor_id', r.get('id','?')):<12}{RESET}"
            f"  {r.get('name', r.get('username','?')):<25}"
            f"  {DIM}{r.get('department_id','')}{RESET}"
        )
    print()


def _print_receipt(result: dict):
    print(hdr("Receipt"))
    print()
    data    = result.get("data", {})
    pdf_url = result.get("pdf_url")
    src     = result.get("source", "?")

    print(f"  Ticket   : {data.get('ticket_id','?')}")
    print(f"  Patient  : {data.get('patient_name','?')}")
    print(f"  Status   : {data.get('status','?')}")
    print(f"  Source   : {src}")
    print()
    if pdf_url:
        print(f"  {GREEN}PDF URL{RESET}  : {pdf_url}")
    else:
        print(warn("No PDF URL found for this ticket."))
        print(dim("PDF is generated after booking completes and backend syncs."))
    print()


def _print_status(creds: dict):
    print(hdr("RitmoScan — Connection Status"))
    print()

    # Supabase
    has_url = bool(creds["url"])
    has_key = bool(creds["key"])
    print(f"  Supabase URL : {'set — ' + creds['url'][:45] if has_url else RED + 'MISSING' + RESET}")
    print(f"  Supabase Key : {'set (' + str(len(creds['key'])) + ' chars)' if has_key else RED + 'MISSING' + RESET}")

    if has_url and has_key:
        r = _sb_get(creds, "tickets", "limit=1")
        if r["ok"]:
            print(ok(f"Supabase REST reachable  ({r['ms']}ms)"))
        else:
            print(err(f"Supabase REST failed: {r['error']}"))

    # Local SQLite
    try:
        from base.database import DB_PATH
        if os.path.exists(DB_PATH):
            size = os.path.getsize(DB_PATH) / 1024
            print(ok(f"Local SQLite at {DB_PATH}  ({size:.0f} KB)"))
        else:
            print(warn("Local SQLite not found — backend never ran locally?"))
    except Exception as ex:
        print(warn(f"Local SQLite check error: {ex}"))

    print()


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="RitmoScan — Supabase + local DB lookup for RITMO",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ritmo/ritmoscan.py --status
  python ritmo/ritmoscan.py --tickets
  python ritmo/ritmoscan.py --ticket T4AF1
  python ritmo/ritmoscan.py --patient "John"
  python ritmo/ritmoscan.py --dept
  python ritmo/ritmoscan.py --doctor "Dr. Smith"
  python ritmo/ritmoscan.py --receipt TKT001
  python ritmo/ritmoscan.py --scan-all
        """,
    )
    ap.add_argument("--status",   action="store_true",  help="Show connection status")
    ap.add_argument("--tickets",  action="store_true",  help="List recent tickets")
    ap.add_argument("--ticket",   metavar="ID",         help="Lookup specific ticket by token/ID")
    ap.add_argument("--patient",  metavar="NAME",       help="Search tickets by patient name")
    ap.add_argument("--dept",     action="store_true",  help="List all departments")
    ap.add_argument("--doctor",   metavar="NAME",       help="Search doctors by name")
    ap.add_argument("--receipt",  metavar="TICKET_ID",  help="Fetch receipt/PDF URL for a ticket")
    ap.add_argument("--scan-all", action="store_true",  help="Full table audit")
    ap.add_argument("--limit",    type=int, default=20, help="Max results (default 20)")
    ap.add_argument("--status-filter", metavar="STATUS",
                    help="Filter tickets: WAITING|IN_CONSULTATION|COMPLETED|CANCELLED")
    args = ap.parse_args()

    print(f"\n  {TEAL}RitmoScan{RESET}  —  REKOV Database Lookup\n")

    cfg   = _load_config()
    creds = _get_creds(cfg)

    if args.status:
        _print_status(creds)
        return

    if args.scan_all:
        scan_all(creds)
        return

    if args.dept:
        r = scan_departments(creds)
        _print_departments(r.get("data", []), r.get("source", "?"))
        return

    if args.doctor:
        r = scan_doctors(creds, name=args.doctor)
        _print_doctors(r.get("data", []), r.get("source", "?"))
        return

    if args.receipt:
        r = scan_receipt(creds, args.receipt)
        _print_receipt(r)
        return

    if args.ticket or args.patient or args.tickets:
        r = scan_tickets(
            creds,
            token          = args.ticket or "",
            patient        = args.patient or "",
            status_filter  = args.status_filter or "",
            limit          = args.limit,
        )
        if not r["ok"] and not r["data"]:
            print(err(f"Lookup failed: {r.get('error')}"))
            if r.get("supabase_error"):
                print(warn(f"Supabase: {r['supabase_error']}"))
        else:
            if r.get("supabase_error"):
                print(warn(f"Supabase offline — showing local data: {r['supabase_error']}"))
            _print_tickets(r.get("data", []), r.get("source", "?"))
        return

    ap.print_help()


if __name__ == "__main__":
    main()
