"""
ritmo/support.py — RITMO Configuration Checker & Support Tool
==============================================================
Diagnoses whether HuggingFace and Offline Qwen (ONNX) are ready.
Run standalone at any time to check / fix your setup.

Usage:
    python ritmo/support.py             # full check + report
    python ritmo/support.py --fix       # interactive fix wizard
    python ritmo/support.py --json      # machine-readable JSON output

HF + ONNX logic lives in: huggfaceonnx/ (shared layer)
Called automatically by ritmo/cli.py at startup (status bar only).
"""

import os
import sys
import json
import time
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

# ── Paths ─────────────────────────────────────────────────────────────────────
RITMO_DIR   = Path(__file__).resolve().parent   # ritmo/
ROOT_DIR    = RITMO_DIR.parent                  # project root
CONFIG_PATH = ROOT_DIR / "config.json"
MODELS_DIR  = ROOT_DIR / "base" / "models"
BACKEND_URL = "http://localhost:4040"

sys.path.insert(0, str(ROOT_DIR))

# ── Shared HF + ONNX layer ────────────────────────────────────────────────────
try:
    from huggfaceonnx import hfmanager as _hfm
    from huggfaceonnx import onnx as _onnx
    OFFLINE_MODELS = {v["hf_id"].split("/")[-1]: v for v in _onnx.OFFLINE_MODELS.values()}
    _HAS_SHARED = True
except ImportError:
    _HAS_SHARED = False
    # Inline fallback (in case huggfaceonnx is unavailable)
    OFFLINE_MODELS = {
        "Qwen2.5-0.5B-Instruct": {
            "hf_id":   "Qwen/Qwen2.5-0.5B-Instruct",
            "size":    "~1 GB",
            "ram":     "~2 GB RAM",
            "quality": "Fast",
        },
        "Qwen2.5-1.5B-Instruct": {
            "hf_id":   "Qwen/Qwen2.5-1.5B-Instruct",
            "size":    "~3 GB",
            "ram":     "~4 GB RAM",
            "quality": "Smarter",
        },
        "Qwen2.5-3B-Instruct": {
            "hf_id":   "Qwen/Qwen2.5-3B-Instruct",
            "size":    "~6 GB",
            "ram":     "~8 GB RAM",
            "quality": "Best",
        },
    }


# ── ANSI Colors ───────────────────────────────────────────────────────────────
class C:
    TEAL    = "\x1b[38;5;43m"
    GREEN   = "\x1b[32;1m"
    YELLOW  = "\x1b[33;1m"
    RED     = "\x1b[31;1m"
    BLUE    = "\x1b[34;1m"
    CYAN    = "\x1b[36;1m"
    WHITE   = "\x1b[97;1m"
    DIM     = "\x1b[2m"
    RESET   = "\x1b[0m"

def _c(color, t): return f"{color}{t}{C.RESET}"
def green(t):  return _c(C.GREEN,  t)
def red(t):    return _c(C.RED,    t)
def yellow(t): return _c(C.YELLOW, t)
def cyan(t):   return _c(C.CYAN,   t)
def teal(t):   return _c(C.TEAL,   t)
def dim(t):    return _c(C.DIM,    t)
def white(t):  return _c(C.WHITE,  t)
def blue(t):   return _c(C.BLUE,   t)

def _ok(msg):   print(f"  {green('[OK]')}  {msg}")
def _warn(msg): print(f"  {yellow('[WRN]')} {msg}")
def _err(msg):  print(f"  {red('[ERR]')} {msg}")
def _info(msg): print(f"  {blue('[INF]')} {msg}")


# ═══════════════════════════════════════════════════════════════════════════════
#  CHECK FUNCTIONS — each returns a dict result
# ═══════════════════════════════════════════════════════════════════════════════

def check_config_file() -> dict:
    """Check if config.json exists and is valid JSON."""
    result = {
        "name":    "config.json",
        "ok":      False,
        "path":    str(CONFIG_PATH),
        "message": "",
    }
    if not CONFIG_PATH.exists():
        result["message"] = f"Not found at {CONFIG_PATH}"
        return result
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        result["ok"]      = True
        result["data"]    = data
        result["message"] = f"Loaded ({CONFIG_PATH.stat().st_size} bytes)"
    except json.JSONDecodeError as e:
        result["message"] = f"Invalid JSON: {e}"
    except Exception as e:
        result["message"] = f"Read error: {e}"
    return result


