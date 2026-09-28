"""
REKOV — Unified System Launcher

Terminal Color Legend:
  DARK GREEN  = Service working / healthy / compiled
  RED         = Service dead / crashed / failed
  YELLOW      = Unknown / port stale / retry
  BLUE        = Update / compiling / progress
"""

import subprocess
import os
import sys
import shutil
import threading
import time
import socket
import urllib.request
import json
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # ensure rekov/ is on path
from logger import sys_logger, UPDATE_LEVEL


# ── Log Classification ────────────────────────────────────────────────────────
# Lines that mean SUCCESS (dark green) from subprocess output
_SUCCESS_PATTERNS = {
    "compiled successfully",
    "ready in",
    "ready started",
    "application startup complete",
    "uvicorn running",
    "started server",
    "[success]",
    "loaded env",
    "200 ok",
    "starting...",
    "[ok]",
    "compiled /",
}

# Lines that mean an UPDATE/progress (blue)
_UPDATE_PATTERNS = {
    "compiling",
    "hmr",
    "hot update",
    "webpack",
    "rebuilding",
    "reloading",
    "reloaded",
    "module reload",
    "- compiled",
    "updated",
    "installing",
    "fetching",
    "resolving",
    "downloading",
    "bundling",
    "built",
    "building",
}

# Lines that definitely mean ERROR (red)
_ERROR_PATTERNS = {
    "error:",
    "error\n",
    "syntaxerror",
    "traceback",
    "exception:",
    "failed to compile",
    "module not found",
    "cannot find module",
    "typeerror",
    "referenceerror",
    "exit code",
    "eaddrinuse",
    "econnrefused",
    "fatal:",
    "critical:",
    "[failed]",
    "unhandledrejection",
    "uncaughtexception",
}

# Next.js noise lines to completely suppress (they are not real issues)
_SUPPRESS_PATTERNS = {
    "node_modules/next/dist/server/",
    "node_modules/next/dist/build/",
    "node_modules/next/dist/compiled/",
    "at module.<anonymous>",
    "at wrapmoduleload",
    "at module._compile",
    "at object.<anonymous>",
    "at module.load",
    "at module._load",
    "at wraptransition",
    "at object..js",
    "requirestack",
    "require stack",
    "warn - next.js",
    "(node:internal/modules",
    "at c:\\users\\",
    "at c:\\program",
    "at async",
    "},",
    "webpack-runtime.js",
    "react-dom/cjs",
    "react-server-dom-webpack",
    "'c:\\users\\",
    "- c:\\users\\",
    "\\node_modules\\next\\",
    "\\node_modules\\next\\dist\\",
}

# Lines that should just be INFO (cyan, neutral)
_INFO_PATTERNS = {
    "get /",
    "post /",
    "put /",
    "delete /",
    " 200 in",
    " 304 in",
    " 307 in",
    " 404 in",
    " 500 in",
    "info:",
    "started",
    "startup",
    "running on",
    "waiting for",
    "ready",
    "listening",
    "connected",
    "startup sequence",
    "database initialized",
    "sync service",
    "backupverifier",
    "purge daemon",
    "application startup",
    "127.0.0.1",
    "0.0.0.0",
    "next.js",
    "environments:",
    ".env.local",
    "local:",
    "network:",
    "rekoviu@",
    "next dev",
}


def _shorten_path_line(line: str) -> str:
    """If a line is a raw file path (stack entry or require chain), shorten it to just the filename."""
    import re
    # Lines like: "  - C:\Users\...\some\file.js"  or  "  'C:\...'"
    path_match = re.search(r"[A-Za-z]:\\[^'\"\n]+\.(?:js|ts|tsx|py)", line)
    if path_match:
        full = path_match.group(0)
        import os as _os
        return line[:path_match.start()] + _os.path.basename(full)
    return line


