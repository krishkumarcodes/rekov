"""
interface.py - REKOV Interface Manager
========================================
Central entry point. Ask the user how they want to run REKOV:

  1  CLI      - Terminal mode (Normal booking / RITMO AI / RITMO Voice)
  2  Web UI   - Next.js frontend + FastAPI backend on port 3000

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

if sys.stdout.encoding.lower() != 'utf-8' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# -- REKOV credits banner -----------------------------------------------------
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from rekov_credits import print_rekov_credits as _print_rekov_credits
    _HAS_CREDITS = True
except ImportError:
    _HAS_CREDITS = False
    def _print_rekov_credits(**_kw): pass

# -- Paths --------------------------------------------------------------------
ROOT_DIR     = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR  = os.path.join(ROOT_DIR, "rekov")
FRONTEND_DIR = os.path.join(ROOT_DIR, "rekoviu")
BASE_DIR     = os.path.join(ROOT_DIR, "base")
CONN_DIR     = os.path.join(ROOT_DIR, "connection")
IS_WIN       = sys.platform == "win32"

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
    print("  " + _green("  1  ") + " ->  " + _white("CLI            ") + _dim("(terminal — Normal booking / RITMO AI / Voice)"))
    print("  " + _C.TEAL + "  2  " + _C.RESET + " ->  " + _white("Web UI         ") + _dim("(browser — Next.js + FastAPI on port 3000)"))
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
                os.environ.setdefault("NEXT_PUBLIC_API_URL", "http://localhost:3000/api/v1")
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
    """Kill whatever process is listening on the given port."""
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


def _spawn(cmd, cwd: str, name: str):
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"]        = "1"
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    print(_dim(f"  [*] Starting {name}..."))
    proc = subprocess.Popen(
        cmd, cwd=cwd,
        env=env, stdin=subprocess.DEVNULL,
        shell=IS_WIN
    )
    return proc


# =============================================================================
#  MODE 1 - CLI (Normal / RITMO AI / Voice — all terminal, no ports)
# =============================================================================

def _print_cli_submenu():
    os.system("cls" if IS_WIN else "clear")
    try:
        from rekov_credits import print_rekov_credits
        print_rekov_credits(compact=True, show_contributors=False)
    except Exception:
        pass

    # Active language badge
    try:
        from language.manager import LM
        lang_badge = f"{LM.color}{LM.flag}  {LM.name}  ({LM.native}){_C.RESET}"
    except Exception:
        lang_badge = "[EN]  English"

    print()
    print("  " + _C.TEAL + "  REKOV CLI  —  Select Mode" + _C.RESET + f"  {_dim(lang_badge)}")
    print("  " + _dim("-" * 60))
    print()
    print(f"  {_green('  1  ')} ->  {_white('Normal Mode')}    {_dim('guided form — name, phone, dept, receipt')}")
    print()
    print(f"  {_cyan('  2  ')} ->  {_white('RITMO AI Mode')}  {_dim('AI chat — HuggingFace (online) or Offline ONNX')}")
    print()
    print(f"  {_C.TEAL}  3  {_C.RESET} ->  {_white('Voice Mode')}    {_dim('always listening — fully voice operated (STT+TTS)')}")
    print()
    print(f"  {_dim('  0  ')} ->  {_white('Back')}           {_dim('return to main menu')}")
    print()
    print("  " + _dim("-" * 60))
    print()


def _pick_cli_mode() -> str:
    while True:
        try:
            choice = input(_white("  Enter choice [1/2/3/0]: ")).strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return "0"
        if choice in ("1", "2", "3", "0"):
            return choice
        print(_red(f"  Invalid choice '{choice}'. Enter 1, 2, 3, or 0 to go back."))


def launch_cli():
    """CLI mode — show language picker, then Normal booking / RITMO AI / Voice. No ports."""
    # -- Language picker (animated, shown once per CLI session) ---------------
    try:
        from language.picker  import show_language_picker
        from language.manager import LM, set_lang
        lang_key = show_language_picker()
        set_lang(lang_key)
        import time; time.sleep(0.4)
    except Exception as _le:
        print(_yellow(f"  [LANG] Picker unavailable ({_le}) — defaulting to English."))

    while True:
        _print_cli_submenu()
        mode = _pick_cli_mode()

        if mode == "0":
            return  # back to main menu

        elif mode == "1":
            # Normal guided form mode
            try:
                sys.path.insert(0, ROOT_DIR)
                from ritmo.normal_mode import run_normal_mode
                run_normal_mode()
            except ImportError as e:
                print(_red(f"  [ERR] Could not load Normal Mode: {e}"))
            except KeyboardInterrupt:
                pass
            # After returning from normal mode, loop back to CLI submenu

        elif mode == "2":
            # RITMO AI CLI (HF or Offline ONNX)
            ritmocli_path = os.path.join(ROOT_DIR, "ritmo", "ritmocli.py")
            if not os.path.isfile(ritmocli_path):
                print(_red("  [ERR] ritmo/ritmocli.py not found."))
                input(_dim("  Press Enter to go back..."))
                continue
            try:
                subprocess.run([sys.executable, ritmocli_path], cwd=ROOT_DIR)
            except KeyboardInterrupt:
                pass

        elif mode == "3":
            # Voice Mode
            try:
                sys.path.insert(0, ROOT_DIR)
                from ritmo.voice import pick_stt_engine, run_voice_loop

                stt = pick_stt_engine()

                try:
                    from ritmo.pull import RitmoPull
                    _load_env_from_config()
                    cfg_path = os.path.join(ROOT_DIR, "config.json")
                    cfg = {}
                    if os.path.isfile(cfg_path):
                        with open(cfg_path) as f:
                            cfg = json.load(f)
                    hf_token = (cfg.get("hf_token") or cfg.get("HF_TOKEN")
                                or os.environ.get("HF_TOKEN", ""))
                    rp = RitmoPull(token=hf_token)

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
                input(_dim("  Press Enter to go back..."))
            except KeyboardInterrupt:
                pass

        # After any mode completes, ask to go back or stay
        print()
        try:
            again = input(_white("  Back to CLI menu?  [Y/n]: ")).strip().lower()
        except (KeyboardInterrupt, EOFError):
            return
        if again in ("n", "no"):
            return


# =============================================================================
#  MODE 2 - WEB UI (Next.js + FastAPI unified on port 3000)
# =============================================================================
def launch_webui():
    print()
    print(_green("  [REKOV]  Mode 2 - Web UI"))
    print()

    _load_env_from_config()

    # Install backend deps
    try:
        r = subprocess.run(
            [sys.executable, "-c",
             "import fastapi, uvicorn, pydantic, supabase, requests"],
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

    # Always clear port 3000 just in case
    print(_yellow("  [INF] Clearing port 3000..."))
    _kill_port(3000)
    time.sleep(1)

    # Launch connection server (unified on :3000) if it exists,
    # otherwise fall back to launching frontend + backend separately
    conn_server = os.path.join(CONN_DIR, "server.py")
    if os.path.isfile(conn_server):
        print(_green("  [OK]  Using unified connection server (port 3000)."))
        backend_cmd = [sys.executable, conn_server]
        api_proc = _spawn(backend_cmd, CONN_DIR, "SERVER")
        
        # If there's no static export, we must run the Next.js dev server on port 3001
        if not os.path.isdir(os.path.join(FRONTEND_DIR, "out")):
            print(_yellow("  [INF] Clearing port 3001..."))
            _kill_port(3001)
            time.sleep(1)
            _node  = shutil.which("node") or "node"
            _next  = os.path.join(FRONTEND_DIR, "node_modules", "next", "dist", "bin", "next")
            _npm   = shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
            frontend_cmd = (
                [_node, _next, "dev", "-p", "3001"]
                if os.path.isfile(_next)
                else [_npm, "run", "dev", "--", "-p", "3001"]
            )
            ui_proc = _spawn(frontend_cmd, FRONTEND_DIR, "UI")
        else:
            ui_proc = None
    else:
        # Legacy: frontend on :3000, FastAPI on :3000/api via proxy
        _kill_port(4040)
        time.sleep(1)
        _kill_port(3000)
        time.sleep(1)

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
        api_proc = _spawn(backend_cmd, BACKEND_DIR, "API")
        ui_proc  = _spawn(frontend_cmd, FRONTEND_DIR, "UI")

    print()
    print(_green("  ALL SYSTEMS LAUNCHING"))
    print()
    print(_cyan("    http://localhost:3000          (App)"))
    print(_cyan("    http://localhost:3000/kiosk    (Kiosk)"))
    print(_cyan("    http://localhost:3000/api/v1   (API)"))
    print()
    print(_dim("  GREEN = ready   RED = error   Ctrl+C to stop"))
    print()

    # Automatically load the webpage in the browser
    try:
        import webbrowser
        time.sleep(1.5)  # Wait briefly for Next.js to start binding
        webbrowser.open("http://localhost:3000/kiosk")
    except Exception:
        pass

    # Keep-alive loop
    try:
        while True:
            if api_proc and api_proc.poll() is not None:
                if api_proc.returncode != 0:
                    print(_red("  [ERR] Server crashed - restarting in 3s..."))
                    time.sleep(3)
                    if conn_server and os.path.isfile(conn_server):
                        _kill_port(3000)
                        time.sleep(1)
                        api_proc = _spawn(backend_cmd, CONN_DIR, "SERVER")
                    else:
                        _kill_port(4040)
                        time.sleep(1)
                        api_proc = _spawn(backend_cmd, BACKEND_DIR, "API")

            if ui_proc and ui_proc.poll() is not None:
                code = ui_proc.returncode
                ui_proc = None
                ui_port = 3001 if conn_server and os.path.isfile(conn_server) else 3000
                if not _service_healthy(f"http://127.0.0.1:{ui_port}/"):
                    print(_red(f"  [ERR] [UI] Exited (code {code}) - restarting..."))
                    time.sleep(3)
                    _kill_port(ui_port)
                    time.sleep(1)
                    ui_proc = _spawn(frontend_cmd, FRONTEND_DIR, "UI")

            time.sleep(3)
    except KeyboardInterrupt:
        print()
        print(_yellow("  [WRN] Shutting down all services..."))
    finally:
        procs = [api_proc]
        if ui_proc:
            procs.append(ui_proc)
        for proc in procs:
            if proc and proc.poll() is None:
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    proc.terminate()
        print(_green("  [OK]  Shutdown complete."))


# =============================================================================
#  ENTRY POINT
# =============================================================================
def main():
    _print_banner()

    while True:
        try:
            choice = input(_white("  Enter choice [1/2]: ")).strip()
        except (KeyboardInterrupt, EOFError):
            print()
            print(_yellow("  Cancelled."))
            sys.exit(0)

        if choice == "1":
            launch_cli()
            # After returning from CLI, re-show main menu
            _print_banner()
        elif choice == "2":
            launch_webui()
            break
        else:
            print(_red(f"  Invalid choice '{choice}'. Please enter 1 or 2."))
            print()


if __name__ == "__main__":
    main()
