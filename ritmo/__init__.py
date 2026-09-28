"""
ritmo/__init__.py
=================
RITMO — Hospital AI Voice Assistant CLI package.

Usage:
    python -m ritmo                 # interactive mode selector
    python -m ritmo --mode hf       # HuggingFace mode
    python -m ritmo --mode offline  # Local Qwen model

Sub-modules:
    ritmo.cli      — main CLI entry point
    ritmo.support  — config checker + fix wizard
"""

from pathlib import Path

RITMO_DIR = Path(__file__).resolve().parent
ROOT_DIR  = RITMO_DIR.parent

__version__ = "1.0.0"
__all__ = ["cli", "support"]
