"""
interface.py - REKOV Interface Manager
========================================
Central entry point. Ask the user how they want to run REKOV:

  1  Web UI    - FastAPI backend (:4040) + Next.js frontend (:3000)
  2  CLI       - FastAPI backend only (no browser)
  3  RITMO CLI - AI assistant (HuggingFace or Offline mode)

Usage:
    python interface.py
    python main.py        (same thing - delegates here)
"""

import os
import sys
import subprocess
import shutil
import threading
import time
import socket
import urllib.request
import json

# -- REKOV credits banner -----------------------------------------------------
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from rekov_credits import print_rekov_credits as _print_rekov_credits
    _HAS_CREDITS = True
except ImportError:
    _HAS_CREDITS = False
    def _print_rekov_credits(**_kw): pass

# -- Paths --------------------------------------------------------------------
ROOT_DIR    = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "rekov")
FRONTEND_DIR = os.path.join(ROOT_DIR, "rekoviu")
BASE_DIR    = os.path.join(ROOT_DIR, "base")
IS_WIN      = sys.platform == "win32"

# -- ANSI helpers -------------------------------------------------------------
class _C:
    GREEN  = "\x1b[32;1m"
    RED    = "\x1b[31;1m"
    YELLOW = "\x1b[33;1m"
    WHITE  = "\x1b[97;1m"
    BLUE   = "\x1b[34;1m"
    CYAN   = "\x1b[36;1m"
    TEAL   = "\x1b[38;5;43m"
    DIM    = "\x1b[2m"
    RESET  = "\x1b[0m"

def _green(t):  return f"{_C.GREEN}{t}{_C.RESET}"
def _red(t):    return f"{_C.RED}{t}{_C.RESET}"
def _yellow(t): return f"{_C.YELLOW}{t}{_C.RESET}"
def _white(t):  return f"{_C.WHITE}{t}{_C.RESET}"
def _blue(t):   return f"{_C.BLUE}{t}{_C.RESET}"
def _cyan(t):   return f"{_C.CYAN}{t}{_C.RESET}"
def _dim(t):    return f"{_C.DIM}{t}{_C.RESET}"


# -- Banner -------------------------------------------------------------------
def _print_banner():
    os.system("cls" if IS_WIN else "clear")
    _print_rekov_credits(show_contributors=True, fetch_live=True)
    print(_dim("  Select how you want to interact with REKOV today."))
    print()
    print("  " + _green("  1  ") + " ->  " + _white("Web UI         ") + _dim("(browser — FastAPI + Next.js)"))
    print("  " + _C.TEAL + "  2  " + _C.RESET + " ->  " + _white("RITMO Terminal ") + _dim("(Normal / AI / Voice — no ports)"))
    print("  " + _blue("  3  ") + " ->  " + _white("Backend Server ") + _dim("(FastAPI on :4040 — for advanced users)"))
    print()
    print("  " + _dim("-" * 52))
    print()


