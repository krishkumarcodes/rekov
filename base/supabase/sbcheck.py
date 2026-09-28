"""
base/supabase/sbcheck.py
=========================
REKOV — Supabase Credential & Connectivity Checker.

Diagnoses every common reason why data stops appearing in Supabase or
PDF receipts go missing:

  1. Credential loading     — config.json present? URL + key non-empty?
  2. URL reachability       — can we reach the Supabase REST endpoint at all?
  3. Key validation         — is the anon/service key accepted (HTTP 200/401/403)?
  4. Table read probe       — can we SELECT from core REKOV tables?
  5. Table write probe      — can we INSERT + DELETE a canary row?
  6. Storage bucket probe   — can we list the receipts/pdfs storage bucket?
  7. PDF URL probe          — given a sample PDF URL, is it actually reachable?
  8. Row-Level Security     — detect if RLS is blocking reads (row count == 0 but
                               no error)

Everything is logged to:
  base/logs/supabase_checks.log   (flat human-readable)
  base/logs/supabase_checks.jsonl (structured, one record per run)

Usage:
  python base/supabase/sbcheck.py              # full interactive report
  python base/supabase/sbcheck.py --quick      # creds + reachability only
  python base/supabase/sbcheck.py --json       # machine-readable output
  python base/supabase/sbcheck.py --fix        # guided fix wizard
  python base/supabase/sbcheck.py --pdf <url>  # probe a specific PDF URL
"""

import os
import sys
import json
import time
import uuid
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT_DIR  = Path(__file__).resolve().parent.parent.parent   # rekov-6.0.0/
BASE_DIR  = ROOT_DIR / "base"
LOGS_DIR  = BASE_DIR / "logs"
CONFIG_CANDIDATES = [
    ROOT_DIR / "config.json",
    BASE_DIR / "config.json",
    ROOT_DIR / "rekov" / "config.json",
]

sys.path.insert(0, str(ROOT_DIR))

# ── ANSI ──────────────────────────────────────────────────────────────────────
RESET   = "\x1b[0m"
BOLD    = "\x1b[1m"
DIM     = "\x1b[2m"
GREEN   = "\x1b[32;1m"
RED     = "\x1b[31;1m"
YELLOW  = "\x1b[33;1m"
CYAN    = "\x1b[36;1m"
WHITE   = "\x1b[97;1m"
TEAL    = "\x1b[38;5;43m"
MAGENTA = "\x1b[35;1m"

def _c(code, t): return f"{code}{t}{RESET}"
def ok(t):    return _c(GREEN,   f"  [OK]   {t}")
def err(t):   return _c(RED,     f"  [FAIL] {t}")
def warn(t):  return _c(YELLOW,  f"  [WARN] {t}")
def info(t):  return _c(CYAN,    f"  [INFO] {t}")
def hdr(t):   return _c(WHITE,   f"\n  {t}")
def dim(t):   return _c(DIM,     f"  {t}")


# ═══════════════════════════════════════════════════════════════════════════════
#  SBLogger — structured + flat logger for all Supabase ops
# ═══════════════════════════════════════════════════════════════════════════════

