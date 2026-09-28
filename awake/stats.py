"""
awake/stats.py
==============
Thread-safe live stats for the REKOV Awake System.

Tracks:
  - Supabase pings sent  (and last status)
  - Render pings sent    (and last status)
  - Total packets        (all pings combined)
  - System uptime
  - Last ping timestamps
"""

import threading
import time
from datetime import datetime, timezone
from typing import Optional


class AwakeStats:
    """Thread-safe stats container for the Awake keep-alive system."""

    def __init__(self):
        self._lock            = threading.Lock()
        self._started_at      = time.monotonic()
        self._started_wall    = datetime.now(timezone.utc)

        # Supabase counters
        self.supabase_pings   = 0
        self.supabase_success = 0
        self.supabase_fail    = 0
        self.supabase_last_ok: Optional[str]     = None
        self.supabase_last_err: Optional[str]    = None
        self.supabase_last_ms: Optional[int]     = None

        # Render / backend counters
        self.render_pings     = 0
        self.render_success   = 0
        self.render_fail      = 0
        self.render_last_ok: Optional[str]       = None
        self.render_last_err: Optional[str]      = None
        self.render_last_ms: Optional[int]       = None

    # ── Supabase ──────────────────────────────────────────────────────────────

    def record_supabase_ok(self, latency_ms: int):
        with self._lock:
            self.supabase_pings   += 1
            self.supabase_success += 1
            self.supabase_last_ok  = datetime.now(timezone.utc).isoformat()
            self.supabase_last_ms  = latency_ms

    def record_supabase_err(self, error: str):
        with self._lock:
            self.supabase_pings  += 1
            self.supabase_fail   += 1
            self.supabase_last_err = f"{datetime.now(timezone.utc).isoformat()} — {error}"

    # ── Render ────────────────────────────────────────────────────────────────

    def record_render_ok(self, latency_ms: int):
        with self._lock:
            self.render_pings   += 1
            self.render_success += 1
            self.render_last_ok  = datetime.now(timezone.utc).isoformat()
            self.render_last_ms  = latency_ms

    def record_render_err(self, error: str):
        with self._lock:
            self.render_pings  += 1
            self.render_fail   += 1
            self.render_last_err = f"{datetime.now(timezone.utc).isoformat()} — {error}"

    # ── Snapshot ──────────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Return a JSON-serialisable dict with all current stats."""
        uptime_s = int(time.monotonic() - self._started_at)
        hours, rem = divmod(uptime_s, 3600)
        minutes, seconds = divmod(rem, 60)

        with self._lock:
            return {
                "uptime_seconds": uptime_s,
                "uptime_human":   f"{hours:02d}h {minutes:02d}m {seconds:02d}s",
                "started_at":     self._started_wall.isoformat(),
                "total_packets":  self.supabase_pings + self.render_pings,
                "supabase": {
                    "total":    self.supabase_pings,
                    "success":  self.supabase_success,
                    "fail":     self.supabase_fail,
                    "last_ok":  self.supabase_last_ok,
                    "last_err": self.supabase_last_err,
                    "last_ms":  self.supabase_last_ms,
                },
                "render": {
                    "total":    self.render_pings,
                    "success":  self.render_success,
                    "fail":     self.render_fail,
                    "last_ok":  self.render_last_ok,
                    "last_err": self.render_last_err,
                    "last_ms":  self.render_last_ms,
                },
            }


# ── Module-level shared instance (used by AwakeKeeper + API router) ───────────
_shared_stats = AwakeStats()


def get_stats() -> dict:
    """Return the current snapshot of the shared global stats object."""
    return _shared_stats.snapshot()


def get_shared_stats() -> AwakeStats:
    """Return the shared AwakeStats instance (used by AwakeKeeper)."""
    return _shared_stats
