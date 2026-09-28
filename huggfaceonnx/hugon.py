"""
huggfaceonnx/hugon.py
======================
HuggingFace Model Info + Hub Utility (hugon = HuggingFace Model ON-demand).

Provides:
  get_model_info(model_id)      — fetch model metadata from HF Hub API
  list_cached_models()          — list locally cached ONNX models
  download_status(model_id)     — check if model is cached or needs download
  estimate_download_size(model_id) — estimate download size from HF API

Used by: ritmo/support.py, ritmo/cli.py (model selection screen)
No extra deps needed — uses stdlib urllib only.
"""

import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

ROOT_DIR   = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT_DIR / "base" / "models"

# ── HF Hub API base ───────────────────────────────────────────────────────────
HF_API_BASE = "https://huggingface.co/api"


# ═══════════════════════════════════════════════════════════════════════════════
#  Model metadata
# ═══════════════════════════════════════════════════════════════════════════════

def get_model_info(model_id: str, hf_token: str = "") -> dict:
    """
    Fetch model card metadata from the HuggingFace Hub API.

    Returns:
        {
            "id":           str,
            "ok":           bool,
            "downloads":    int,
            "likes":        int,
            "tags":         list[str],
            "pipeline_tag": str,
            "last_modified": str,
            "siblings":     list (files in the repo),
            "error":        str | None,
        }
    """
    result: dict = {
        "id":            model_id,
        "ok":            False,
        "downloads":     0,
        "likes":         0,
        "tags":          [],
        "pipeline_tag":  "",
        "last_modified": "",
        "siblings":      [],
        "error":         None,
    }
    url = f"{HF_API_BASE}/models/{model_id}"
    headers = {"User-Agent": "HugOn/1.0"}
    if hf_token:
        headers["Authorization"] = f"Bearer {hf_token}"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
            result["ok"]            = True
            result["downloads"]     = data.get("downloads", 0)
            result["likes"]         = data.get("likes", 0)
            result["tags"]          = data.get("tags", [])
            result["pipeline_tag"]  = data.get("pipeline_tag", "")
            result["last_modified"] = data.get("lastModified", "")
            result["siblings"]      = [
                {"name": s.get("rfilename", ""), "size": s.get("size", 0)}
                for s in data.get("siblings", [])
            ]
    except urllib.error.HTTPError as e:
        result["error"] = f"HTTP {e.code}"
    except Exception as ex:
        result["error"] = str(ex)

    return result


def estimate_download_size(model_id: str, hf_token: str = "") -> dict:
    """
    Estimate total download size by summing sibling file sizes from HF Hub.

    Returns:
        {"model_id": str, "size_bytes": int, "size_gb": float, "file_count": int}
    """
    info = get_model_info(model_id, hf_token)
    if not info["ok"]:
        return {"model_id": model_id, "size_bytes": 0, "size_gb": 0.0,
                "file_count": 0, "error": info["error"]}

    total = sum(f.get("size", 0) for f in info["siblings"])
    return {
        "model_id":   model_id,
        "size_bytes": total,
        "size_gb":    round(total / (1024 ** 3), 2),
        "file_count": len(info["siblings"]),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  Local cache inspection
# ═══════════════════════════════════════════════════════════════════════════════

def list_cached_models(models_dir: Optional[Path] = None) -> list:
    """
    Return a list of dicts for every ONNX-cached model in base/models/.

    Each entry:
        {"name": str, "path": str, "size_gb": float, "ready": bool}
    """
    if models_dir is None:
        models_dir = MODELS_DIR
    models_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for d in sorted(models_dir.iterdir()):
        if not d.is_dir():
            continue
        try:
            total    = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            has_onnx = any(d.rglob("*.onnx"))
            has_cfg  = (d / "config.json").exists()
            results.append({
                "name":    d.name,
                "path":    str(d),
                "size_gb": round(total / (1024 ** 3), 2),
                "ready":   has_onnx and has_cfg,
            })
        except Exception as e:
            results.append({"name": d.name, "path": str(d), "error": str(e)})

    return results


def download_status(model_id: str, models_dir: Optional[Path] = None) -> dict:
    """
    Check whether a model is already cached locally in ONNX format.

    Returns:
        {
            "model_id":  str,
            "cached":    bool,
            "ready":     bool,
            "path":      str | None,
            "size_gb":   float,
        }
    """
    if models_dir is None:
        models_dir = MODELS_DIR

    short_name = model_id.split("/")[-1]
    onnx_path  = models_dir / (short_name + "-onnx")

    if not onnx_path.exists():
        return {
            "model_id": model_id,
            "cached":   False,
            "ready":    False,
            "path":     None,
            "size_gb":  0.0,
        }

    try:
        total    = sum(f.stat().st_size for f in onnx_path.rglob("*") if f.is_file())
        has_onnx = any(onnx_path.rglob("*.onnx"))
        has_cfg  = (onnx_path / "config.json").exists()
        return {
            "model_id": model_id,
            "cached":   True,
            "ready":    has_onnx and has_cfg,
            "path":     str(onnx_path),
            "size_gb":  round(total / (1024 ** 3), 2),
        }
    except Exception as e:
        return {
            "model_id": model_id,
            "cached":   True,
            "ready":    False,
            "path":     str(onnx_path),
            "size_gb":  0.0,
            "error":    str(e),
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI  (python huggfaceonnx/hugon.py <model_id>)
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys as _sys

    if len(_sys.argv) < 2:
        print("Usage: python huggfaceonnx/hugon.py <model_id>")
        print("       python huggfaceonnx/hugon.py --list-cached")
        _sys.exit(0)

    if _sys.argv[1] == "--list-cached":
        cached = list_cached_models()
        if not cached:
            print("  No ONNX models cached in base/models/")
        else:
            print(f"  {'Model':<35}  {'Size':>8}  {'Ready'}")
            print("  " + "-" * 55)
            for m in cached:
                ready = "YES" if m.get("ready") else "NO"
                print(f"  {m['name']:<35}  {m.get('size_gb', 0):>6.2f} GB  {ready}")
    else:
        model_id = _sys.argv[1]
        print(f"  Fetching HF metadata for: {model_id}")
        info = get_model_info(model_id)
        if not info["ok"]:
            print(f"  Error: {info['error']}")
        else:
            print(f"  Downloads    : {info['downloads']:,}")
            print(f"  Likes        : {info['likes']}")
            print(f"  Pipeline     : {info['pipeline_tag']}")
            print(f"  Files        : {len(info['siblings'])}")
            print(f"  Last modified: {info['last_modified'][:10]}")

        size = estimate_download_size(model_id)
        print(f"  Est. size    : {size['size_gb']} GB  ({size['file_count']} files)")

        status = download_status(model_id)
        print(f"  Local cache  : {'READY' if status['ready'] else 'NOT CACHED'}")
        if status["cached"]:
            print(f"  Cache path   : {status['path']}")
            print(f"  Cache size   : {status['size_gb']} GB")
