"""
awake/keeper.py
================
REKOV Awake System — keep-alive engine.

Responsibilities:
  1. Ping Supabase REST API every INTERVAL seconds so the project
     never enters "paused" state (free plan auto-pauses after 1 week idle).

  2. Ping the Render backend URL every INTERVAL seconds so the dyno
     never spins down (free plan sleeps after 15 min of inactivity).

Both run in background daemon threads — zero impact on the main process.
The stats.AwakeStats object is updated on every ping for live reporting.

Usage (embedded in backend startup):
    from awake.keeper import AwakeKeeper
    keeper = AwakeKeeper(
        supabase_url="https://xxx.supabase.co",
        supabase_key="eyJ...",
        render_url="https://your-app.onrender.com",
    )
    keeper.start()

Usage (standalone):
    python awake/keeper.py
"""

import os
import sys
import time
import json
import threading
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parent.parent

# ── Shared stats ──────────────────────────────────────────────────────────────
from awake.stats import get_shared_stats
_stats = get_shared_stats()

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_INTERVAL_S  = 300        # 5 minutes
SUPABASE_PING_TABLE = "_awake"   # lightweight table for pings (or use /rest/v1/ check)
CONFIG_PATHS = [
    ROOT_DIR / "config.json",
    ROOT_DIR / "base" / "config.json",
    ROOT_DIR / "rekov" / "config.json",
]


# ═══════════════════════════════════════════════════════════════════════════════
#  Config loader
# ═══════════════════════════════════════════════════════════════════════════════

def _load_config() -> dict:
    for p in CONFIG_PATHS:
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


def _resolve_supabase(cfg: dict) -> tuple[str, str]:
    """Return (url, anon_key) from config or env."""
    sb  = cfg.get("supabase", {}) if isinstance(cfg.get("supabase"), dict) else {}
    url = sb.get("url") or cfg.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL", "")
    key = sb.get("key") or cfg.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY", "")
    return url.rstrip("/"), key


def _resolve_render(cfg: dict) -> str:
    """Return the Render app URL from config or env."""
    return (
        cfg.get("render_url")
        or cfg.get("RENDER_URL")
        or os.environ.get("RENDER_URL", "")
        or os.environ.get("BACKEND_URL", "")
        or "https://rekov.onrender.com"       # fallback default
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Ping functions
# ═══════════════════════════════════════════════════════════════════════════════

def _ping_supabase(url: str, key: str) -> tuple[bool, int, str]:
    """
    Send a lightweight GET to the Supabase REST health endpoint.
    Returns (ok, latency_ms, message).
    """
    if not url or not key:
        return False, 0, "Supabase URL or key not configured"

    # Use the Supabase REST health check — no table needed
    ping_url = f"{url}/rest/v1/"
    try:
        req = urllib.request.Request(
            ping_url,
            headers={
                "apikey":        key,
                "Authorization": f"Bearer {key}",
                "User-Agent":    "REKOV-Awake/1.0",
            },
        )
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=10) as r:
            ms = int((time.time() - t0) * 1000)
            return True, ms, f"HTTP {r.status}  {ms}ms"
    except urllib.error.HTTPError as e:
        # 406 = normal Supabase REST response when no table given — means alive!
        if e.code in (406, 200, 204):
            ms = 0
            return True, ms, f"HTTP {e.code} (alive)"
        return False, 0, f"HTTP {e.code}"
    except Exception as ex:
        return False, 0, str(ex)


def _ping_render(render_url: str) -> tuple[bool, int, str]:
    """
    GET the Render app health endpoint to prevent dyno sleep.
    Returns (ok, latency_ms, message).
    """
    if not render_url:
        return False, 0, "Render URL not configured"

    # Try /health first, then root
    for path in ["/api/v1/health", "/health", "/"]:
        try:
            req = urllib.request.Request(
                f"{render_url.rstrip('/')}{path}",
                headers={"User-Agent": "REKOV-Awake/1.0"},
            )
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=15) as r:
                ms = int((time.time() - t0) * 1000)
                return True, ms, f"HTTP {r.status}  {ms}ms"
        except urllib.error.HTTPError as e:
            if e.code < 500:
                ms = int((time.time() - t0) * 1000)
                return True, ms, f"HTTP {e.code} (alive)"
        except Exception:
            continue
    return False, 0, "All endpoints unreachable"


