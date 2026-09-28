"""
REKOV — Root Entry Point
========================
Delegates immediately to interface.py (the Interface Manager).

Usage:
    python main.py        ← same as: python interface.py
    python interface.py   ← preferred entry point

The actual backend launcher lives in:   rekov/launcher.py
The actual FastAPI app entry point is:  rekov/main.py
"""

import os
import sys

# Ensure the project root is on the path
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

if __name__ == "__main__":
    # Hand off to interface.py (which shows the full REKOV banner + credits)
    from interface import main
    main()