def _classify_and_log(line: str, name: str):
    """
    Route subprocess output lines to correct color level:
      DARK GREEN  = compiled OK / service healthy
      BLUE        = compiling / updating / progress
      YELLOW      = warnings / unknowns
      RED         = real errors / crashes
      (suppressed) = Next.js internal stack frames
    """
    lower = line.lower()

    # Hard suppress Next.js internal stack noise
    if any(p in lower for p in _SUPPRESS_PATTERNS):
        return

    # Empty or cosmetic separators
    stripped = line.strip("-=* \t")
    if not stripped:
        return

    # Shorten raw file path lines to just the filename
    line = _shorten_path_line(line)

    # Classify
    if any(p in lower for p in _ERROR_PATTERNS):
        sys_logger.error(f"  [ERR]  [{name}]  {line}")
    elif any(p in lower for p in _SUCCESS_PATTERNS):
        sys_logger.success(f"  [OK]   [{name}]  {line}")
    elif any(p in lower for p in _UPDATE_PATTERNS):
        sys_logger.update(f"  [UPD]  [{name}]  {line}")
    elif any(p in lower for p in _INFO_PATTERNS):
        sys_logger.info(f"  [INF]  [{name}]  {line}")
    else:
        # Everything else that doesn't match known patterns -> yellow
        sys_logger.warning(f"  [WRN]  [{name}]  {line}")


def read_stream(stream, name: str, is_stderr: bool = False):
    """Read output from a subprocess stream and route to colored log levels."""
    for raw_line in iter(stream.readline, b""):
        line = raw_line.decode("utf-8", errors="replace").rstrip()
        if not line.strip():
            continue
        # Strip emojis requested by user
        line = line.replace("✓", "[OK]").replace("▲", "*").replace("🚨", "[!]").replace("✨", "*").replace("▸", "->").replace("⚠", "[!]").replace("☁", "[CLOUD]").replace("✗", "[X]").replace("★", "*").replace("│", "|").replace("┌", "+").replace("└", "+").replace("─", "-").replace("┐", "+").replace("┘", "+")
        _classify_and_log(line, name)
    stream.close()