# ═══════════════════════════════════════════════════════════════════════════════
#  AwakeKeeper
# ═══════════════════════════════════════════════════════════════════════════════

class AwakeKeeper:
    """
    Background keep-alive engine for REKOV.

    Sends periodic pings to:
      - Supabase REST API  (prevents free-tier project pause)
      - Render backend URL (prevents dyno sleep)

    All results are recorded in the shared AwakeStats instance.
    Threads are daemon threads — they stop automatically when the main process exits.
    """

    def __init__(
        self,
        supabase_url: str  = "",
        supabase_key: str  = "",
        render_url: str    = "",
        interval_s: int    = DEFAULT_INTERVAL_S,
        verbose: bool      = False,
        log_fn             = None,
    ):
        cfg = _load_config()

        self.supabase_url = supabase_url or _resolve_supabase(cfg)[0]
        self.supabase_key = supabase_key or _resolve_supabase(cfg)[1]
        self.render_url   = render_url   or _resolve_render(cfg)
        self.interval_s   = interval_s
        self.verbose      = verbose
        self._log         = log_fn or self._default_log
        self._stop_event  = threading.Event()
        self._threads: list[threading.Thread] = []

    def _default_log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        print(f"  [{ts}] [AWAKE] {msg}", flush=True)

    # ── Ping loops ────────────────────────────────────────────────────────────

    def _supabase_loop(self):
        while not self._stop_event.is_set():
            ok, ms, msg = _ping_supabase(self.supabase_url, self.supabase_key)
            if ok:
                _stats.record_supabase_ok(ms)
                if self.verbose:
                    self._log(f"Supabase  OK  {msg}")
            else:
                _stats.record_supabase_err(msg)
                if self.verbose:
                    self._log(f"Supabase  FAIL  {msg}")
            self._stop_event.wait(self.interval_s)

    def _render_loop(self):
        while not self._stop_event.is_set():
            ok, ms, msg = _ping_render(self.render_url)
            if ok:
                _stats.record_render_ok(ms)
                if self.verbose:
                    self._log(f"Render    OK  {msg}")
            else:
                _stats.record_render_err(msg)
                if self.verbose:
                    self._log(f"Render    FAIL  {msg}")
            self._stop_event.wait(self.interval_s)

    # ── Control ───────────────────────────────────────────────────────────────

    def start(self):
        """Start both ping loops in background daemon threads."""
        self._stop_event.clear()
        for name, target in [
            ("awake-supabase", self._supabase_loop),
            ("awake-render",   self._render_loop),
        ]:
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)
        if self.verbose:
            self._log(f"Started — interval={self.interval_s}s  "
                      f"supabase={'OK' if self.supabase_url else 'NO URL'}  "
                      f"render={self.render_url or 'NO URL'}")

    def stop(self):
        """Signal both threads to stop and wait for them."""
        self._stop_event.set()
        for t in self._threads:
            t.join(timeout=5)
        self._threads.clear()

    def is_running(self) -> bool:
        return any(t.is_alive() for t in self._threads)


# ═══════════════════════════════════════════════════════════════════════════════
#  Standalone mode  (python awake/keeper.py)
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("  REKOV Awake System — standalone mode")
    print("  Pinging every 5 minutes. Ctrl+C to stop.")
    print()

    keeper = AwakeKeeper(verbose=True)
    keeper.start()

    try:
        while True:
            time.sleep(60)
            s = _stats.snapshot()
            print(
                f"  Uptime {s['uptime_human']} | "
                f"Supabase {s['supabase']['success']}/{s['supabase']['total']} | "
                f"Render {s['render']['success']}/{s['render']['total']} | "
                f"Total packets {s['total_packets']}"
            )
    except KeyboardInterrupt:
        print("\n  Stopped.")
        keeper.stop()
