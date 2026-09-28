"""
huggfaceonnx/hfmanager.py
==========================
HuggingFace API management for REKOV.

Provides:
  HFManager            — stateful wrapper for backend API calls
  check_hf_api(token)  — ping HF whoami endpoint
  check_hf_models()    — check Qwen model availability on HF inference

Used by: ritmo/cli.py, ritmo/support.py
"""

import json
import sys
import time
import urllib.request
import urllib.error
import uuid
from typing import Optional

# ── Backend default ───────────────────────────────────────────────────────────
_BACKEND_BASE = "http://localhost:4040/api/v1"


# ═══════════════════════════════════════════════════════════════════════════════
#  HFManager — stateful backend API client
# ═══════════════════════════════════════════════════════════════════════════════

class HFManager:
    """
    Manages communication with the running REKOV FastAPI backend.

    Usage:
        mgr = HFManager(token=cfg["hf_token"])
        ok  = mgr.check_backend()
        res = mgr.chat(session_id, "I have a headache")
    """

    def __init__(
        self,
        token: str = "",
        backend_base: str = _BACKEND_BASE,
    ):
        self.token        = token
        self.backend_base = backend_base.rstrip("/")

    # ── Health ────────────────────────────────────────────────────────────────

    def check_backend(self) -> bool:
        """Return True if the REKOV backend is reachable at :4040."""
        for path in ["/health", "/"]:
            try:
                req = urllib.request.Request(
                    f"{self.backend_base}{path}",
                    headers={"User-Agent": "HFManager/1.0"},
                )
                with urllib.request.urlopen(req, timeout=2) as r:
                    if r.status in (200, 304):
                        return True
            except Exception:
                pass
        return False

    # ── Chat ──────────────────────────────────────────────────────────────────

    def chat(self, session_id: str, message: str) -> dict:
        """
        POST to /api/v1/ai_voice/chat.
        Returns {"reply": str, "action": str|None, "action_data": dict|None}.
        """
        url     = f"{self.backend_base}/ai_voice/chat"
        payload = json.dumps({"session_id": session_id, "message": message}).encode()
        req     = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "HFManager/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            return {"reply": f"[API Error {e.code}] {body[:200]}", "action": None}
        except Exception as ex:
            return {"reply": f"[Connection Error] {ex}", "action": None}

    # ── Ticket booking ────────────────────────────────────────────────────────

    def book_ticket(self, action_data: dict) -> str:
        """
        POST to /api/v1/kiosk/ticket.
        Returns a human-readable booking confirmation string.
        """
        patient_name = action_data.get("patient_name", "CLI Patient")
        payload_dict = {
            "department_id":     action_data.get("dept_id", "dep_gen"),
            "doctor_id":         action_data.get("doctor_id"),
            "combo_package_ids": [],
            "patient": {
                "full_name":        patient_name,
                "phone":            action_data.get("phone", "0000000000"),
                "national_id":      action_data.get(
                    "national_id", f"CLI{uuid.uuid4().hex[:6].upper()}"
                ),
                "age":              int(action_data.get("age", 30)),
                "gender":           action_data.get("gender", "Unknown"),
                "insurance_member": False,
            },
            "payment_method": "CASH",
        }
        url     = f"{self.backend_base}/kiosk/ticket"
        payload = json.dumps(payload_dict).encode()
        req     = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data   = json.loads(r.read().decode())
                token  = data.get("token_number", "?")
                doctor = data.get("doctor_name", "?")
                dept   = data.get("department_name", "?")
                return f"Ticket booked!  Token: {token}  |  Doctor: {doctor}  |  Dept: {dept}"
        except Exception as ex:
            return f"[Booking Error] {ex}"


# ═══════════════════════════════════════════════════════════════════════════════
#  Standalone HuggingFace API helpers (used by support.py)
# ═══════════════════════════════════════════════════════════════════════════════

def check_hf_api(hf_token: str = "") -> dict:
    """
    Ping https://huggingface.co/api/whoami to verify token validity.

    Returns:
        {
            "name": "HuggingFace API",
            "ok":   bool,
            "latency_ms": int|None,
            "username": str,
            "message": str,
        }
    """
    result: dict = {
        "name":       "HuggingFace API",
        "ok":         False,
        "message":    "",
        "latency_ms": None,
        "username":   "",
    }
    if not hf_token:
        result["message"] = "No token — skipping API ping"
        return result

    try:
        req = urllib.request.Request(
            "https://huggingface.co/api/whoami",
            headers={
                "Authorization": f"Bearer {hf_token}",
                "User-Agent":    "HFManager/1.0",
            },
        )
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=8) as r:
            ms              = int((time.time() - t0) * 1000)
            body            = json.loads(r.read().decode())
            username        = body.get("name", "unknown")
            result["ok"]         = True
            result["latency_ms"] = ms
            result["username"]   = username
            result["message"]    = f"Valid token  user={username}  latency={ms}ms"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            result["message"] = "Token rejected (401 Unauthorized) — token may be expired"
        else:
            result["message"] = f"HTTP {e.code} from HuggingFace"
    except Exception as ex:
        result["message"] = f"Cannot reach HuggingFace: {ex}"
    return result


def check_hf_models(hf_token: str = "") -> dict:
    """
    Check if Qwen inference models are available on the HF inference router.

    Returns:
        {
            "name":    "HF Inference Models",
            "ok":      bool,
            "models":  {model_id: status_str, ...},
            "message": str,
        }
    """
    result: dict = {
        "name":    "HF Inference Models",
        "ok":      False,
        "models":  {},
        "message": "",
    }
    if not hf_token:
        result["message"] = "No HF token — cannot check models"
        return result

    models_to_check = [
        "Qwen/Qwen2.5-72B-Instruct",
        "Qwen/Qwen2.5-7B-Instruct",
    ]
    any_ok = False
    for model_id in models_to_check:
        url = f"https://api-inference.huggingface.co/models/{model_id}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {hf_token}",
                "User-Agent":    "HFManager/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=6) as r:
                data   = json.loads(r.read().decode())
                loaded = not data.get("estimated_time")
                result["models"][model_id] = "READY" if loaded else "LOADING"
                any_ok = True
        except urllib.error.HTTPError as e:
            if e.code == 503:
                result["models"][model_id] = "LOADING (cold start)"
                any_ok = True
            elif e.code == 403:
                result["models"][model_id] = "NO ACCESS (gated model)"
            else:
                result["models"][model_id] = f"HTTP {e.code}"
        except Exception as ex:
            result["models"][model_id] = f"ERROR: {ex}"

    result["ok"]      = any_ok
    result["message"] = "At least one model accessible" if any_ok else "No models accessible"
    return result