# ── Network Helpers ───────────────────────────────────────────────────────────
def _is_port_in_use(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False


def _is_service_healthy(url: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RekovLauncher"})
        with urllib.request.urlopen(req, timeout=1.5) as res:
            return res.status in (200, 304, 307, 308)
    except Exception:
        return False


def _kill_port(port: int):
    """Kill any process holding a port (Windows)."""
    try:
        netstat_bin = shutil.which("netstat") or (
            r"C:\Windows\System32\netstat.exe" if os.path.exists(r"C:\Windows\System32\netstat.exe") else "netstat"
        )
        taskkill_bin = shutil.which("taskkill") or (
            r"C:\Windows\System32\taskkill.exe" if os.path.exists(r"C:\Windows\System32\taskkill.exe") else "taskkill"
        )
        result = subprocess.run(
            [netstat_bin, "-ano"], capture_output=True, text=True, timeout=5
        )
        killed_pids = set()
        for line in result.stdout.splitlines():
            if f":{port}" in line:
                parts = line.strip().split()
                if parts:
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) > 0 and pid not in killed_pids:
                        killed_pids.add(pid)
                        subprocess.run(
                            [taskkill_bin, "/F", "/T", "/PID", pid],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        )
                        sys_logger.warning(f"  [WRN]  [CLEANUP]  Killed stale PID {pid} on :{port}")
    except Exception:
        pass


# ── Process Launcher ──────────────────────────────────────────────────────────
def run_process(cmd, cwd: str, name: str, shell: bool = False):
    cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
    sys_logger.update(f"  [UPD]  [{name}]  Spawning: {cmd_str}")
    try:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"]      = "1"
        env["NEXT_TELEMETRY_DISABLED"] = "1"   # Silence Next.js upgrade notices
        env["NO_COLOR"]              = "0"     # Keep colors
        process = subprocess.Popen(
            cmd, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, shell=shell, stdin=subprocess.DEVNULL,
        )
        threading.Thread(target=read_stream, args=(process.stdout, name, False), daemon=True).start()
        threading.Thread(target=read_stream, args=(process.stderr, name, True),  daemon=True).start()
        return process
    except Exception as e:
        sys_logger.error(f"  [ERR]  [{name}]  Failed to start: {e}")
        return None


# ── Banner Helper ─────────────────────────────────────────────────────────────
def _banner(text: str):
    sys_logger.success(f"  {'=' * 54}")
    sys_logger.success(f"  {text}")
    sys_logger.success(f"  {'=' * 54}")


def _service_status(name: str, alive: bool):
    if alive:
        sys_logger.success(f"  [OK]   {name:<30}  ONLINE")
    else:
        sys_logger.error(f"  [ERR]  {name:<30}  OFFLINE / STARTING")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    _banner("REKOV  *  Unified System Launcher")
    sys_logger.info("")

    # ── 0. Health-check existing services ────────────────────────────────────
    api_alive = _is_service_healthy("http://127.0.0.1:4040/api/v1/health") or \
                _is_service_healthy("http://127.0.0.1:4040/")
    ui_alive  = _is_service_healthy("http://127.0.0.1:3000/")

    if api_alive and ui_alive:
        sys_logger.success("  [OK]   All services already online — reusing existing instances.")
        sys_logger.info("")
        _service_status("API  (FastAPI)     :4040", api_alive)
        _service_status("UI   (Next.js)     :3000", ui_alive)
        sys_logger.info("")
        sys_logger.info("  ->  http://localhost:3000         (App)")
        sys_logger.info("  ->  http://localhost:3000/kiosk   (Kiosk)")
        sys_logger.info("  ->  http://localhost:4040/docs    (API Docs)")
        sys_logger.info("")
        sys_logger.info("  Press Ctrl+C to exit launcher (services stay running).")
        try:
            while True:
                time.sleep(2)
        except KeyboardInterrupt:
            sys_logger.warning("  [WRN]  Launcher stopped. Services remain active.")
        return

    # ── Kill stale zombie processes on our ports ──────────────────────────────
    if not ui_alive and _is_port_in_use(3000):
        sys_logger.warning("  [WRN]  [CLEANUP]  Port 3000 occupied — killing stale process...")
        _kill_port(3000)
        # Wait until confirmed free (max 6s in 0.5s steps)
        for _ in range(12):
            if not _is_port_in_use(3000):
                break
            time.sleep(0.5)
        else:
            sys_logger.warning("  [WRN]  [CLEANUP]  Port 3000 still occupied — proceeding anyway")
    if not api_alive and _is_port_in_use(4040):
        sys_logger.warning("  [WRN]  [CLEANUP]  Port 4040 occupied — killing stale process...")
        _kill_port(4040)
        for _ in range(12):
            if not _is_port_in_use(4040):
                break
            time.sleep(0.5)
    time.sleep(0.5)  # extra settle time


    # ── Re-check health after cleanup ─────────────────────────────────────────
    api_alive = _is_service_healthy("http://127.0.0.1:4040/api/v1/health") or \
                _is_service_healthy("http://127.0.0.1:4040/")
    ui_alive  = _is_service_healthy("http://127.0.0.1:3000/")

    root_dir    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # rekov/ → project root
    is_win      = sys.platform == "win32"
    if is_win and len(root_dir) > 1 and root_dir[1] == ':':
        # Canonical uppercase drive letter prevents Windows RSC Client Manifest case mismatch
        root_dir = root_dir[0].upper() + root_dir[1:]
    backend_dir  = os.path.join(root_dir, "rekov")   # same folder as this file
    frontend_dir = os.path.join(root_dir, "rekoviu")

    # ── Load config.json Supabase & Hugging Face credentials ─────────────────
    config_candidates = [
        os.path.join(root_dir, "config.json"),
        os.path.join(backend_dir, "config.json"),
    ]
    for cfg_path in config_candidates:
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                    sb = cfg_data.get("supabase", {}) if isinstance(cfg_data.get("supabase"), dict) else {}
                    url = sb.get("url") or cfg_data.get("SUPABASE_URL")
                    key = sb.get("key") or cfg_data.get("SUPABASE_KEY")
                    if url:
                        os.environ["SUPABASE_URL"] = url
                        # Also expose to Next.js frontend via NEXT_PUBLIC_ prefix
                        os.environ["NEXT_PUBLIC_SUPABASE_URL"] = url
                    if key:
                        os.environ["SUPABASE_KEY"] = key
                        os.environ["NEXT_PUBLIC_SUPABASE_KEY"] = key
                    # Also set NEXT_PUBLIC_API_URL so the frontend always hits the right backend
                    os.environ.setdefault("NEXT_PUBLIC_API_URL", "http://localhost:4040/api/v1")
                    hf = cfg_data.get("hf_token") or cfg_data.get("HF_TOKEN") or cfg_data.get("HF_API_TOKEN") or os.environ.get("HF_TOKEN") or os.environ.get("HF_API_TOKEN") or ""
                    if hf:
                        os.environ["HF_TOKEN"] = hf
                        os.environ["HF_API_TOKEN"] = hf
                        os.environ["HUGGINGFACE_API_KEY"] = hf
                    sys_logger.success(f"  [OK]   [CONFIG] Supabase & Hugging Face credentials loaded from {os.path.basename(cfg_path)}")
                    break
            except Exception as e:
                sys_logger.warning(f"  [WRN]  [CONFIG] Could not parse {cfg_path}: {e}")

    # ── 1. Backend Python dependencies ───────────────────────────────────────
    backend_ready = False
    try:
        check_proc = subprocess.run(
            [sys.executable, "-c", "import fastapi, uvicorn, pydantic, supabase, requests, edge_tts, fpdf"],
            capture_output=True, text=True, timeout=15,
        )
        if check_proc.returncode == 0:
            backend_ready = True
    except Exception:
        backend_ready = False

    if backend_ready:
        sys_logger.success("  [OK]   [SETUP]  Backend dependencies ready.")
    else:
        sys_logger.update("  [UPD]  [SETUP]  Installing backend dependencies...")
        req_file = os.path.join(backend_dir, "requirements.txt")
        if not os.path.exists(req_file):
            req_file = os.path.join(root_dir, "requirements.txt")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", req_file, "--quiet"],
                cwd=backend_dir, check=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            sys_logger.success("  [OK]   [SETUP]  Backend dependencies ready.")
        except subprocess.CalledProcessError as e:
            sys_logger.error(f"  [ERR]  [SETUP]  Backend dependencies failed: {e}")
            sys.exit(1)

    # ── 2. Frontend Node dependencies ────────────────────────────────────────
    node_modules_dir = os.path.join(frontend_dir, "node_modules")
    if os.path.isdir(node_modules_dir):
        sys_logger.success("  [OK]   [SETUP]  Frontend dependencies ready.")
    else:
        sys_logger.update("  [UPD]  [SETUP]  Installing frontend dependencies (first-time setup)...")
        try:
            npm_cmd = shutil.which("npm.cmd") or shutil.which("npm") or ("npm.cmd" if is_win else "npm")
            subprocess.run([npm_cmd, "install"], cwd=frontend_dir, check=True, shell=is_win)
            sys_logger.success("  [OK]   [SETUP]  Frontend dependencies ready.")
        except subprocess.CalledProcessError as e:
            sys_logger.error(f"  [ERR]  [SETUP]  Frontend dependencies failed: {e}")
            sys.exit(1)

    # ── 3. Clear stale .next webpack cache & apply Windows patch ─────────────
    if not ui_alive:
        next_cache = os.path.join(frontend_dir, ".next")
        if os.path.isdir(next_cache):
            try:
                shutil.rmtree(next_cache)
                sys_logger.success("  [OK]   [UI]     Cleared stale .next cache — fresh webpack build.")
            except Exception as _e:
                sys_logger.warning(f"  [WRN]  [UI]     Could not clear .next cache: {_e}")

        patch_script = os.path.join(frontend_dir, "scripts", "patch-next-windows.js")
        if os.path.isfile(patch_script):
            try:
                subprocess.run(["node", patch_script], cwd=frontend_dir, capture_output=True, text=True, timeout=10)
                sys_logger.success("  [OK]   [UI]     Next.js Windows RSC manifest patch active.")
            except Exception as _pe:
                sys_logger.warning(f"  [WRN]  [UI]     Next.js patch script note: {_pe}")

    # ── 4. Launch services ───────────────────────────────────────────────────
    backend_cmd = [sys.executable, "-m", "uvicorn", "main:app",
                   "--host", "0.0.0.0", "--port", "4040", "--reload"]

    # Use explicit npm binary (no shell=True) so Python owns the npm process
    # directly instead of through cmd.exe, which can exit early on Windows.
    _npm_bin = (
        shutil.which("npm.cmd")   # Windows npm wrapper
        or shutil.which("npm")    # Unix / PATH fallback
        or "npm.cmd"
    )

    # On Windows, npm.cmd is a batch file that exits after spawning node,
    # giving us a false code-0 exit every time. Bypass it and call node + next
    # directly so Python owns the real node process.
    _next_bin = os.path.join(frontend_dir, "node_modules", "next", "dist", "bin", "next")
    _node_bin = shutil.which("node") or "node"
    if os.path.isfile(_next_bin):
        frontend_cmd = [_node_bin, _next_bin, "dev", "-p", "3000"]
        sys_logger.info("  [INF]  [UI]   Launching Next.js directly via node (bypasses npm.cmd wrapper)")
    else:
        # Fallback: npm run dev without shell so we at least own npm.cmd
        frontend_cmd = [_npm_bin, "run", "dev"]

    backend_process  = run_process(backend_cmd,  backend_dir,  "API") if not api_alive else None
    frontend_process = run_process(frontend_cmd, frontend_dir, "UI") if not ui_alive else None

    # ── 5. Startup banner ────────────────────────────────────────────────────
    sys_logger.info("")
    _banner("ALL SYSTEMS LAUNCHING")
    sys_logger.info("")
    _service_status("API  (FastAPI + BackupVerifier) :4040", not not backend_process or api_alive)
    _service_status("UI   (Next.js)                  :3000", not not frontend_process or ui_alive)
    sys_logger.info("")
    sys_logger.info("  ->  http://localhost:3000         (App)")
    sys_logger.info("  ->  http://localhost:3000/kiosk   (Kiosk)")
    sys_logger.info("  ->  http://localhost:4040/docs    (API Docs)")
    sys_logger.info("")
    sys_logger.info("  BLUE = compiling/updating   GREEN = working   RED = error   YELLOW = unknown")
    sys_logger.info("  Press Ctrl+C to stop all services.")
    sys_logger.info("")

    # ── 6. Keep-alive loop ───────────────────────────────────────────────────
    def _exit_code_name(code) -> str:
        if code == 4294967295 or code == -1:
            return "FORCE_KILLED"
        return str(code)

    # ui_orphaned: True when npm process exited but Next.js node is still alive
    ui_orphaned = False

    try:
        while True:
            # ── Backend: restart on non-zero exit ────────────────────────────
            if backend_process and backend_process.poll() is not None:
                code = backend_process.returncode
                if code != 0:
                    sys_logger.error(f"  [ERR]  [API]  Process exited (code {_exit_code_name(code)}) -- restarting in 3s...")
                    time.sleep(3)
                    _kill_port(4040)
                    time.sleep(1)
                    backend_process = run_process(backend_cmd, backend_dir, "API")

            # ── Frontend: process-based tracking ─────────────────────────────
            if frontend_process and frontend_process.poll() is not None:
                code = frontend_process.returncode
                frontend_process = None

                # Before killing anything, check if Next.js is actually serving.
                # On Windows, the npm wrapper can exit (code 0) while the node
                # child is still alive and healthy on :3000.
                if _is_service_healthy("http://127.0.0.1:3000/"):
                    sys_logger.info("  [INF]  [UI]   npm process exited but Next.js is still serving on :3000 — switching to port monitor")
                    ui_orphaned = True
                else:
                    # Port is either gone or not responding — real exit
                    if code == 0:
                        sys_logger.warning("  [WRN]  [UI]   Process exited cleanly — waiting for port to free...")
                    else:
                        sys_logger.error(f"  [ERR]  [UI]   Process exited (code {_exit_code_name(code)}) -- restarting in 3s...")
                        time.sleep(3)

                    # Kill any stale holder and wait until port is confirmed free
                    _kill_port(3000)
                    for _wait in range(10):          # up to 5 seconds
                        if not _is_port_in_use(3000):
                            break
                        time.sleep(0.5)
                    else:
                        sys_logger.warning("  [WRN]  [UI]   Port 3000 still occupied after kill — force-trying anyway")

                    time.sleep(1)   # small extra cushion
                    ui_orphaned = False
                    frontend_process = run_process(frontend_cmd, frontend_dir, "UI")

            # ── Frontend: port-health monitor (orphan mode) ───────────────────
            elif ui_orphaned:
                if not _is_service_healthy("http://127.0.0.1:3000/"):
                    sys_logger.warning("  [WRN]  [UI]   Next.js went down — clearing port and restarting...")
                    _kill_port(3000)
                    time.sleep(2)
                    ui_orphaned = False
                    frontend_process = run_process(frontend_cmd, frontend_dir, "UI")

            time.sleep(3)
    except KeyboardInterrupt:
        sys_logger.warning("  [WRN]  Shutting down all services...")
    finally:
        sys_logger.info("  Terminating child processes...")
        for proc in [backend_process, frontend_process]:
            if proc and proc.poll() is None:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
        sys_logger.success("  [OK]   System shutdown complete.")


if __name__ == "__main__":
    main()
