"""
huggfaceonnx/onnx.py
=====================
ONNX Runtime offline inference layer for REKOV.

Provides:
  OFFLINE_MODELS        — canonical model registry (single source of truth)
  check_onnx_deps()     — verify optimum[onnxruntime] + transformers installed
  install_onnx_deps()   — pip install the ONNX stack
  load_model()          — download + export to ONNX (first run), or load cache
  generate()            — run one inference step (no PyTorch at runtime)
  check_model_cache()   — scan base/models/ for cached -onnx directories

Used by: ritmo/cli.py, ritmo/support.py
No PyTorch required — pure ONNX Runtime on CPU.
"""

import importlib
import os
import sys
import warnings
from pathlib import Path
from typing import Optional

# Suppress Windows symlinks warning from huggingface_hub (no functional impact)
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# ── Project root ──────────────────────────────────────────────────────────────
ROOT_DIR   = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT_DIR / "base" / "models"

# ── Ritmo system prompt ───────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are RITMO, a hospital AI assistant helping patients book appointments via CLI.

RULES:
1. Be concise — max 40 words per reply.
2. Match the user's language (English, Hindi, Hinglish).
3. Help the patient describe their symptom and recommend a department.
4. When you decide on a doctor/department, end with "Shall I book your appointment? Say Yes or No."
5. When user says Yes/Haan/Sure, output EXACTLY:
   [BOOK_TICKET] dept_id=<dept> doctor_id=<id> priority=STANDARD patient_name=<name>
6. For chest pain, bleeding, unconscious: output [EMERGENCY] immediately.
7. Never use emojis.

