"""
ritmo/ritmolog.py
==================
RITMO Session Logger.

Logs all RITMO conversations and actions to:
  - base/logs/ritmo_sessions.jsonl   (structured JSONL — one record per session)
  - base/logs/ritmo_events.log       (human-readable flat log)

Usage (from ritmo/cli.py or any RITMO entry point):
    from ritmo.ritmolog import RitmoLogger

    log = RitmoLogger(mode="offline", model="Qwen2.5-0.5B-Instruct")
    log.message("user", "I have a headache")
    log.message("assistant", "Let me check the department for you.")
    log.action("BOOK_TICKET", {"dept_id": "dep_gen", "patient_name": "John"})
    log.end_session(outcome="booked")
"""

import json
import time
import uuid
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT_DIR  = Path(__file__).resolve().parent.parent
LOGS_DIR  = ROOT_DIR / "base" / "logs"
JSONL_LOG = LOGS_DIR / "ritmo_sessions.jsonl"
FLAT_LOG  = LOGS_DIR / "ritmo_events.log"


def _ensure_logs_dir():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
#  RitmoLogger
# ═══════════════════════════════════════════════════════════════════════════════

class RitmoLogger:
    """
    Per-session logger for RITMO conversations.

    Each session gets a unique ID and records every user message,
    assistant reply, and action (BOOK_TICKET, EMERGENCY, etc.).
    On end_session(), the full record is written to JSONL.
    """

    def __init__(
        self,
        mode: str  = "unknown",    # "hf" or "offline"
        model: str = "",           # model ID e.g. "Qwen2.5-0.5B-Instruct"
        session_id: Optional[str] = None,
    ):
        _ensure_logs_dir()
        self.session_id  = session_id or str(uuid.uuid4())
        self.mode        = mode
        self.model       = model
        self.started_at  = _ts()
        self.messages: list  = []
        self.actions: list   = []
        self._flat_lines: list = []

        self._log_flat(f"SESSION START  id={self.session_id}  mode={mode}  model={model or 'N/A'}")

    # ── Recording ─────────────────────────────────────────────────────────────

    def message(self, role: str, content: str, latency_ms: Optional[int] = None):
        """Record a chat message (role: 'user' or 'assistant')."""
        entry = {
            "ts":         _ts(),
            "role":       role,
            "content":    content,
            "latency_ms": latency_ms,
        }
        self.messages.append(entry)
        label = "USER" if role == "user" else "RITMO"
        ms_str = f"  [{latency_ms}ms]" if latency_ms else ""
        self._log_flat(f"{label}{ms_str}  {content[:120]}")

    def action(self, action_type: str, data: dict):
        """Record a RITMO action (BOOK_TICKET, EMERGENCY, GENERATE_RECEIPT)."""
        entry = {
            "ts":   _ts(),
            "type": action_type,
            "data": data,
        }
        self.actions.append(entry)
        self._log_flat(f"ACTION  {action_type}  {json.dumps(data, ensure_ascii=False)[:100]}")

    def note(self, text: str):
        """Record a free-form note (e.g. 'Model loaded', 'Backend offline')."""
        self._log_flat(f"NOTE  {text}")

    def end_session(self, outcome: str = "ended"):
        """
        Finalise the session and write to JSONL log.
        outcome: 'booked', 'emergency', 'abandoned', 'ended'
        """
        record = {
            "session_id":  self.session_id,
            "mode":        self.mode,
            "model":       self.model,
            "started_at":  self.started_at,
            "ended_at":    _ts(),
            "outcome":     outcome,
            "turn_count":  len([m for m in self.messages if m["role"] == "user"]),
            "messages":    self.messages,
            "actions":     self.actions,
        }
        self._log_flat(f"SESSION END  outcome={outcome}  turns={record['turn_count']}")

        try:
            with open(JSONL_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            self._log_flat(f"JSONL WRITE ERROR  {e}")

        # Push to Supabase 'ritmohis' table
        try:
            import urllib.request
            cfg_path = ROOT_DIR / "config.json"
            if cfg_path.exists():
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                sb_url = cfg.get("SUPABASE_URL") or cfg.get("supabase", {}).get("url")
                sb_key = cfg.get("SUPABASE_KEY") or cfg.get("supabase", {}).get("key")
                if sb_url and sb_key:
                    req = urllib.request.Request(
                        f"{sb_url.rstrip('/')}/rest/v1/ritmohis",
                        data=json.dumps(record).encode("utf-8"),
                        headers={
                            "apikey": sb_key,
                            "Authorization": f"Bearer {sb_key}",
                            "Content-Type": "application/json",
                            "Prefer": "return=minimal"
                        },
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=5) as res:
                        self._log_flat(f"SUPABASE SYNC OK  code={res.status}")
        except Exception as e:
            self._log_flat(f"SUPABASE SYNC ERROR  {e}")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _log_flat(self, msg: str):
        ts    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        line  = f"[{ts}] [{self.session_id[:8]}]  {msg}"
        self._flat_lines.append(line)
        try:
            with open(FLAT_LOG, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
#  Convenience: read recent sessions
# ═══════════════════════════════════════════════════════════════════════════════

def get_recent_sessions(n: int = 20) -> list:
    """Return the last n session records from the JSONL log."""
    if not JSONL_LOG.exists():
        return []
    try:
        lines = JSONL_LOG.read_text(encoding="utf-8").strip().splitlines()
        records = [json.loads(l) for l in lines if l.strip()]
        return records[-n:]
    except Exception:
        return []


def get_session_stats() -> dict:
    """Return aggregate stats across all logged sessions."""
    sessions = get_recent_sessions(n=10_000)
    if not sessions:
        return {"total": 0, "outcomes": {}, "avg_turns": 0}
    outcomes: dict = {}
    total_turns = 0
    for s in sessions:
        outcome = s.get("outcome", "unknown")
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        total_turns += s.get("turn_count", 0)
    return {
        "total":     len(sessions),
        "outcomes":  outcomes,
        "avg_turns": round(total_turns / len(sessions), 1),
        "log_path":  str(JSONL_LOG),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI (python ritmo/ritmolog.py)
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys as _sys
    stats = get_session_stats()
    if stats["total"] == 0:
        print("  No RITMO sessions logged yet.")
        print(f"  Log file: {JSONL_LOG}")
    else:
        print(f"  RITMO Sessions: {stats['total']}")
        print(f"  Avg turns/session: {stats['avg_turns']}")
        print(f"  Outcomes: {json.dumps(stats['outcomes'], indent=4)}")
        print(f"  Log: {stats['log_path']}")