def check_hf_token(cfg_data: Optional[dict] = None) -> dict:
    """Check if a HuggingFace token is configured."""
    result = {
        "name":    "HuggingFace Token",
        "ok":      False,
        "token":   "",
        "source":  "",
        "message": "",
    }
    if cfg_data is None:
        r = check_config_file()
        cfg_data = r.get("data", {})

    token = (
        cfg_data.get("hf_token") or cfg_data.get("HF_TOKEN")
        or os.environ.get("HF_TOKEN") or os.environ.get("HF_API_TOKEN") or ""
    )

    if not token:
        result["message"] = "No HF token found in config.json or environment"
        return result

    if not token.startswith("hf_"):
        result["message"] = f"Token present but looks invalid (expected 'hf_...')"
        result["token"]   = token[:6] + "..." if len(token) > 6 else token
        return result

    # Source tracking
    if cfg_data.get("hf_token") or cfg_data.get("HF_TOKEN"):
        source = "config.json"
    elif os.environ.get("HF_TOKEN"):
        source = "env:HF_TOKEN"
    else:
        source = "env:HF_API_TOKEN"

    result["ok"]     = True
    result["token"]  = token[:8] + "..." + token[-4:]  # masked: hf_PuBR...qMHF
    result["source"] = source
    result["message"] = f"Configured ({source})"
    return result


def check_hf_api_reachable(hf_token: str = "") -> dict:
    """Ping HuggingFace API to verify the token works."""
    if _HAS_SHARED:
        return _hfm.check_hf_api(hf_token)
    # inline fallback (huggfaceonnx unavailable)
    result: dict = {
        "name": "HuggingFace API", "ok": False, "message": "", "latency_ms": None,
    }
    if not hf_token:
        result["message"] = "No token — skipping API ping"
        return result
    try:
        req = urllib.request.Request(
            "https://huggingface.co/api/whoami",
            headers={"Authorization": f"Bearer {hf_token}", "User-Agent": "RitmoSupport/1.0"},
        )
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=8) as r:
            ms   = int((time.time() - t0) * 1000)
            body = json.loads(r.read().decode())
            result["ok"]         = True
            result["latency_ms"] = ms
            result["message"]    = f"Valid token  user={body.get('name','?')}  latency={ms}ms"
    except urllib.error.HTTPError as e:
        result["message"] = (
            "Token rejected (401 Unauthorized) — token may be expired" if e.code == 401
            else f"HTTP {e.code} from HuggingFace"
        )
    except Exception as ex:
        result["message"] = f"Cannot reach HuggingFace: {ex}"
    return result


def check_hf_inference_models() -> dict:
    """Check which Qwen models are accessible via the HF inference router."""
    if _HAS_SHARED:
        cfg_data = check_config_file().get("data", {})
        token = (
            cfg_data.get("hf_token") or cfg_data.get("HF_TOKEN")
            or os.environ.get("HF_TOKEN", "")
        )
        return _hfm.check_hf_models(token)
    return {"name": "HF Inference Models", "ok": False, "models": {}, "message": "huggfaceonnx not installed"}


def check_offline_deps() -> dict:
    """Check if the ONNX Runtime stack is installed."""
    if _HAS_SHARED:
        return _onnx.check_onnx_deps_detail()
    # inline fallback
    import importlib as _il
    result: dict = {
        "name": "Offline Dependencies (ONNX)", "ok": False, "details": {}, "message": "",
    }
    packages = {"onnxruntime": "onnxruntime", "optimum": "optimum", "transformers": "transformers"}
    missing = []
    for display, pkg in packages.items():
        try:
            mod = _il.import_module(pkg)
            result["details"][display] = f"installed  v{getattr(mod, '__version__', '?')}"
        except ImportError:
            result["details"][display] = "NOT INSTALLED"
            missing.append(display)
    result["ok"]      = not missing
    result["message"] = "All ONNX packages installed" if not missing else f"Missing: {', '.join(missing)}"
    return result


