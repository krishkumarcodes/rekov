"""
huggfaceonnx/__init__.py
========================
Shared HuggingFace API + ONNX Runtime layer for REKOV.

Used by:
  ritmo/cli.py      — RITMO terminal CLI (HF mode + Offline mode)
  ritmo/support.py  — Configuration checker + fix wizard

Modules:
  hfmanager  — HuggingFace API calls (chat, health, model ping, whoami)
  onnx       — ONNX offline inference (check deps, load model, generate)
"""

from pathlib import Path

ROOT_DIR    = Path(__file__).resolve().parent.parent
MODELS_DIR  = ROOT_DIR / "base" / "models"

__version__ = "1.0.0"
__all__     = ["hfmanager", "onnx"]
