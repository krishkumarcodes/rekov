"""
ritmo/pull.py
==============
RITMO — Independent Real-Time HuggingFace API Puller (Online Mode).
Connects directly to HuggingFace Inference API. Does NOT require the REKOV backend.
"""

import os
import sys
import json
import time
import uuid
import urllib.request
import urllib.error
from pathlib import Path
from typing import Iterator

RITMO_DIR = Path(__file__).resolve().parent
ROOT_DIR  = RITMO_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

# ── HF Inference API constants ────────────────────────────────────────────────
HF_INFERENCE_BASE = "https://api-inference.huggingface.co/models"
DEFAULT_MODEL     = "Qwen/Qwen2.5-72B-Instruct"
FALLBACK_MODELS   = [
    "Qwen/Qwen2.5-7B-Instruct",
    "Qwen/Qwen2.5-3B-Instruct",
    "Qwen/Qwen2.5-1.5B-Instruct",
]

def get_system_prompt() -> str:
    try:
        from ritmo.pulldata.ritmoscan import get_hospital_context
        ctx = get_hospital_context()
    except Exception as e:
        ctx = "Available departments: General, Cardiology, Neurology, Orthopedics, Pediatrics, Emergency."
    
    return f"""You are RITMO, the friendly and proactive hospital voice assistant for REKOV Medical System.
Your job is to act as a helpful receptionist in a voice conversation.
1. Greet the patient warmly and ask for their symptoms to route them to the correct department.
2. If they need an appointment, PROACTIVELY ask for their details one by one:
   - Full Name
   - Phone Number
   - Age
   DO NOT ask for everything at once. Have a natural conversation.
3. Once you have all details, output EXACTLY this on a new line: [BOOK_TICKET] dept_id=<id> patient_name=<name> phone=<phone> age=<age>
4. After booking, ask if they want a receipt. If they say yes, output EXACTLY: [GENERATE_RECEIPT]
5. Handle emergencies with PRIORITY MAX triage. Output: [EMERGENCY]

{ctx}

Be extremely concise (1-2 short sentences max) because you are speaking out loud. Be warm, polite, and clinical."""

def _load_config() -> dict:
    for p in [ROOT_DIR / "config.json", ROOT_DIR / "rekov" / "config.json"]:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}

def _get_token(cfg: dict = None) -> str:
    cfg = cfg or _load_config()
    return (
        cfg.get("hf_token") or cfg.get("HF_TOKEN")
        or os.environ.get("HF_TOKEN") or os.environ.get("HF_API_TOKEN")
        or ""
    )

def _save_history(session_id: str, role: str, content: str):
    """Save conversation history to local SQLite database (ritmohis)."""
    if not content: return
    try:
        from base.database import SessionLocal, init_db
        from base.models import RitmoHisModel
        init_db()  # Ensures the new ritmohis table exists
        db = SessionLocal()
        try:
            his = RitmoHisModel(session_id=session_id, role=role, content=content)
            db.add(his)
            db.commit()
        except Exception:
            pass
        finally:
            db.close()
    except Exception:
        pass  # Fail silently if db isn't available

def _hf_request(
    model: str,
    token: str,
    messages: list,
    stream: bool = False,
    max_tokens: int = 512,
    temperature: float = 0.7,
) -> dict:
    url     = f"{HF_INFERENCE_BASE}/{model}/v1/chat/completions"
    payload = json.dumps({
        "model":       model,
        "messages":    messages,
        "max_tokens":  max_tokens,
        "temperature": temperature,
        "stream":      stream,
    }).encode()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "User-Agent":    "REKOV-RitmoPull/1.0",
    }
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    resp = urllib.request.urlopen(req, timeout=60)
    return json.loads(resp.read().decode("utf-8"))