def check_offline_models() -> dict:
    """Check which Qwen ONNX models are cached in base/models/."""
    if _HAS_SHARED:
        return _onnx.check_model_cache(MODELS_DIR)
    # inline fallback
    result: dict = {
        "name":      "Offline Models Cache (ONNX)",
        "ok":        False,
        "models":    {},
        "cache_dir": str(MODELS_DIR),
        "message":   "",
    }
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    any_found = False
    for model_name, info in OFFLINE_MODELS.items():
        onnx_path = MODELS_DIR / (model_name + "-onnx")
        if onnx_path.exists():
            try:
                total   = sum(f.stat().st_size for f in onnx_path.rglob("*") if f.is_file())
                has_o   = any(onnx_path.rglob("*.onnx"))
                has_cfg = (onnx_path / "config.json").exists()
                status  = "READY" if (has_o and has_cfg) else "INCOMPLETE"
                result["models"][model_name] = {
                    "status":  status,
                    "size_gb": round(total / (1024**3), 2),
                    "path":    str(onnx_path),
                    "hf_id":   info["hf_id"],
                    "quality": info["quality"],
                    "engine":  "ONNX Runtime",
                }
                if status == "READY":
                    any_found = True
            except Exception as e:
                result["models"][model_name] = {"status": f"ERROR: {e}", "hf_id": info["hf_id"]}
        else:
            result["models"][model_name] = {
                "status": "NOT DOWNLOADED", "size": info["size"],
                "ram": info["ram"], "hf_id": info["hf_id"], "quality": info["quality"],
                "engine": "ONNX Runtime (auto-export on first run)",
            }
    result["ok"]      = any_found
    result["message"] = (
        f"{sum(1 for m in result['models'].values() if m.get('status')=='READY')} ONNX model(s) ready"
        if any_found else "No ONNX models cached yet — will download+export on first use"
    )
    return result