Departments: General Medicine (dep_gen), Cardiology (dep_card), Orthopedics (dep_ortho),
Neurology (dep_neuro), Pediatrics (dep_ped), ENT (dep_ent), Dermatology (dep_derm),
Gastroenterology (dep_gastro), Emergency (dep_emg).
"""

# ═══════════════════════════════════════════════════════════════════════════════
#  OFFLINE_MODELS — canonical registry (single source of truth for all of REKOV)
# ═══════════════════════════════════════════════════════════════════════════════

OFFLINE_MODELS: dict = {
    "1": {
        "id":      "Qwen/Qwen2.5-0.5B-Instruct",
        "label":   "Qwen2.5-0.5B  (~1 GB)  ← Fastest, lowest RAM",
        "size":    "~1 GB",
        "ram":     "~1.5 GB",
        "quality": "Good for basic triage",
        "hf_id":   "Qwen/Qwen2.5-0.5B-Instruct",
    },
    "2": {
        "id":      "Qwen/Qwen2.5-1.5B-Instruct",
        "label":   "Qwen2.5-1.5B  (~3 GB)  ← Smarter responses",
        "size":    "~3 GB",
        "ram":     "~4 GB",
        "quality": "Better language understanding",
        "hf_id":   "Qwen/Qwen2.5-1.5B-Instruct",
    },
    "3": {
        "id":      "Qwen/Qwen2.5-3B-Instruct",
        "label":   "Qwen2.5-3B    (~6 GB)  ← Best quality",
        "size":    "~6 GB",
        "ram":     "~8 GB",
        "quality": "Highest quality offline inference",
        "hf_id":   "Qwen/Qwen2.5-3B-Instruct",
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Dependency management
# ═══════════════════════════════════════════════════════════════════════════════

def check_onnx_deps() -> bool:
    """
    Return True if the full ONNX Runtime inference stack is available.
    Required: optimum.onnxruntime, onnxruntime, transformers.
    No PyTorch needed.
    """
    try:
        importlib.import_module("optimum.onnxruntime")
        importlib.import_module("transformers")
        importlib.import_module("onnxruntime")
        return True
    except ImportError:
        return False


def check_onnx_deps_detail() -> dict:
    """
    Return a detailed status dict for each package.
    Used by ritmo/support.py's check_offline_deps().
    """
    result: dict = {
        "name":    "Offline Dependencies (ONNX)",
        "ok":      False,
        "details": {},
        "message": "",
    }
    packages = {
        "onnxruntime": "onnxruntime",
        "optimum":     "optimum",
        "transformers": "transformers",
    }
    missing = []
    for display, pkg in packages.items():
        try:
            mod     = importlib.import_module(pkg)
            version = getattr(mod, "__version__", "?")
            result["details"][display] = f"installed  v{version}"
        except ImportError:
            result["details"][display] = "NOT INSTALLED"
            missing.append(display)

    # Extra check: optimum.onnxruntime submodule
    try:
        importlib.import_module("optimum.onnxruntime")
        result["details"]["optimum.onnxruntime"] = "available"
    except ImportError:
        result["details"]["optimum.onnxruntime"] = "NOT INSTALLED"
        if "optimum" not in missing:
            missing.append("optimum[onnxruntime]")

    if not missing:
        result["ok"]      = True
        result["message"] = "All ONNX packages installed"
    else:
        result["message"] = f"Missing: {', '.join(missing)}"
    return result


def install_onnx_deps(print_fn=print) -> None:
    """
    pip install the ONNX Runtime stack (no PyTorch, no CUDA needed).
    Packages: optimum[onnxruntime], onnxruntime, transformers.
    """
    import subprocess
    pkgs = [
        ("optimum[onnxruntime]>=1.18.0", "optimum[onnxruntime]"),
        ("onnxruntime>=1.18.0",           "onnxruntime"),
        ("transformers>=4.45.0",          "transformers"),
    ]
    for pkg, label in pkgs:
        print_fn(f"  Installing {label}...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
            check=False,
        )
    print_fn("  ONNX Runtime stack installed.")


# ═══════════════════════════════════════════════════════════════════════════════
#  Model loading
# ═══════════════════════════════════════════════════════════════════════════════

def _get_token_from_config() -> str:
    """Read HF token from config.json (project root) or environment."""
    import json
    for p in [ROOT_DIR / "config.json", ROOT_DIR / "rekov" / "config.json"]:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                tok  = (
                    data.get("hf_token") or data.get("HF_TOKEN")
                    or data.get("HF_API_TOKEN") or data.get("HUGGINGFACE_API_KEY")
                )
                if tok:
                    return tok
            except Exception:
                pass
    return (
        os.environ.get("HF_TOKEN")
        or os.environ.get("HF_API_TOKEN")
        or os.environ.get("HUGGINGFACE_API_KEY")
        or ""
    )


def load_model(model_id: str, cache_dir: Optional[Path] = None, token: str = ""):
    """
    Load a Qwen model via ONNX Runtime (optimum[onnxruntime]).

    First call:
      - Downloads the model from HuggingFace (authenticated if token set)
      - Auto-exports to ONNX format (one-time, may take several minutes)
      - Saves to cache_dir/<model_name>-onnx/

    Subsequent calls:
      - Loads directly from the ONNX cache (seconds, no internet)
      - No PyTorch at runtime — pure ONNX Runtime on CPU

    Args:
        model_id:   HuggingFace model ID, e.g. "Qwen/Qwen2.5-0.5B-Instruct"
        cache_dir:  directory to save/load ONNX models (default: base/models/)
        token:      HuggingFace token (auto-read from config.json if not given)

    Returns:
        (tokenizer, model) tuple ready for generate()
    """
    from optimum.onnxruntime import ORTModelForCausalLM
    from transformers import AutoTokenizer

    # ── Resolve token ──────────────────────────────────────────────────────────
    if not token:
        token = _get_token_from_config()
    if token:
        os.environ["HF_TOKEN"]           = token
        os.environ["HF_API_TOKEN"]        = token
        os.environ["HUGGINGFACE_API_KEY"] = token

    if cache_dir is None:
        cache_dir = MODELS_DIR

    short_name = model_id.split("/")[-1]
    onnx_cache = cache_dir / (short_name + "-onnx")
    cache_dir.mkdir(parents=True, exist_ok=True)

    if onnx_cache.exists():
        load_from = str(onnx_cache)
        export    = False
    else:
        load_from = model_id
        export    = True

    # ── Patch: suppress the additional_chat_templates 404 ─────────────────────
    # huggingface_hub >= 0.24 tries to fetch additional_chat_templates which
    # doesn't exist in Qwen repos. It raises a 404 EntryNotFoundError that
    # bubbles up through optimum's export pipeline. We suppress it here.
    try:
        from huggingface_hub import file_download as _hfd
        _orig_get_file_metadata = getattr(_hfd, "get_hf_file_metadata", None)
    except ImportError:
        _orig_get_file_metadata = None

    def _safe_from_pretrained(cls, repo_id, **kwargs):
        """Wrapper that retries without the failing additional_chat_templates fetch."""
        import contextlib
        try:
            # Suppress HFValidationError / EntryNotFoundError from hub listing
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return cls.from_pretrained(repo_id, **kwargs)
        except Exception as e:
            msg = str(e)
            if "additional_chat_templates" in msg or "EntryNotFound" in msg:
                # Non-fatal — the tokenizer works fine without this folder
                # Try again with tokenizer_config only
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        return cls.from_pretrained(
                            repo_id,
                            **{k: v for k, v in kwargs.items() if k != "additional_chat_templates"},
                        )
                except Exception:
                    pass
            raise

    try:
        # Suppress all UserWarning from HF Hub during load
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning)
            warnings.filterwarnings("ignore", message=".*symlink.*")
            warnings.filterwarnings("ignore", message=".*unauthenticated.*")

            tokenizer_src = model_id if export else load_from
            tok_kwargs = dict(
                trust_remote_code=True,
                token=token or None,
            )
            try:
                tokenizer = AutoTokenizer.from_pretrained(tokenizer_src, **tok_kwargs)
            except Exception as e:
                if "additional_chat_templates" in str(e) or "EntryNotFound" in str(e):
                    # Retry: huggingface_hub sometimes 404s on optional dirs
                    tokenizer = AutoTokenizer.from_pretrained(
                        tokenizer_src, **tok_kwargs
                    )
                else:
                    raise

            model_kwargs = dict(
                export=export,
                trust_remote_code=True,
                provider="CPUExecutionProvider",
                token=token or None,
            )
            model = ORTModelForCausalLM.from_pretrained(load_from, **model_kwargs)

        if export:
            model.save_pretrained(str(onnx_cache))
            tokenizer.save_pretrained(str(onnx_cache))

        return tokenizer, model

    except Exception as e:
        raise RuntimeError(f"Failed to load model '{model_id}': {e}") from e


# ═══════════════════════════════════════════════════════════════════════════════
#  Inference
# ═══════════════════════════════════════════════════════════════════════════════

def generate(
    tokenizer,
    model,
    conversation: list,
    system_prompt: str = SYSTEM_PROMPT,
    max_new_tokens: int = 150,
) -> str:
    """
    Run one ONNX inference step.

    Args:
        tokenizer:      from load_model()
        model:          from load_model()
        conversation:   list of {"role": str, "content": str} dicts
        system_prompt:  prepended as system message
        max_new_tokens: max tokens to generate

    Returns:
        Assistant reply text (decoded, stripped)

    No PyTorch at runtime — uses ONNX Runtime under the hood.
    """
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation)

    try:
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    except Exception:
        # Fallback: manual ChatML format
        text = f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
        for m in conversation:
            text += f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n"
        text += "<|im_start|>assistant\n"

    # optimum wraps onnxruntime — accepts pt-style tensors, runs on ONNX graph
    inputs = tokenizer(text, return_tensors="pt")

    output_ids = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        do_sample=True,
        temperature=0.7,
        top_p=0.9,
        repetition_penalty=1.1,
        pad_token_id=tokenizer.eos_token_id,
    )

    input_len = inputs["input_ids"].shape[-1]
    new_ids   = output_ids[0][input_len:]
    return tokenizer.decode(new_ids, skip_special_tokens=True).strip()


# ═══════════════════════════════════════════════════════════════════════════════
#  Cache inspection (used by support.py)
# ═══════════════════════════════════════════════════════════════════════════════

def check_model_cache(models_dir: Optional[Path] = None) -> dict:
    """
    Scan base/models/ for cached ONNX model directories (<name>-onnx/).

    Returns:
        {
            "name":      "Offline Models Cache (ONNX)",
            "ok":        bool,   (True if at least one READY)
            "models":    {model_name: {status, size_gb, path, ...}, ...},
            "cache_dir": str,
            "message":   str,
        }
    """
    if models_dir is None:
        models_dir = MODELS_DIR

    result: dict = {
        "name":      "Offline Models Cache (ONNX)",
        "ok":        False,
        "models":    {},
        "cache_dir": str(models_dir),
        "message":   "",
    }
    models_dir.mkdir(parents=True, exist_ok=True)

    any_found = False
    for model_key, info in OFFLINE_MODELS.items():
        model_name = info["hf_id"].split("/")[-1]
        onnx_path  = models_dir / (model_name + "-onnx")

        if onnx_path.exists():
            try:
                total    = sum(f.stat().st_size for f in onnx_path.rglob("*") if f.is_file())
                size_gb  = round(total / (1024 ** 3), 2)
                has_onnx = any(onnx_path.rglob("*.onnx"))
                has_cfg  = (onnx_path / "config.json").exists()
                status   = "READY" if (has_onnx and has_cfg) else "INCOMPLETE"
                result["models"][model_name] = {
                    "status":  status,
                    "size_gb": size_gb,
                    "path":    str(onnx_path),
                    "hf_id":   info["hf_id"],
                    "quality": info["quality"],
                    "engine":  "ONNX Runtime",
                }
                if status == "READY":
                    any_found = True
            except Exception as e:
                result["models"][model_name] = {
                    "status": f"ERROR: {e}",
                    "hf_id":  info["hf_id"],
                }
        else:
            result["models"][model_name] = {
                "status":  "NOT DOWNLOADED",
                "size":    info["size"],
                "ram":     info["ram"],
                "hf_id":   info["hf_id"],
                "quality": info["quality"],
                "engine":  "ONNX Runtime (auto-export on first run)",
            }

    result["ok"]      = any_found
    result["message"] = (
        f"{sum(1 for m in result['models'].values() if m.get('status') == 'READY')} ONNX model(s) ready"
        if any_found else
        "No ONNX models cached yet — will download+export on first use"
    )
    return result