# -- Config loader ------------------------------------------------------------
def _load_env_from_config():
    """Inject Supabase + HF creds from config.json into environment."""
    candidates = [
        os.path.join(ROOT_DIR, "config.json"),
        os.path.join(BASE_DIR, "config.json"),
        os.path.join(BACKEND_DIR, "config.json"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                sb  = cfg.get("supabase", {}) if isinstance(cfg.get("supabase"), dict) else {}
                url = sb.get("url") or cfg.get("SUPABASE_URL", "")
                key = sb.get("key") or cfg.get("SUPABASE_KEY", "")
                if url:
                    os.environ["SUPABASE_URL"]            = url
                    os.environ["NEXT_PUBLIC_SUPABASE_URL"] = url
                if key:
                    os.environ["SUPABASE_KEY"]            = key
                    os.environ["NEXT_PUBLIC_SUPABASE_KEY"] = key
                os.environ.setdefault("NEXT_PUBLIC_API_URL", "http://localhost:4040/api/v1")
                hf = (
                    cfg.get("hf_token") or cfg.get("HF_TOKEN")
                    or os.environ.get("HF_TOKEN", "")
                )
                if hf:
                    os.environ["HF_TOKEN"] = os.environ["HF_API_TOKEN"] = os.environ["HUGGINGFACE_API_KEY"] = hf
                print(_green(f"  [OK]  Config loaded from {os.path.basename(path)}"))
                return
            except Exception as e:
                print(_yellow(f"  [WRN] Could not parse {path}: {e}"))


# -- Network helpers ----------------------------------------------------------
def _port_in_use(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False


def _service_healthy(url: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "REKOV-Monitor/1.0"})
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status in (200, 304)
    except Exception:
        return False


def _kill_port(port: int):
    """Kill whatever process is listening on the given port (Windows)."""
    if not IS_WIN:
        try:
            os.system(f"fuser -k {port}/tcp 2>/dev/null")
        except Exception:
            pass
        return
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=8,
        )
        killed: set = set()
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if parts:
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) > 0 and pid not in killed:
                        killed.add(pid)
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", pid],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        )
    except Exception:
        pass


# -- Subprocess stream reader -------------------------------------------------
_SUCCESS_PAT = {
    "compiled successfully", "ready in", "ready started",
    "application startup complete", "uvicorn running",
    "started server", "[ok]", "compiled /",
}
_ERROR_PAT = {
    "error:", "traceback", "exception:", "failed to compile",
    "module not found", "typeerror", "exit code", "eaddrinuse",
    "fatal:", "[failed]",
}
_SUPPRESS_PAT = {"node_modules/next/dist/", "at module.", "at wrapmodule", "webpack-runtime"}


def _route_line(line: str, name: str):
    lo = line.lower()
    if any(p in lo for p in _SUPPRESS_PAT):
        return
    stripped = line.strip("-=* \t")
    if not stripped:
        return
    if any(p in lo for p in _ERROR_PAT):
        print(_red(f"  [ERR] [{name}]  {line}"))
    elif any(p in lo for p in _SUCCESS_PAT):
        print(_green(f"  [OK]  [{name}]  {line}"))
    else:
        print(_dim(f"  [..]  [{name}]  {line}"))


def _read_stream(stream, name: str):
    for raw in iter(stream.readline, b""):
        line = raw.decode("utf-8", errors="replace").rstrip()
        if line.strip():
            _route_line(line, name)
    stream.close()


def _spawn(cmd, cwd: str, name: str):
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"]        = "1"
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    proc = subprocess.Popen(
        cmd, cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, stdin=subprocess.DEVNULL,
    )
    threading.Thread(target=_read_stream, args=(proc.stdout, name), daemon=True).start()
    threading.Thread(target=_read_stream, args=(proc.stderr, name), daemon=True).start()
    return proc