def check_backend() -> dict:
    """Check if the REKOV FastAPI backend is running (Skipped for standalone RITMO)."""
    return {
        "name":       "REKOV Backend",
        "ok":         False,
        "url":        BACKEND_URL,
        "message":    "Backend check skipped (RITMO runs standalone)",
        "latency_ms": None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  FULL REPORT
# ═══════════════════════════════════════════════════════════════════════════════

def run_full_check(verbose: bool = True, ping_hf: bool = True) -> dict:
    """Run all checks and return a combined status dict."""
    report = {}

    # 1. config.json
    r_cfg = check_config_file()
    report["config"] = r_cfg
    cfg_data = r_cfg.get("data", {})

    # 2. HF token present
    r_token = check_hf_token(cfg_data)
    report["hf_token"] = r_token

    # 3. HF API reachable (optional, slow)
    if ping_hf and r_token["ok"]:
        r_api = check_hf_api_reachable(
            cfg_data.get("hf_token") or cfg_data.get("HF_TOKEN") or ""
        )
    else:
        r_api = {"name": "HuggingFace API", "ok": None, "message": "Skipped"}
    report["hf_api"] = r_api

    # 4. Offline deps
    r_deps = check_offline_deps()
    report["offline_deps"] = r_deps

    # 5. Offline model cache
    r_models = check_offline_models()
    report["offline_models"] = r_models

    # 6. Backend
    r_backend = check_backend()
    report["backend"] = r_backend

    # Overall readiness
    hf_ready      = r_token["ok"]
    offline_ready = r_deps["ok"] and r_models["ok"]
    report["summary"] = {
        "hf_ready":      hf_ready,
        "offline_ready": offline_ready,
        "any_ready":     hf_ready or offline_ready,
    }

    if verbose:
        _print_report(report)

    return report


def _print_report(report: dict):
    """Pretty-print the full status report to terminal."""
    print()
    print(teal("  ╔══════════════════════════════════════════════════════╗"))
    print(teal("  ║") + white("   RITMO Support — Configuration Status               ") + teal("║"))
    print(teal("  ╚══════════════════════════════════════════════════════╝"))
    print()

    # ── Config file ───────────────────────────────────────────────────────────
    r = report["config"]
    _status_line("config.json", r["ok"], r["message"])

    # ── HuggingFace section ───────────────────────────────────────────────────
    print()
    print(cyan("  ── HuggingFace (Cloud) ──────────────────────────────────"))

    r = report["hf_token"]
    if r["ok"]:
        _status_line("HF Token", True, f"{r['message']}  [{r['token']}]")
    else:
        _status_line("HF Token", False, r["message"])

    r = report["hf_api"]
    if r.get("ok") is None:
        print(f"  {dim('[---]')} HF API Ping       {dim('skipped (no token)')}")
    elif r["ok"]:
        _status_line("HF API Ping", True,  r["message"])
    else:
        _status_line("HF API Ping", False, r["message"])

    # HF readiness verdict
    print()
    if report["summary"]["hf_ready"]:
        print(f"  {green('●')} HuggingFace Mode   {green('READY')}  — token configured")
    else:
        print(f"  {red('●')} HuggingFace Mode   {red('NOT READY')}  — no valid HF token")
        print(dim("    Fix: add hf_token to config.json  or  run --fix wizard"))

    # ── Offline section ───────────────────────────────────────────────────────
    print()
    print(cyan("  ── Offline (Local Qwen) ──────────────────────────────────"))

    # Deps
    r = report["offline_deps"]
    _status_line("Python Deps", r["ok"], r["message"])
    for pkg, status in r.get("details", {}).items():
        installed = "NOT INSTALLED" not in status
        icon = green("[OK]") if installed else red("[X] ")
        print(f"          {icon}  {pkg:<15} {dim(status)}")

    # Models
    print()
    r = report["offline_models"]
    print(f"  {dim('Models cache:')}  {dim(r['cache_dir'])}")
    any_ready = False
    for model_name, info in r.get("models", {}).items():
        status = info.get("status", "?")
        if status == "READY":
            size = info.get("size_gb", "?")
            q    = info.get("quality", "")
            _status_line(model_name, True,  f"{size} GB on disk  [{q}]")
            any_ready = True
        elif status == "NOT DOWNLOADED":
            size = info.get("size", "?")
            ram  = info.get("ram", "?")
            _status_line(model_name, None, f"Not downloaded  ({size}, needs {ram})")
        elif "INCOMPLETE" in status:
            _status_line(model_name, False, "Download incomplete — re-run offline mode to finish")
        else:
            _status_line(model_name, False, status)

    print()
    if report["summary"]["offline_ready"]:
        print(f"  {green('●')} Offline Mode   {green('READY')}  — at least one model available")
    elif r["ok"] and not report["offline_deps"]["ok"]:
        print(f"  {red('●')} Offline Mode   {red('NOT READY')}  — missing Python packages")
        print(dim("    Fix: python ritmo/support.py --fix  (installs ONNX Runtime stack)"))
    else:
        print(f"  {yellow('●')} Offline Mode   {yellow('NOT READY')}  — no models downloaded yet")
        print(dim("    Fix: run ritmocli.py → Mode 2 to download a model"))

    # ── Backend ───────────────────────────────────────────────────────────────
    print()
    print(cyan("  ── REKOV Backend ────────────────────────────────────────"))
    r = report["backend"]
    _status_line("Backend :4040", r["ok"], r["message"])
    if not r["ok"]:
        print(dim("    Start: python interface.py → Mode 1"))

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print(dim("  " + "─" * 52))
    print()
    s = report["summary"]
    hf_icon  = green("READY") if s["hf_ready"]      else red("NOT READY")
    off_icon = green("READY") if s["offline_ready"]  else yellow("NOT READY")
    be_icon  = green("READY") if report["backend"]["ok"] else yellow("OFFLINE")

    print(f"  {'Mode':<22}  {'Status'}")
    print(f"  {'─'*22}  {'─'*14}")
    print(f"  {'HuggingFace (cloud)':<22}  {hf_icon}")
    print(f"  {'Offline (local Qwen)':<22}  {off_icon}")
    print(f"  {'Backend API (:4040)':<22}  {be_icon}")
    print()

    if not s["any_ready"]:
        print(red("  Nothing is configured. Run --fix to set up."))
    else:
        print(dim("  Run: python rekov/ritmocli.py  to start chatting."))
    print()


def _status_line(label: str, ok, message: str):
    """Print a single status line with colored icon."""
    label = f"{label:<24}"
    if ok is True:
        print(f"  {green('[OK] ')} {label} {dim(message)}")
    elif ok is False:
        print(f"  {red('[ERR]')} {label} {yellow(message)}")
    else:
        print(f"  {yellow('[---]')} {label} {dim(message)}")


# ═══════════════════════════════════════════════════════════════════════════════
#  INLINE STATUS BAR  (called by ritmocli.py at startup)
# ═══════════════════════════════════════════════════════════════════════════════

def inline_status() -> dict:
    """
    Quick silent check — no HF API ping, no printing.
    Returns summary dict for ritmocli.py to display as a status bar.
    """
    cfg_data   = check_config_file().get("data", {})
    hf_token   = check_hf_token(cfg_data)
    deps       = check_offline_deps()
    models     = check_offline_models()
    backend    = check_backend()

    return {
        "hf_token_ok":    hf_token["ok"],
        "hf_token_masked": hf_token.get("token", ""),
        "offline_deps_ok": deps["ok"],
        "offline_model_ready": models["ok"],
        "offline_model_count": sum(
            1 for m in models["models"].values()
            if m.get("status") == "READY"
        ),
        "backend_ok":     backend["ok"],
        "hf_ready":       hf_token["ok"],
        "offline_ready":  deps["ok"] and models["ok"],
        "config_ok":      check_config_file()["ok"],
    }


def print_inline_status():
    """Print a compact one-line status bar for ritmocli.py header."""
    s = inline_status()

    hf_icon  = green("HF [OK]")      if s["hf_ready"]      else red("HF [X]")
    off_icon = green(f"Offline [OK] ({s['offline_model_count']} model)") \
               if s["offline_ready"]  else yellow("Offline [X]")

    parts = [hf_icon, off_icon]
    print(f"  {dim('Status:')}  {'  |  '.join(parts)}")

    # Show hints for what's broken
    hints = []
    if not s["hf_token_ok"]:
        hints.append(red("  ! No HF token → add hf_token to config.json"))
    if not s["offline_deps_ok"]:
        hints.append(yellow("  ! ONNX stack not installed → run: pip install optimum[onnxruntime] onnxruntime transformers"))
    elif not s["offline_model_ready"]:
        hints.append(yellow("  ! No local model → choose Offline Mode to download one"))
    for h in hints:
        print(h)

    return s


# ═══════════════════════════════════════════════════════════════════════════════
#  FIX WIZARD
# ═══════════════════════════════════════════════════════════════════════════════

def run_fix_wizard():
    """Interactive wizard to fix common configuration problems."""
    print()
    print(teal("  ╔══════════════════════════════════════════════════════╗"))
    print(teal("  ║") + white("   RITMO Support — Fix Wizard                          ") + teal("║"))
    print(teal("  ╚══════════════════════════════════════════════════════╝"))
    print()

    report = run_full_check(verbose=False)

    fixes_applied = 0

    # ── Fix 1: HF token ───────────────────────────────────────────────────────
    if not report["summary"]["hf_ready"]:
        print(yellow("  [FIX 1] HuggingFace token not configured."))
        print(dim("  Get your token at: https://huggingface.co/settings/tokens"))
        print()
        token = input(cyan("  Paste your HF token (hf_...): ")).strip()
        if token.startswith("hf_") and len(token) > 10:
            _save_hf_token(token)
            print(green("  Token saved to config.json"))
            fixes_applied += 1
        elif token:
            print(red("  Invalid token format. Skipping."))
        else:
            print(dim("  Skipped."))
        print()

    # ── Fix 2: Missing ONNX Runtime stack ─────────────────────────────────────
    if not report["offline_deps"]["ok"]:
        print(yellow("  [FIX 2] ONNX Runtime stack not installed."))
        print(dim("  Will install: optimum[onnxruntime] + onnxruntime + transformers (no PyTorch)"))
        do_install = input(cyan("  Install now? [Y/n]: ")).strip().lower()
        if do_install != "n":
            _install_offline_deps()
            fixes_applied += 1
        else:
            print(dim("  Skipped."))
        print()

    # ── Fix 3: No models downloaded ───────────────────────────────────────────
    if report["offline_deps"]["ok"] and not report["offline_models"]["ok"]:
        print(yellow("  [FIX 3] No local Qwen model downloaded yet."))
        print()
        for i, (name, info) in enumerate(OFFLINE_MODELS.items(), 1):
            print(f"    {cyan(str(i))}  {name}  {dim(info['size'])}  {dim(info['quality'])}")
        print()
        choice = input(cyan("  Download a model? [1/2/3/n]: ")).strip().lower()
        if choice in ("1", "2", "3"):
            model_name, model_info = list(OFFLINE_MODELS.items())[int(choice) - 1]
            _download_model(model_info["hf_id"], model_name)
            fixes_applied += 1
        else:
            print(dim("  Skipped."))
        print()

    # ── Result ────────────────────────────────────────────────────────────────
    if fixes_applied == 0:
        cfg_ok  = report["config"]["ok"]
        hf_ok   = report["summary"]["hf_ready"]
        off_ok  = report["summary"]["offline_ready"]
        if cfg_ok and (hf_ok or off_ok):
            print(green("  Everything looks good! No fixes needed."))
        else:
            print(dim("  No fixes applied."))
    else:
        print(green(f"  Applied {fixes_applied} fix(es). Re-run to verify."))
    print()


def _save_hf_token(token: str):
    """Write HF token into config.json."""
    data = {}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    data["hf_token"] = token
    data["HF_TOKEN"]  = token
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _install_offline_deps():
    """pip install ONNX Runtime stack (no PyTorch needed)."""
    import subprocess
    pkgs = [
        ("optimum[onnxruntime]>=1.18.0", "optimum[onnxruntime]"),
        ("onnxruntime>=1.18.0",           "onnxruntime"),
        ("transformers>=4.45.0",          "transformers"),
    ]
    for pkg, label in pkgs:
        print(dim(f"  Installing {label}..."))
        subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
            check=False
        )
    print(green("  ONNX Runtime stack installed."))