def pull_chat(
    conversation: list,
    token: str = "",
    model: str = DEFAULT_MODEL,
    system_prompt: str = None,
    max_tokens: int = 512,
) -> dict:
    if system_prompt is None:
        system_prompt = get_system_prompt()
        
    token = token or _get_token()
    result = {"reply": "", "model": model, "ok": False, "elapsed_ms": 0, "error": None}
    if not token:
        result["error"] = "HF_TOKEN missing"
        return result

    messages = [{"role": "system", "content": system_prompt}] + conversation
    models_to_try = [model] + [m for m in FALLBACK_MODELS if m != model]

    for m in models_to_try:
        try:
            t0   = time.time()
            data = _hf_request(m, token, messages, stream=False, max_tokens=max_tokens)
            ms   = int((time.time() - t0) * 1000)
            
            # Robust parsing for multiple HF API response formats
            reply = ""
            if isinstance(data, dict):
                if "choices" in data:
                    reply = data["choices"][0].get("message", {}).get("content", "").strip()
                elif "generated_text" in data:
                    reply = data["generated_text"].strip()
                elif "error" in data:
                    result["error"] = data["error"]
                    continue
            elif isinstance(data, list) and len(data) > 0:
                if "generated_text" in data[0]:
                    reply = data[0]["generated_text"].strip()
                    
            if reply:
                result.update({"reply": reply, "model": m, "ok": True, "elapsed_ms": ms})
                return result
        except urllib.error.HTTPError as e:
            if e.code in (429, 503, 502):
                result["error"] = f"HTTP {e.code}"
                continue
            elif e.code == 401:
                result["error"] = "HF token rejected (401)"
                return result
            else:
                try:
                    # Try reading error payload for exact cause
                    err_payload = json.loads(e.read().decode())
                    result["error"] = err_payload.get("error", f"HTTP {e.code}")
                except Exception:
                    result["error"] = f"HTTP {e.code}"
                continue
        except urllib.error.URLError as e:
            result["error"] = f"Network error: {e.reason}"
            continue
        except Exception as ex:
            result["error"] = str(ex)
            continue
            
    if not result["error"]:
        result["error"] = "All HF models failed or timed out."
    return result

class RitmoPull:
    """Stateful real-time puller for RITMO online mode (HF API)."""
    def __init__(self, token: str = "", model: str = DEFAULT_MODEL):
        self.token = token or _get_token()
        self.model = model
        self.session_id = str(uuid.uuid4())
        self.conversation = []

    def send(self, message: str) -> tuple:
        _save_history(self.session_id, "user", message)
        self.conversation.append({"role": "user", "content": message})
        
        result = pull_chat(self.conversation, token=self.token, model=self.model)
        
        reply  = result.get("reply", "")
        if not reply:
            err = result.get('error', 'Unknown error')
            if 'getaddrinfo' in str(err) or 'Network error' in str(err):
                reply = (
                    "I can't reach HuggingFace right now — your internet appears to be "
                    "offline or DNS is failing.\n\n"
                    "Tip: Type /quit and restart with Offline Mode (option 2) to use "
                    "the local ONNX model instead — no internet needed!"
                )
            else:
                reply = f"Sorry, HuggingFace API error: {err}"
        ms = result.get("elapsed_ms", 0)
        
        _save_history(self.session_id, "assistant", reply)
        self.conversation.append({"role": "assistant", "content": reply})
        
        # Extract actions like [BOOK_TICKET] or [EMERGENCY]
        try:
            from ritmo.ritmocli import _parse_action
            action, action_data = _parse_action(reply)
        except Exception:
            action, action_data = None, None
        
        return reply, ms, "hf_api", action, action_data

    def reset(self):
        self.conversation = []
        self.session_id = str(uuid.uuid4())

def check_pull_status(verbose: bool = True) -> dict:
    token = _get_token()
    status = {"token_ok": bool(token), "errors": []}
    if not token:
        status["errors"].append("HF_TOKEN missing")
    if verbose:
        C = {True: "\x1b[32;1m OK \x1b[0m", False: "\x1b[31;1mFAIL\x1b[0m"}
        print(f"  HF Token    {C[status['token_ok']]}")
    return status

if __name__ == "__main__":
    rp = RitmoPull()
    reply, ms, source, action, action_data = rp.send("Hello")
    print(reply)
