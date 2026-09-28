"""
awake/__init__.py
==================
REKOV Awake System — keeps Supabase active and Render from sleeping.

Exports:
  AwakeKeeper   — main engine (start/stop keep-alive threads)
  AwakeStats    — live stats tracker
  get_stats()   — snapshot of current stats
"""

from .keeper import AwakeKeeper
from .stats  import AwakeStats, get_stats

__all__ = ["AwakeKeeper", "AwakeStats", "get_stats"]
__version__ = "1.0.0"