class SBLogger:
    """
    In-memory logger for Supabase diagnostic events.
    All output goes to the terminal only — no files written.

    Usage anywhere in REKOV:
        from base.supabase.sbcheck import SBLogger
        log = SBLogger(context="kiosk_service")
        log.ok("Ticket inserted", table="tickets", row_id=123)
        log.fail("PDF upload failed", bucket="receipts", error="403")
    """

    def __init__(self, context: str = "sbcheck", run_id: Optional[str] = None):
        self.context = context
        self.run_id  = run_id or str(uuid.uuid4())[:8]
        self._events: list = []

    # ── Event writers ─────────────────────────────────────────────────────────

    def _write(self, level: str, message: str, **meta):
        ts    = datetime.now(timezone.utc).isoformat()
        event = {
            "ts":      ts,
            "run_id":  self.run_id,
            "context": self.context,
            "level":   level,
            "message": message,
            **meta,
        }
        self._events.append(event)
        # Terminal only — no file writes

    def ok(self, message: str, **meta):   self._write("OK",   message, **meta)
    def fail(self, message: str, **meta): self._write("FAIL", message, **meta)
    def warn(self, message: str, **meta): self._write("WARN", message, **meta)
    def note(self, message: str, **meta): self._write("NOTE", message, **meta)

    def events(self) -> list:
        return list(self._events)

    def summary(self) -> dict:
        ok_n   = sum(1 for e in self._events if e["level"] == "OK")
        fail_n = sum(1 for e in self._events if e["level"] == "FAIL")
        warn_n = sum(1 for e in self._events if e["level"] == "WARN")
        return {
            "run_id":  self.run_id,
            "context": self.context,
            "ok":      ok_n,
            "fail":    fail_n,
            "warn":    warn_n,
            "events":  self._events,
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  Config loading
# ═══════════════════════════════════════════════════════════════════════════════

def _load_credentials() -> dict:
    """Load Supabase URL + key from config.json or environment."""
    result = {
        "url":       "",
        "key":       "",
        "source":    "none",
        "config_path": None,
        "hf_token":  "",
    }

    # Try config.json first
    for p in CONFIG_CANDIDATES:
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                sb   = data.get("supabase", {}) if isinstance(data.get("supabase"), dict) else {}
                result["url"]         = sb.get("url") or data.get("SUPABASE_URL", "")
                result["key"]         = sb.get("key") or data.get("SUPABASE_KEY", "")
                result["hf_token"]    = (data.get("hf_token") or data.get("HF_TOKEN", ""))
                result["source"]      = f"config.json ({p})"
                result["config_path"] = str(p)
                break
            except Exception as e:
                result["source"] = f"parse_error:{e}"

    # Fall back to environment
    if not result["url"]:
        result["url"]    = os.environ.get("SUPABASE_URL", "")
        result["source"] = "env"
    if not result["key"]:
        result["key"]    = os.environ.get("SUPABASE_KEY", "")

    return result


def get_client(url: str = "", key: str = ""):
    """
    Return an authenticated supabase-py client.
    Falls back to credentials from config.json if not provided.
    Returns None if supabase-py is not installed.
    """
    creds = _load_credentials()
    url   = url or creds["url"]
    key   = key or creds["key"]
    try:
        from supabase import create_client
        return create_client(url, key)
    except ImportError:
        return None
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Individual check functions
# ═══════════════════════════════════════════════════════════════════════════════

def check_credentials(creds: dict, log: SBLogger) -> dict:
    """Check 1 — are URL and key present and well-formed?"""
    r = {"passed": True, "url": creds["url"], "key_len": len(creds["key"]),
         "source": creds["source"]}

    if not creds["url"]:
        r["passed"] = False
        r["issue"]  = "SUPABASE_URL is empty"
        log.fail("SUPABASE_URL is empty", source=creds["source"])
        print(err("SUPABASE_URL missing — check config.json or SUPABASE_URL env var"))
    elif not creds["url"].startswith("https://"):
        r["passed"] = False
        r["issue"]  = "URL does not start with https://"
        log.fail("SUPABASE_URL invalid", url=creds["url"])
        print(err(f"URL looks wrong: {creds['url'][:60]}"))
    else:
        log.ok("SUPABASE_URL present", url=creds["url"])
        print(ok(f"URL: {creds['url'][:60]}"))

    if not creds["key"]:
        r["passed"] = False
        r["key_issue"] = "empty"
        log.fail("SUPABASE_KEY is empty")
        print(err("SUPABASE_KEY missing — check config.json or SUPABASE_KEY env var"))
    elif len(creds["key"]) < 20:
        r["passed"] = False
        r["key_issue"] = "too_short"
        log.warn("SUPABASE_KEY looks too short", length=len(creds["key"]))
        print(warn(f"Key looks too short ({len(creds['key'])} chars) — may be truncated"))
    else:
        key_preview = creds["key"][:12] + "..." + creds["key"][-6:]
        log.ok("SUPABASE_KEY present", preview=key_preview, length=len(creds["key"]))
        print(ok(f"Key: {key_preview}  ({len(creds['key'])} chars)"))

    print(dim(f"Source: {creds['source']}"))
    return r


def check_reachability(creds: dict, log: SBLogger) -> dict:
    """Check 2 — is the Supabase project reachable at all?"""
    r = {"passed": False, "latency_ms": None}
    url = creds["url"].rstrip("/") + "/rest/v1/"
    headers = {
        "apikey":        creds["key"],
        "Authorization": f"Bearer {creds['key']}",
        "User-Agent":    "REKOV-SBCheck/1.0",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        t0  = time.time()
        with urllib.request.urlopen(req, timeout=12) as resp:
            ms = int((time.time() - t0) * 1000)
            r["passed"]     = True
            r["latency_ms"] = ms
            r["http_status"]= resp.status
            log.ok("REST endpoint reachable", url=url, status=resp.status, ms=ms)
            print(ok(f"REST endpoint reachable  ({resp.status})  {ms}ms"))
    except urllib.error.HTTPError as e:
        ms = 0
        # 406 = valid Supabase response (no table specified) → server IS alive
        if e.code in (406, 200, 204, 201):
            r["passed"]     = True
            r["http_status"]= e.code
            r["latency_ms"] = 0
            log.ok("REST endpoint alive (406 = expected)", url=url)
            print(ok(f"REST endpoint alive  (HTTP {e.code} = normal Supabase response)"))
        elif e.code == 401:
            r["issue"] = "invalid_key"
            log.fail("REST 401 Unauthorized — key is wrong or expired", url=url)
            print(err("401 Unauthorized — key is WRONG or EXPIRED"))
            print(warn("Fix: regenerate anon key in Supabase dashboard → Project Settings → API"))
        elif e.code == 403:
            r["issue"] = "forbidden"
            log.fail("REST 403 Forbidden — key rejected", url=url)
            print(err("403 Forbidden — double-check key type (anon vs service_role)"))
        elif e.code == 404:
            r["issue"] = "not_found"
            log.fail("REST 404 — project URL wrong or project deleted", url=url)
            print(err("404 — project URL is wrong, or the Supabase project was deleted/paused"))
        else:
            r["issue"] = f"http_{e.code}"
            log.fail(f"REST HTTP {e.code}", url=url)
            print(err(f"HTTP {e.code} — unexpected response from Supabase"))
    except Exception as ex:
        r["issue"] = str(ex)
        log.fail("REST endpoint unreachable", url=url, error=str(ex))
        print(err(f"Cannot reach Supabase: {ex}"))
        print(warn("Check internet connection, VPN, or whether the project is paused on Supabase dashboard"))
    return r


def check_table_read(creds: dict, log: SBLogger) -> dict:
    """Check 3 — can we SELECT from core REKOV tables?"""
    r: dict = {"passed": True, "tables": {}}
    base_url = creds["url"].rstrip("/") + "/rest/v1"
    headers  = {
        "apikey":        creds["key"],
        "Authorization": f"Bearer {creds['key']}",
        "Accept":        "application/json",
        "User-Agent":    "REKOV-SBCheck/1.0",
    }
    # Core REKOV tables to probe
    TABLES = ["tickets", "departments", "doctors", "queue_state", "receipts"]
    for table in TABLES:
        url = f"{base_url}/{table}?limit=1&select=*"
        try:
            req = urllib.request.Request(url, headers=headers)
            t0  = time.time()
            with urllib.request.urlopen(req, timeout=10) as resp:
                ms   = int((time.time() - t0) * 1000)
                body = json.loads(resp.read().decode())
                count = len(body) if isinstance(body, list) else -1
                status = "ok"
                if count == 0:
                    status = "empty_or_rls"
                    log.warn(f"Table '{table}' returned 0 rows — RLS may be blocking reads",
                             table=table, ms=ms)
                    print(warn(f"Table '{table}'  → 0 rows (RLS blocking? or table empty?)"))
                else:
                    log.ok(f"Table '{table}' readable", table=table, rows=count, ms=ms)
                    print(ok(f"Table '{table}'  → {count} row(s)  {ms}ms"))
                r["tables"][table] = {"status": status, "rows": count, "ms": ms}
        except urllib.error.HTTPError as e:
            msg = f"HTTP {e.code}"
            if e.code == 404:
                msg += " (table does not exist in Supabase — run migrations?)"
                log.warn(f"Table '{table}' not found (404)", table=table)
                print(warn(f"Table '{table}'  → 404 (not found — run schema migrations)"))
            elif e.code in (401, 403):
                msg += " (credentials rejected)"
                r["passed"] = False
                log.fail(f"Table '{table}' access denied ({e.code})", table=table)
                print(err(f"Table '{table}'  → {e.code} — credentials rejected"))
            else:
                log.warn(f"Table '{table}' HTTP {e.code}", table=table)
                print(warn(f"Table '{table}'  → HTTP {e.code}"))
            r["tables"][table] = {"status": msg}
        except Exception as ex:
            r["tables"][table] = {"status": f"error:{ex}"}
            log.fail(f"Table '{table}' read error", table=table, error=str(ex))
            print(err(f"Table '{table}'  → {ex}"))
    return r


def check_table_write(creds: dict, log: SBLogger) -> dict:
    """Check 4 — INSERT + DELETE a canary row into a safe test path."""
    r = {"passed": False, "action": "write_test"}
    base_url = creds["url"].rstrip("/") + "/rest/v1"
    headers  = {
        "apikey":         creds["key"],
        "Authorization":  f"Bearer {creds['key']}",
        "Content-Type":   "application/json",
        "Prefer":         "return=minimal",
        "User-Agent":     "REKOV-SBCheck/1.0",
    }
    # We use the tickets table with a obviously-fake test row
    canary_id = f"SBCHECK-CANARY-{str(uuid.uuid4())[:8].upper()}"
    payload   = json.dumps({
        "ticket_number": canary_id,
        "status":        "cancelled",
        "patient_name":  "__sbcheck_probe__",
    }).encode()

    # INSERT
    insert_url = f"{base_url}/tickets"
    try:
        req = urllib.request.Request(
            insert_url, data=payload, headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            log.ok("Write probe INSERT succeeded", table="tickets", ticket=canary_id)
            print(ok(f"Write test INSERT succeeded (canary row: {canary_id})"))
            r["insert"] = "ok"
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read().decode()[:200]
        except Exception: pass
        if e.code in (404,):
            log.warn("Write probe skipped — tickets table not found", code=e.code)
            print(warn("Write probe skipped — 'tickets' table not found (run schema migrations)"))
            r["insert"] = "table_missing"
            return r
        elif e.code in (401, 403):
            log.fail("Write probe denied — key may be anon-only (RLS blocks INSERT)",
                     code=e.code, body=body)
            print(err(f"Write probe denied ({e.code}) — RLS may block inserts with anon key"))
            print(warn("Fix: use service_role key for writes, or update RLS policies"))
            r["insert"] = f"denied_{e.code}"
            return r
        else:
            log.warn(f"Write probe HTTP {e.code}", body=body)
            print(warn(f"Write probe HTTP {e.code}: {body[:100]}"))
            r["insert"] = f"http_{e.code}"
            return r
    except Exception as ex:
        log.fail("Write probe exception", error=str(ex))
        print(err(f"Write probe failed: {ex}"))
        r["insert"] = f"error:{ex}"
        return r

    # DELETE canary row
    del_url = f"{base_url}/tickets?ticket_number=eq.{canary_id}"
    try:
        req = urllib.request.Request(del_url, headers=headers, method="DELETE")
        with urllib.request.urlopen(req, timeout=10):
            log.ok("Write probe DELETE succeeded (canary cleaned up)", ticket=canary_id)
            print(ok(f"Write test DELETE succeeded (canary cleaned up)"))
            r["delete"]  = "ok"
            r["passed"]  = True
    except Exception as ex:
        log.warn("Write probe canary DELETE failed — may leave stale row",
                 ticket=canary_id, error=str(ex))
        print(warn(f"Canary DELETE failed: {ex} (stale row left: {canary_id})"))
        r["delete"] = f"error:{ex}"

    return r


def check_storage(creds: dict, log: SBLogger) -> dict:
    """Check 5 — can we list the Supabase Storage bucket for PDF receipts?"""
    r = {"passed": False}
    base_url = creds["url"].rstrip("/")
    headers  = {
        "apikey":        creds["key"],
        "Authorization": f"Bearer {creds['key']}",
        "User-Agent":    "REKOV-SBCheck/1.0",
    }
    # Try common bucket names
    bucket_names = ["receipts", "pdfs", "pdf_receipts", "rekov-receipts"]
    found_bucket = None

    # List all buckets first
    list_url = f"{base_url}/storage/v1/bucket"
    try:
        req = urllib.request.Request(list_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            buckets = json.loads(resp.read().decode())
            names   = [b.get("name", "") for b in buckets] if isinstance(buckets, list) else []
            log.ok("Storage buckets listed", buckets=names)
            print(ok(f"Storage buckets found: {names or '(none)'}"))
            r["buckets"] = names

            # Check which expected bucket exists
            for bn in bucket_names:
                if bn in names:
                    found_bucket = bn
                    break

            if found_bucket:
                print(ok(f"Receipts bucket '{found_bucket}' exists"))
                log.ok("Receipts bucket exists", bucket=found_bucket)
                r["receipts_bucket"] = found_bucket
                r["passed"] = True
            else:
                print(warn(f"No receipts bucket found. Expected one of: {bucket_names}"))
                print(warn("PDFs will fail if no storage bucket exists — create one in Supabase Storage"))
                log.warn("No receipts bucket found", checked=bucket_names, available=names)
                r["issue"] = "no_receipts_bucket"

    except urllib.error.HTTPError as e:
        if e.code == 400 and "storage" in str(e.reason or "").lower():
            log.warn("Storage not enabled on this Supabase project", code=e.code)
            print(warn("Supabase Storage may not be enabled on this project"))
            r["issue"] = "storage_disabled"
        elif e.code in (401, 403):
            log.fail("Storage access denied — key rejected", code=e.code)
            print(err(f"Storage access denied ({e.code}) — key may not have storage permissions"))
            r["issue"] = f"denied_{e.code}"
        else:
            log.warn(f"Storage list HTTP {e.code}")
            print(warn(f"Storage list HTTP {e.code}"))
            r["issue"] = f"http_{e.code}"
    except Exception as ex:
        log.fail("Storage probe failed", error=str(ex))
        print(err(f"Storage probe failed: {ex}"))
        r["issue"] = str(ex)

    return r


def check_pdf_url(pdf_url: str, log: SBLogger) -> dict:
    """Check 6 — is a specific PDF storage URL actually reachable?"""
    r = {"passed": False, "url": pdf_url}
    if not pdf_url:
        print(warn("No PDF URL provided for probe"))
        return r
    try:
        req = urllib.request.Request(
            pdf_url,
            headers={"User-Agent": "REKOV-SBCheck/1.0"},
        )
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=15) as resp:
            ms = int((time.time() - t0) * 1000)
            content_type = resp.headers.get("Content-Type", "")
            content_len  = resp.headers.get("Content-Length", "?")
            r["passed"]       = True
            r["status"]       = resp.status
            r["content_type"] = content_type
            r["size_bytes"]   = content_len
            log.ok("PDF URL reachable", url=pdf_url[:80], status=resp.status,
                   content_type=content_type, size=content_len, ms=ms)
            print(ok(f"PDF reachable  ({resp.status})  {content_type}  {content_len} bytes  {ms}ms"))
    except urllib.error.HTTPError as e:
        r["status"] = e.code
        if e.code == 404:
            log.fail("PDF URL 404 — file not in storage", url=pdf_url[:80])
            print(err(f"PDF URL 404 — file not found in storage bucket"))
            print(warn("PDF was likely never uploaded, or was deleted, or the path in DB is wrong"))
        elif e.code in (401, 403):
            log.fail(f"PDF URL {e.code} — access denied", url=pdf_url[:80])
            print(err(f"PDF URL {e.code} — storage bucket is private (needs signed URL or public bucket)"))
        else:
            log.warn(f"PDF URL HTTP {e.code}", url=pdf_url[:80])
            print(err(f"PDF URL HTTP {e.code}"))
    except Exception as ex:
        log.fail("PDF URL probe exception", url=pdf_url[:80], error=str(ex))
        print(err(f"PDF URL unreachable: {ex}"))

    return r


# ═══════════════════════════════════════════════════════════════════════════════
#  Full check orchestrator
# ═══════════════════════════════════════════════════════════════════════════════

def run_full_check(
    quick: bool = False,
    test_write: bool = True,
    test_storage: bool = True,
    pdf_url: Optional[str] = None,
    verbose: bool = True,
) -> dict:
    """
    Run all Supabase diagnostic checks in sequence.

    Returns a dict with:
      { "passed": bool, "run_id": str, "checks": {...}, "summary": {...} }
    """
    log      = SBLogger(context="full_check")
    creds    = _load_credentials()
    results  = {}

    if verbose:
        try:
            from rekov_credits import print_rekov_credits as _pr
            _pr(compact=True, show_contributors=False)
        except ImportError:
            pass
        print()
        print(f"\x1b[38;5;43;1m  REKOV — Supabase Diagnostic Check\x1b[0m")
        print(f"\x1b[2m  run_id: {log.run_id}  ·  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\x1b[0m")
        print()

    # ── 1. Credentials ────────────────────────────────────────────────────────
    if verbose: print(hdr("1. Credential Check"))
    results["credentials"] = check_credentials(creds, log)

    if not results["credentials"]["passed"]:
        if verbose:
            print()
            print(err("Cannot continue — credentials are missing or malformed."))
            print(warn("Edit config.json and set supabase.url and supabase.key"))
        log.note("Aborting further checks — credentials failed")
        return _finalize(results, log, verbose)

    if quick:
        if verbose: print(hdr("2. Reachability Check (quick mode)"))
        results["reachability"] = check_reachability(creds, log)
        return _finalize(results, log, verbose)

    # ── 2. Reachability ───────────────────────────────────────────────────────
    if verbose: print(hdr("2. Network Reachability"))
    results["reachability"] = check_reachability(creds, log)

    if not results["reachability"].get("passed"):
        if verbose: print(err("Cannot continue — Supabase endpoint is unreachable"))
        return _finalize(results, log, verbose)

    # ── 3. Table reads ────────────────────────────────────────────────────────
    if verbose: print(hdr("3. Table Read Probe"))
    results["table_read"] = check_table_read(creds, log)

    # ── 4. Table writes ───────────────────────────────────────────────────────
    if test_write:
        if verbose: print(hdr("4. Table Write Probe"))
        results["table_write"] = check_table_write(creds, log)

    # ── 5. Storage ────────────────────────────────────────────────────────────
    if test_storage:
        if verbose: print(hdr("5. Storage Bucket Check"))
        results["storage"] = check_storage(creds, log)

    # ── 6. PDF URL ────────────────────────────────────────────────────────────
    if pdf_url:
        if verbose: print(hdr(f"6. PDF URL Probe"))
        results["pdf_url"] = check_pdf_url(pdf_url, log)

    return _finalize(results, log, verbose)


def _finalize(results: dict, log: SBLogger, verbose: bool) -> dict:
    """Print summary and write JSONL record."""
    all_passed = all(v.get("passed", True) for v in results.values() if isinstance(v, dict))
    summary    = log.summary()

    record = {
        "run_id":  log.run_id,
        "ts":      datetime.now(timezone.utc).isoformat(),
        "passed":  all_passed,
        "checks":  results,
        "log_ok":  summary["ok"],
        "log_fail":summary["fail"],
        "log_warn":summary["warn"],
    }

    if verbose:
        print()
        print(f"\x1b[2m  {'─' * 52}\x1b[0m")
        print()
        if all_passed:
            print(f"  \x1b[32;1m  ALL CHECKS PASSED  \x1b[0m"
                  f"  \x1b[2mok={summary['ok']}  warn={summary['warn']}\x1b[0m")
        else:
            print(f"  \x1b[31;1m  ISSUES FOUND  \x1b[0m"
                  f"  \x1b[2mok={summary['ok']}  fail={summary['fail']}  warn={summary['warn']}\x1b[0m")
        print()

    return record


# ═══════════════════════════════════════════════════════════════════════════════
#  Fix wizard
# ═══════════════════════════════════════════════════════════════════════════════

def run_fix_wizard():
    """Interactive guided fix wizard for common Supabase issues."""
    print(f"\x1b[38;5;43;1m\n  REKOV — Supabase Fix Wizard\x1b[0m\n")

    creds = _load_credentials()

    if not creds["config_path"]:
        print(err("config.json not found in any of:"))
        for p in CONFIG_CANDIDATES:
            print(dim(str(p)))
        print()
        create = input("  Create config.json at project root? [y/N]: ").strip().lower()
        if create == "y":
            template = {
                "supabase": {
                    "url": input("  Supabase URL: ").strip(),
                    "key": input("  Supabase Anon Key: ").strip(),
                },
                "hf_token": input("  HuggingFace token (or blank): ").strip(),
            }
            out = ROOT_DIR / "config.json"
            out.write_text(json.dumps(template, indent=2), encoding="utf-8")
            print(ok(f"Saved to {out}"))
            return

    print(info(f"Config found: {creds['config_path']}"))
    print(info(f"URL: {creds['url'][:60]}"))
    print(info(f"Key: {creds['key'][:12]}...{creds['key'][-6:] if len(creds['key']) > 18 else '(short)'}"))
    print()

    action = input("  Options: [1] Update URL  [2] Update Key  [3] Run full check  [q] Quit: ").strip()

    if action == "1":
        new_url = input("  New Supabase URL: ").strip()
        _patch_config(creds["config_path"], "supabase.url", new_url)
    elif action == "2":
        new_key = input("  New Supabase Key: ").strip()
        _patch_config(creds["config_path"], "supabase.key", new_key)
    elif action == "3":
        run_full_check()
    else:
        print("  Cancelled.")


def _patch_config(path: str, dot_key: str, value: str):
    """Update a dot-notation key in config.json."""
    try:
        p    = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        keys = dot_key.split(".")
        obj  = data
        for k in keys[:-1]:
            obj = obj.setdefault(k, {})
        obj[keys[-1]] = value
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(ok(f"Updated {dot_key} in {path}"))
    except Exception as e:
        print(err(f"Could not update config: {e}"))


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="REKOV — Supabase Credential & Connectivity Checker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python base/supabase/sbcheck.py                  # full check
  python base/supabase/sbcheck.py --quick          # creds + reachability only
  python base/supabase/sbcheck.py --json           # machine-readable JSON
  python base/supabase/sbcheck.py --fix            # guided fix wizard
  python base/supabase/sbcheck.py --pdf <URL>      # probe a PDF receipt URL
  python base/supabase/sbcheck.py --no-write       # skip write probe (safer)
        """,
    )
    parser.add_argument("--quick",    action="store_true", help="Credentials + reachability only")
    parser.add_argument("--json",     action="store_true", help="Output JSON result to stdout")
    parser.add_argument("--fix",      action="store_true", help="Run interactive fix wizard")
    parser.add_argument("--pdf",      metavar="URL",       help="Probe a specific PDF storage URL")
    parser.add_argument("--no-write", action="store_true", help="Skip table write probe")
    parser.add_argument("--no-storage", action="store_true", help="Skip storage bucket probe")
    args = parser.parse_args()

    if args.fix:
        run_fix_wizard()
        return

    result = run_full_check(
        quick         = args.quick,
        test_write    = not args.no_write,
        test_storage  = not args.no_storage,
        pdf_url       = args.pdf,
        verbose       = not args.json,
    )

    if args.json:
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
