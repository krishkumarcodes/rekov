"""
base/supabase/__init__.py
==========================
REKOV — Supabase layer package.

Exports:
  sbcheck         — run_full_check() for one-shot diagnostics
  SBLogger        — session logger for all Supabase operations
  get_client()    — returns an authenticated supabase-py client
"""

from .sbcheck import run_full_check, get_client, SBLogger

__all__ = ["run_full_check", "get_client", "SBLogger"]