# =============================================================================
#  MODE 1 - WEB UI
# =============================================================================
def launch_webui():
    print()
    print(_green("  [REKOV]  Mode 1 - Web UI"))
    print()

    _load_env_from_config()

    # Install backend deps
    try:
        r = subprocess.run(
            [sys.executable, "-c",
             "import fastapi, uvicorn, pydantic, supabase, requests, edge_tts, fpdf"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            raise RuntimeError("missing deps")
        print(_green("  [OK]  Backend dependencies ready."))
    except Exception:
        print(_yellow("  [UPD] Installing backend dependencies..."))
        req = os.path.join(BACKEND_DIR, "requirements.txt")
        if not os.path.exists(req):
            req = os.path.join(ROOT_DIR, "requirements.txt")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req, "--quiet"],
            cwd=BACKEND_DIR, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        print(_green("  [OK]  Backend dependencies installed."))

    # Install frontend deps
    if os.path.isdir(os.path.join(FRONTEND_DIR, "node_modules")):
        print(_green("  [OK]  Frontend dependencies ready."))
    else:
        print(_yellow("  [UPD] Installing frontend dependencies (first-time)..."))
        npm = shutil.which("npm.cmd") or shutil.which("npm") or ("npm.cmd" if IS_WIN else "npm")
        subprocess.run([npm, "install"], cwd=FRONTEND_DIR, check=True, shell=IS_WIN)
        print(_green("  [OK]  Frontend dependencies installed."))

    # Clear .next cache
    next_cache = os.path.join(FRONTEND_DIR, ".next")
    if os.path.isdir(next_cache):
        try:
            shutil.rmtree(next_cache)
            print(_green("  [OK]  Cleared stale .next cache."))
        except Exception as e:
            print(_yellow(f"  [WRN] Could not clear .next cache: {e}"))

    # Kill stale ports
    for port in (3000, 4040):
        if _port_in_use(port):
            print(_yellow(f"  [WRN] Port {port} occupied - clearing..."))
            _kill_port(port)
            time.sleep(1)

    # Build launch commands
    backend_cmd = [
        sys.executable, "-m", "uvicorn", "main:app",
        "--host", "0.0.0.0", "--port", "4040", "--reload",
    ]
    _node  = shutil.which("node") or "node"
    _next  = os.path.join(FRONTEND_DIR, "node_modules", "next", "dist", "bin", "next")
    _npm   = shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
    frontend_cmd = (
        [_node, _next, "dev", "-p", "3000"]
        if os.path.isfile(_next)
        else [_npm, "run", "dev"]
    )

    # Launch
    api_proc = _spawn(backend_cmd,  BACKEND_DIR,  "API")
    ui_proc  = _spawn(frontend_cmd, FRONTEND_DIR, "UI")

    print()
    print(_green("  ALL SYSTEMS LAUNCHING"))
    print()
    print(_cyan("    http://localhost:3000          (App)"))
    print(_cyan("    http://localhost:3000/kiosk    (Kiosk)"))
    print(_cyan("    http://localhost:4040/docs     (API Docs)"))
    print()
    print(_dim("  GREEN = ready   RED = error   Ctrl+C to stop"))
    print()

    # Keep-alive loop
    ui_orphaned = False
    try:
        while True:
            # Backend watchdog
            if api_proc and api_proc.poll() is not None:
                if api_proc.returncode != 0:
                    print(_red("  [ERR] [API] Crashed - restarting in 3s..."))
                    time.sleep(3)
                    _kill_port(4040)
                    time.sleep(1)
                    api_proc = _spawn(backend_cmd, BACKEND_DIR, "API")

            # Frontend watchdog
            if ui_proc and ui_proc.poll() is not None:
                code = ui_proc.returncode
                ui_proc = None
                if _service_healthy("http://127.0.0.1:3000/"):
                    ui_orphaned = True
                else:
                    print(_red(f"  [ERR] [UI] Exited (code {code}) - restarting..."))
                    time.sleep(3)
                    _kill_port(3000)
                    time.sleep(1)
                    ui_proc = _spawn(frontend_cmd, FRONTEND_DIR, "UI")
            elif ui_orphaned and not _service_healthy("http://127.0.0.1:3000/"):
                print(_yellow("  [WRN] [UI] Next.js went down - restarting..."))
                _kill_port(3000)
                time.sleep(2)
                ui_orphaned = False
                ui_proc = _spawn(frontend_cmd, FRONTEND_DIR, "UI")

            time.sleep(3)
    except KeyboardInterrupt:
        print()
        print(_yellow("  [WRN] Shutting down all services..."))
    finally:
        for proc in [api_proc, ui_proc]:
            if proc and proc.poll() is None:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
        print(_green("  [OK]  Shutdown complete."))


# =============================================================================
#  MODE 2 - CLI
# =============================================================================
def launch_cli():
    print()
    print(_blue("  [REKOV]  Mode 2 - CLI"))
    print()
    print(_dim("  Starting REKOV in terminal mode (FastAPI backend only)."))
    print(_dim("  No browser or Next.js frontend will be launched."))
    print()

    _load_env_from_config()

    # Install backend deps
    try:
        r = subprocess.run(
            [sys.executable, "-c",
             "import fastapi, uvicorn, pydantic, supabase, requests, edge_tts, fpdf"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            raise RuntimeError("missing deps")
        print(_green("  [OK]  Backend dependencies ready."))
    except Exception:
        print(_yellow("  [UPD] Installing backend dependencies..."))
        req = os.path.join(BACKEND_DIR, "requirements.txt")
        if not os.path.exists(req):
            req = os.path.join(ROOT_DIR, "requirements.txt")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req, "--quiet"],
            cwd=BACKEND_DIR, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        print(_green("  [OK]  Backend dependencies installed."))

    if _port_in_use(4040):
        print(_yellow("  [WRN] Port 4040 occupied - clearing..."))
        _kill_port(4040)
        time.sleep(1)

    backend_cmd = [
        sys.executable, "-m", "uvicorn", "main:app",
        "--host", "0.0.0.0", "--port", "4040", "--reload",
    ]
    api_proc = _spawn(backend_cmd, BACKEND_DIR, "API")

    print()
    print(_blue("  REKOV CLI - API RUNNING"))
    print()
    print(_cyan("    http://localhost:4040/docs     (API Docs / Swagger)"))
    print(_cyan("    http://localhost:4040/api/v1   (REST API base)"))
    print()

    # Interactive CLI loop
    print(_dim("  CLI Commands:"))
    print(_dim("    status   - check service health"))
    print(_dim("    restart  - restart the API server"))
    print(_dim("    quit     - stop and exit"))
    print()

    try:
        while True:
            try:
                cmd = input(_white("  rekov> ")).strip().lower()
            except EOFError:
                break

            if cmd in ("quit", "exit", "q"):
                break
            elif cmd == "status":
                alive = (
                    _service_healthy("http://127.0.0.1:4040/api/v1/health")
                    or _service_healthy("http://127.0.0.1:4040/")
                )
                proc_alive = api_proc and api_proc.poll() is None
                print(_green("  API  :4040  ONLINE") if alive else _red("  API  :4040  OFFLINE / STARTING"))
                print(_green("  Process  ALIVE") if proc_alive else _red("  Process  DEAD"))
            elif cmd == "restart":
                print(_yellow("  [WRN] Restarting API..."))
                if api_proc and api_proc.poll() is None:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(api_proc.pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                time.sleep(1)
                _kill_port(4040)
                time.sleep(1)
                api_proc = _spawn(backend_cmd, BACKEND_DIR, "API")
                print(_green("  [OK]  API restarted."))
            elif cmd == "help":
                print(_dim("  status / restart / quit"))
            elif cmd == "":
                pass
            else:
                print(_yellow(f"  Unknown command: '{cmd}'  (type 'help')"))

    except KeyboardInterrupt:
        print()
    finally:
        print(_yellow("  [WRN] Shutting down..."))
        if api_proc and api_proc.poll() is None:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(api_proc.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        print(_green("  [OK]  Shutdown complete."))


# =============================================================================
#  RITMO SUB-MENU (Mode 3)
# =============================================================================

def _print_ritmo_submenu():
    os.system("cls" if IS_WIN else "clear")
    try:
        from rekov_credits import print_rekov_credits
        print_rekov_credits(compact=True, show_contributors=False)
    except Exception:
        pass
    print()
    print("  " + "\x1b[38;5;43m" + "  ╔══════════════════════════════════════════════════════╗" + "\x1b[0m")
    print("  " + "\x1b[38;5;43m" + "  ║" + "\x1b[0m" + _white("   RITMO  —  Select Mode                              ") + "\x1b[38;5;43m" + "║" + "\x1b[0m")
    print("  " + "\x1b[38;5;43m" + "  ╚══════════════════════════════════════════════════════╝" + "\x1b[0m")
    print()
    print(f"  {_green('  1  ')} ->  {_white('Normal Mode')}    {_dim('guided form — name, dept, receipt (no AI)')}")
    print()
    print(f"  {_cyan('  2  ')} ->  {_white('RITMO AI Mode')}  {_dim('conversational AI — HuggingFace or Offline ONNX')}")
    print()
    print(f"  {'\x1b[35;1m  3  \x1b[0m'} ->  {_white('Voice Mode')}    {_dim('always listening — fully voice operated (STT+TTS)')}")
    print()
    print("  " + _dim("-" * 52))
    print()


def _pick_ritmo_mode() -> str:
    while True:
        try:
            choice = input(_white("  Enter choice [1/2/3]: ")).strip()
        except (KeyboardInterrupt, EOFError):
            print(); sys.exit(0)
        if choice in ("1", "2", "3"):
            return choice
        print(_red(f"  Invalid choice '{choice}'. Please enter 1, 2, or 3."))


def launch_ritmocli():
    """Show RITMO sub-menu and launch the chosen mode."""
    _print_ritmo_submenu()
    mode = _pick_ritmo_mode()

    if mode == "1":
        # Normal guided form mode
        try:
            sys.path.insert(0, ROOT_DIR)
            from ritmo.normal_mode import run_normal_mode
            run_normal_mode()
        except ImportError as e:
            print(_red(f"  [ERR] Could not load Normal Mode: {e}"))
        except KeyboardInterrupt:
            pass

    elif mode == "2":
        # Existing RITMO AI CLI (HF or Offline ONNX)
        ritmocli_path = os.path.join(ROOT_DIR, "ritmo", "ritmocli.py")
        if not os.path.isfile(ritmocli_path):
            print(_red("  [ERR] ritmo/ritmocli.py not found."))
            return
        try:
            subprocess.run([sys.executable, ritmocli_path], cwd=ROOT_DIR)
        except KeyboardInterrupt:
            pass

    elif mode == "3":
        # Voice Mode
        try:
            sys.path.insert(0, ROOT_DIR)
            from ritmo.voice import pick_stt_engine, run_voice_loop

            # Try to wire up the HF AI backend for voice mode
            stt = pick_stt_engine()

            try:
                from ritmo.pull import RitmoPull
                _load_env_from_config()
                cfg_path = os.path.join(ROOT_DIR, "config.json")
                cfg = {}
                if os.path.isfile(cfg_path):
                    import json
                    with open(cfg_path) as f:
                        cfg = json.load(f)
                hf_token = (cfg.get("hf_token") or cfg.get("HF_TOKEN")
                            or os.environ.get("HF_TOKEN", ""))
                rp = RitmoPull(hf_token=hf_token)

                def _ai_reply(text):
                    reply, ms, source, action, action_data = rp.send(text)
                    return reply, action, action_data

                print(_cyan("  [VOICE] Using HuggingFace AI backend."))
            except Exception as hf_err:
                print(_yellow(f"  [VOICE] HF not available ({hf_err}) — using echo mode."))
                def _ai_reply(text):
                    return f"You said: {text}", None, {}

            run_voice_loop(_ai_reply, stt_engine=stt)

        except ImportError as e:
            print(_red(f"  [ERR] Voice mode requires additional packages: {e}"))
            print(_yellow("  Run: pip install SpeechRecognition sounddevice edge-tts pygame"))
        except KeyboardInterrupt:
            pass


# =============================================================================
#  ENTRY POINT
# =============================================================================
def main():
    _print_banner()

    while True:
        try:
            choice = input(_white("  Enter choice [1/2/3]: ")).strip()
        except (KeyboardInterrupt, EOFError):
            print()
            print(_yellow("  Cancelled."))
            sys.exit(0)

        if choice == "1":
            launch_webui()
            break
        elif choice == "2":
            launch_ritmocli()
            break
        elif choice == "3":
            launch_cli()
            break
        else:
            print(_red(f"  Invalid choice '{choice}'. Please enter 1, 2, or 3."))
            print()


if __name__ == "__main__":
    main()