def _download_model(hf_id: str, model_name: str):
    """
    Download + auto-export Qwen model to ONNX format via optimum.
    Saves to base/models/<model_name>-onnx/  (no PyTorch files, pure ONNX).
    """
    try:
        from optimum.onnxruntime import ORTModelForCausalLM
        from transformers import AutoTokenizer
    except ImportError:
        print(red("  optimum[onnxruntime] not installed. Run fix first."))
        return

    onnx_path = MODELS_DIR / (model_name + "-onnx")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    print(dim(f"  Downloading {hf_id} and exporting to ONNX..."))
    print(dim("  This may take several minutes on first run."))
    print(dim("  ONNX = ~50% smaller, 2-3x faster inference vs PyTorch."))
    print()
    try:
        tokenizer = AutoTokenizer.from_pretrained(hf_id, trust_remote_code=True)
        model = ORTModelForCausalLM.from_pretrained(
            hf_id,
            export=True,
            trust_remote_code=True,
            provider="CPUExecutionProvider",
        )
        tokenizer.save_pretrained(str(onnx_path))
        model.save_pretrained(str(onnx_path))
        print(green(f"  ONNX model saved to base/models/{model_name}-onnx"))
    except Exception as e:
        print(red(f"  Download/export failed: {e}"))


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="RITMO Support — Configuration checker and fix wizard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python rekov/ritmosupport.py              # full status report
  python rekov/ritmosupport.py --fix        # interactive fix wizard
  python rekov/ritmosupport.py --json       # JSON output (for scripts)
  python rekov/ritmosupport.py --no-ping    # skip slow HF API ping
        """
    )
    parser.add_argument("--fix",     action="store_true", help="Run interactive fix wizard")
    parser.add_argument("--json",    action="store_true", help="Output JSON (no colors)")
    parser.add_argument("--no-ping", action="store_true", help="Skip HF API ping (faster)")
    args = parser.parse_args()

    if args.fix:
        run_fix_wizard()
        return

    if args.json:
        report = run_full_check(verbose=False, ping_hf=not args.no_ping)
        # Make JSON-serialisable
        print(json.dumps(report, indent=2, default=str))
        return

    # Default: full verbose report
    run_full_check(verbose=True, ping_hf=not args.no_ping)


if __name__ == "__main__":
    main()
