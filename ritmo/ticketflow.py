"""
ritmo/ticketflow.py
====================
Complete independent ticket booking + receipt + QR pipeline.
Talks directly to Supabase REST API and Storage — no backend needed.

Flow:
  1. book_ticket()        → insert into Supabase `tickets` table (fallback: SQLite)
  2. generate_receipt()   → create HTML receipt + QR code PNG
  3. _upload_to_storage() → upload HTML receipt to Supabase Storage bucket `receipts`
  4. get_ticket()         → fetch a ticket by ticket_id from Supabase
  5. ascii_qr()           → render QR as ASCII art for terminal display
"""

import json
import uuid
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

RECEIPTS_DIR = ROOT_DIR / "data" / "receipts"
RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    for p in [ROOT_DIR / "config.json", ROOT_DIR / "rekov" / "config.json"]:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def _sb_creds() -> tuple:
    """Return (url, key) from config."""
    cfg = _load_config()
    url = cfg.get("SUPABASE_URL") or cfg.get("supabase", {}).get("url")
    key = cfg.get("SUPABASE_KEY") or cfg.get("supabase", {}).get("key")
    return url, key


def _sb_request(method: str, endpoint: str, data: dict = None,
                prefer: str = "return=representation") -> dict:
    """Fire a request to Supabase REST API. Returns {ok, status, data, error}."""
    import urllib.request, urllib.error
    url, key = _sb_creds()
    if not url or not key:
        return {"ok": False, "status": 0, "data": None,
                "error": "No Supabase creds in config.json"}

    full_url = f"{url.rstrip('/')}/rest/v1/{endpoint}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }

    payload = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(full_url, data=payload, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            parsed = json.loads(body) if body.strip() else None
            return {"ok": True, "status": resp.status, "data": parsed, "error": None}
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            pass
        return {"ok": False, "status": e.code, "data": None,
                "error": f"HTTP {e.code}: {err_body[:200]}"}
    except Exception as e:
        return {"ok": False, "status": 0, "data": None, "error": str(e)}


def _upload_to_storage(file_path: Path, bucket: str, dest_path: str) -> str | None:
    """
    Upload a file to Supabase Storage bucket via REST API.
    Returns public URL or None on failure. No supabase-py dependency needed.
    """
    import urllib.request, urllib.error
    sb_url, sb_key = _sb_creds()
    if not sb_url or not sb_key:
        return None

    file_bytes = file_path.read_bytes()
    ext = file_path.suffix.lower()
    content_type = {
        ".html": "text/html",
        ".png": "image/png",
        ".pdf": "application/pdf",
    }.get(ext, "application/octet-stream")

    upload_url = f"{sb_url.rstrip('/')}/storage/v1/object/{bucket}/{dest_path}"
    headers = {
        "apikey": sb_key,
        "Authorization": f"Bearer {sb_key}",
        "Content-Type": content_type,
        "x-upsert": "true",
    }

    req = urllib.request.Request(upload_url, data=file_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status in (200, 201):
                # Build public URL
                pub_url = f"{sb_url.rstrip('/')}/storage/v1/object/public/{bucket}/{dest_path}"
                return pub_url
    except urllib.error.HTTPError as e:
        err = ""
        try:
            err = e.read().decode()
        except Exception:
            pass
        print(f"  [STORAGE] Upload failed HTTP {e.code}: {err[:100]}")
    except Exception as e:
        print(f"  [STORAGE] Upload failed: {e}")
    return None


def _resolve_dept(dept_raw: str) -> tuple:
    """Return (dept_id, dept_name) from a raw string like 'dep_card' or 'cardiology'."""
    mapping = {
        "general":     ("dep_gen",   "General"),
        "gen":         ("dep_gen",   "General"),
        "dep_gen":     ("dep_gen",   "General"),
        "medicine":    ("dep_gen",   "General Medicine"),
        "cardiology":  ("dep_card",  "Cardiology"),
        "card":        ("dep_card",  "Cardiology"),
        "dep_card":    ("dep_card",  "Cardiology"),
        "neurology":   ("dep_neuro", "Neurology"),
        "neuro":       ("dep_neuro", "Neurology"),
        "dep_neuro":   ("dep_neuro", "Neurology"),
        "orthopedics": ("dep_ortho", "Orthopedics"),
        "ortho":       ("dep_ortho", "Orthopedics"),
        "dep_ortho":   ("dep_ortho", "Orthopedics"),
        "pediatrics":  ("dep_ped",   "Pediatrics"),
        "ped":         ("dep_ped",   "Pediatrics"),
        "dep_ped":     ("dep_ped",   "Pediatrics"),
        "emergency":   ("dep_emg",   "Emergency"),
        "emg":         ("dep_emg",   "Emergency"),
        "dep_emg":     ("dep_emg",   "Emergency"),
    }
    key = dept_raw.lower().strip()
    if key in mapping:
        return mapping[key]
    for k, v in mapping.items():
        if k in key or key in k:
            return v
    return ("dep_gen", "General")


# ═══════════════════════════════════════════════════════════════════════════════
#  ASCII QR Code renderer
# ═══════════════════════════════════════════════════════════════════════════════

def ascii_qr(data_url: str, width: int = 35) -> list[str]:
    """
    Render a QR code as ASCII art lines using Unicode block chars.
    Returns a list of strings (one per row). Falls back to empty on error.
    Uses  ██  for dark and spaces for light modules.
    """
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=2,
        )
        qr.add_data(data_url)
        qr.make(fit=True)
        matrix = qr.modules  # list of list of bool

        lines = []
        # Walk in steps of 2 rows using Unicode half-block chars for compact rendering
        # ▀ = top half filled, ▄ = bottom half filled, █ = full, ' ' = empty
        for r in range(0, len(matrix), 2):
            row_top = matrix[r]
            row_bot = matrix[r + 1] if r + 1 < len(matrix) else [False] * len(row_top)
            line = ""
            for t, b in zip(row_top, row_bot):
                if t and b:
                    line += "█"
                elif t and not b:
                    line += "▀"
                elif not t and b:
                    line += "▄"
                else:
                    line += " "
            lines.append(line)
        return lines
    except Exception:
        return []


def print_ascii_qr(data_url: str, label: str = "Scan QR"):
    """Print QR code as ASCII art with a plain border and label."""
    lines = ascii_qr(data_url)
    if not lines:
        return
    w = len(lines[0]) + 4
    print("  +" + "-" * w + "+")
    for ln in lines:
        print("  |  " + ln + "  |")
    print("  +" + "-" * w + "+")
    print(f"  {('  ' + label):^{w + 2}}")


# ═══════════════════════════════════════════════════════════════════════════════
#  1. BOOK TICKET  (Supabase + Local fallback)
# ═══════════════════════════════════════════════════════════════════════════════

def book_ticket(action_data: dict) -> dict:
    """
    Book a ticket — pushes directly to Supabase `tickets` table.
    Falls back to local SQLite if Supabase is unreachable.

    Returns: {ok, ticket_id, token, dept_name, patient, phone, age, fee,
              supabase_synced, message}
    """
    dept_raw = action_data.get("dept_id") or action_data.get("dept", "dep_gen")
    dept_id, dept_name = _resolve_dept(dept_raw)
    pname = action_data.get("patient_name", "Patient")
    phone = action_data.get("phone", "")
    age   = action_data.get("age", "")
    doctor_id = action_data.get("doctor_id", "")
    doctor_name = action_data.get("doctor_name", "")
    fee   = float(action_data.get("fee", 35.00))

    token = f"T{uuid.uuid4().hex[:4].upper()}"
    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()

    ticket_record = {
        "ticket_id":       ticket_id,
        "token_number":    token,
        "department_id":   dept_id,
        "department_name": dept_name,
        "doctor_id":       doctor_id or None,
        "doctor_name":     doctor_name or None,
        "patient_name":    pname,
        "patient_phone":   phone,
        "status":          "WAITING",
        "priority_level":  "EMERGENCY" if dept_id == "dep_emg" else "STANDARD",
        "triage_score":    5 if dept_id == "dep_emg" else 1,
        "total_fee":       fee,
        "created_at":      now,
        "expires_at":      expires,
    }

    result = {
        "ok": False,
        "ticket_id": ticket_id,
        "token": token,
        "dept_name": dept_name,
        "patient": pname,
        "phone": phone,
        "age": age,
        "fee": fee,
        "supabase_synced": False,
        "message": "",
    }

    # Try Supabase first
    sb = _sb_request("POST", "tickets", ticket_record)
    if sb["ok"]:
        result["ok"] = True
        result["supabase_synced"] = True
        result["message"] = f"Ticket {token} booked -> Supabase [CLOUD]"
    else:
        # Fallback to local SQLite
        try:
            from ritmo.booking import book_ticket_local
            local_msg = book_ticket_local(action_data)
            result["ok"] = True
            result["message"] = local_msg + " (Local only — Supabase unreachable)"
        except Exception as e:
            result["message"] = f"Booking failed entirely: {e}"

    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  2. GENERATE RECEIPT (HTML + QR Code + Storage upload)
# ═══════════════════════════════════════════════════════════════════════════════

def _ensure_qrcode():
    """Install qrcode + pillow if missing."""
    try:
        import qrcode
        return True
    except ImportError:
        import subprocess
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "qrcode[pil]", "--quiet"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True


def _generate_qr_png(data_url: str, out_path: Path) -> bool:
    """Generate a QR code PNG that encodes `data_url`."""
    try:
        _ensure_qrcode()
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(data_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(str(out_path))
        return True
    except Exception:
        return False


def generate_receipt(ticket_data: dict) -> dict:
    """
    Generate an HTML receipt + QR code PNG for a booked ticket.
    Uploads HTML + QR to Supabase Storage bucket `receipts`.
    The QR encodes the public storage URL (or REST fallback).

    Returns: {ok, html_path, qr_path, public_url, storage_url, receipt_synced, ascii_qr_lines}
    """
    tid   = ticket_data.get("ticket_id", "UNKNOWN")
    token = ticket_data.get("token", "T0000")
    dept  = ticket_data.get("dept_name", "General")
    pname = ticket_data.get("patient", "Patient")
    phone = ticket_data.get("phone", "")
    age   = ticket_data.get("age", "")
    fee   = ticket_data.get("fee", 35.0)
    now   = datetime.now().strftime("%Y-%m-%d %H:%M")

    sb_url, sb_key = _sb_creds()

    # ── Paths ──────────────────────────────────────────────────────────────────
    receipt_dir = RECEIPTS_DIR / tid
    receipt_dir.mkdir(parents=True, exist_ok=True)
    html_path = receipt_dir / "receipt.html"
    qr_path   = receipt_dir / "qr.png"

    # ── Generate QR PNG first with a temp URL ─────────────────────────────────
    # We'll encode the final storage URL into QR after upload.
    # For now build a Supabase REST URL as placeholder.
    if sb_url and sb_key:
        rest_url = (
            f"{sb_url.rstrip('/')}/rest/v1/tickets"
            f"?ticket_id=eq.{tid}&select=*&apikey={sb_key}"
        )
        storage_html_path = f"user/{tid}_receipt.html"
        # The final public URL after upload
        expected_storage_url = (
            f"{sb_url.rstrip('/')}/storage/v1/object/public/receipts/{storage_html_path}"
        )
        qr_target = expected_storage_url   # QR points at the actual receipt HTML
    else:
        rest_url = f"REKOV-TICKET:{tid}"
        storage_html_path = None
        expected_storage_url = None
        qr_target = rest_url

    # Generate QR PNG
    _ensure_qrcode()
    qr_ok = _generate_qr_png(qr_target, qr_path)

    # Generate ASCII QR for terminal
    ascii_lines = ascii_qr(qr_target) if qr_target else []

    # ── Build HTML receipt ────────────────────────────────────────────────────
    if qr_ok:
        import base64
        qr_b64 = base64.b64encode(qr_path.read_bytes()).decode()
        qr_img_tag = f'<img src="data:image/png;base64,{qr_b64}" width="180" height="180" alt="QR Code">'
    else:
        qr_img_tag = ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>REKOV Receipt — {tid}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background: #0a0a0a; color: #e0e0e0;
    display: flex; justify-content: center; align-items: center;
    min-height: 100vh; padding: 20px;
  }}
  .receipt {{
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    border: 1px solid #00d4aa40; border-radius: 16px;
    max-width: 440px; width: 100%; padding: 32px;
    box-shadow: 0 0 40px rgba(0,212,170,0.1);
  }}
  .header {{ text-align: center; margin-bottom: 24px; }}
  .header h1 {{ color: #00d4aa; font-size: 28px; letter-spacing: 3px; }}
  .header p {{ color: #888; font-size: 12px; margin-top: 4px; }}
  .divider {{
    border: none; height: 1px;
    background: linear-gradient(90deg, transparent, #00d4aa40, transparent);
    margin: 16px 0;
  }}
  .token-box {{
    text-align: center; padding: 16px;
    background: #00d4aa15; border-radius: 12px; margin: 16px 0;
  }}
  .token-box .token {{ font-size: 36px; font-weight: 800; color: #00d4aa; letter-spacing: 4px; }}
  .token-box .label {{ color: #888; font-size: 11px; text-transform: uppercase; }}
  .row {{ display: flex; justify-content: space-between; padding: 8px 0; }}
  .row .key {{ color: #888; font-size: 13px; }}
  .row .val {{ color: #e0e0e0; font-size: 13px; font-weight: 600; }}
  .qr-section {{ text-align: center; margin-top: 20px; }}
  .qr-section img {{ border-radius: 8px; background: #fff; padding: 8px; }}
  .qr-section p {{ color: #666; font-size: 10px; margin-top: 8px; }}
  .qr-section a {{ color: #00d4aa; font-size: 10px; word-break: break-all; }}
  .footer {{
    text-align: center; margin-top: 20px;
    color: #555; font-size: 10px; line-height: 1.6;
  }}
  .status {{
    display: inline-block; padding: 4px 12px; border-radius: 20px;
    font-size: 11px; font-weight: 700; text-transform: uppercase;
    background: #00d4aa20; color: #00d4aa; margin-top: 8px;
  }}
  .fee-box {{
    text-align: center; margin: 12px 0; padding: 12px;
    background: #e6b80015; border: 1px solid #e6b80030; border-radius: 8px;
  }}
  .fee-box .amount {{ font-size: 24px; font-weight: 800; color: #e6b800; }}
  .fee-box .label {{ font-size: 11px; color: #888; }}
  @media print {{
    body {{ background: #fff; }}
    .receipt {{ box-shadow: none; border: 2px solid #333; }}
  }}
</style>
</head>
<body>
<div class="receipt">
  <div class="header">
    <h1>REKOV</h1>
    <p>Hospital Management System — Digital Receipt</p>
  </div>
  <hr class="divider">
  <div class="token-box">
    <div class="label">Your Token Number</div>
    <div class="token">{token}</div>
    <span class="status">WAITING</span>
  </div>
  <hr class="divider">
  <div class="row"><span class="key">Ticket ID</span><span class="val">{tid}</span></div>
  <div class="row"><span class="key">Patient</span><span class="val">{pname}</span></div>
  <div class="row"><span class="key">Phone</span><span class="val">{phone or '—'}</span></div>
  <div class="row"><span class="key">Age</span><span class="val">{age or '—'}</span></div>
  <div class="row"><span class="key">Department</span><span class="val">{dept}</span></div>
  <hr class="divider">
  <div class="fee-box">
    <div class="label">Consultation Fee</div>
    <div class="amount">₹{fee:.2f}</div>
  </div>
  <hr class="divider">
  <div class="row"><span class="key">Date</span><span class="val">{now}</span></div>
  <div class="row"><span class="key">Valid For</span><span class="val">24 Hours</span></div>
  <hr class="divider">
  <div class="qr-section">
    {qr_img_tag}
    <p>Scan QR to open this receipt from any device</p>
    <br>
    <a href="{qr_target}">{qr_target[:60]}...</a>
  </div>
  <hr class="divider">
  <div class="footer">
    REKOV &copy; pheonix14 &mdash; github.com/pheonix14/rekov<br>
    Generated by RITMO AI &bull; This is a digital receipt
  </div>
</div>
</body>
</html>"""

    html_path.write_text(html, encoding="utf-8")

    # ── Upload to Supabase Storage ─────────────────────────────────────────────
    storage_url = None
    receipt_synced = False
    if sb_url and sb_key:
        # Upload QR PNG to storage (image/png is always accepted)
        if qr_ok:
            qr_storage_path = f"qr/{tid}_qr.png"
            qr_store_url = _upload_to_storage(qr_path, "receipts", qr_storage_path)
            if qr_store_url:
                storage_url = qr_store_url
                receipt_synced = True
                # Patch receipt_pdf_url with the QR public URL
                _sb_request(
                    "PATCH",
                    f"tickets?ticket_id=eq.{tid}",
                    {"receipt_pdf_url": qr_store_url},
                    prefer="return=minimal",
                )

    # Fallback: if no storage, just patch with REST URL
    if not receipt_synced and sb_url and sb_key:
        _sb_request(
            "PATCH",
            f"tickets?ticket_id=eq.{tid}",
            {"receipt_pdf_url": rest_url},
            prefer="return=minimal",
        )

    final_url = storage_url or rest_url

    return {
        "ok": True,
        "html_path": str(html_path),
        "qr_path": str(qr_path) if qr_ok else None,
        "public_url": final_url,
        "storage_url": storage_url,
        "receipt_synced": receipt_synced,
        "ascii_qr_lines": ascii_lines,
        "message": f"Receipt saved → {html_path.name}",
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  3. FETCH TICKET (from Supabase)
# ═══════════════════════════════════════════════════════════════════════════════

def get_ticket(ticket_id: str) -> dict:
    """Fetch a single ticket from Supabase by ticket_id."""
    res = _sb_request("GET", f"tickets?ticket_id=eq.{ticket_id}&select=*")
    if res["ok"] and res["data"] and len(res["data"]) > 0:
        return {"ok": True, "ticket": res["data"][0]}
    return {"ok": False, "ticket": None, "error": res.get("error", "Not found")}


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI self-test
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=== TicketFlow Self-Test ===")
    result = book_ticket({
        "dept_id": "dep_gen",
        "patient_name": "Test Patient",
        "phone": "9876543210",
        "age": "25",
    })
    print(json.dumps({k: v for k, v in result.items()}, indent=2))

    if result["ok"]:
        receipt = generate_receipt(result)
        print(json.dumps({k: v for k, v in receipt.items()
                          if k not in ("ascii_qr_lines",)}, indent=2))
        print("\nASCII QR Preview:")
        for line in receipt.get("ascii_qr_lines", []):
            print("  " + line)
