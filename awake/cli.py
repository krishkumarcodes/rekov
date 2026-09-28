"""
awake/cli.py
=============
REKOV Awake System — rich terminal CLI.

Shows live stats: uptime, pings, packets sent, last ping times and latencies.
Refreshes every 10 seconds. Press Ctrl+C to stop.

Usage:
    python awake/cli.py
    python awake/cli.py --interval 300   (custom ping interval in seconds)
    python awake/cli.py --once           (print stats snapshot and exit)
    python awake/cli.py --json           (machine-readable stats to stdout)
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from awake.keeper import AwakeKeeper
from awake.stats  import get_stats, get_shared_stats

# ── REKOV credits ─────────────────────────────────────────────────────────────
try:
    from rekov_credits import print_rekov_credits as _print_rekov_credits
    _HAS_CREDITS = True
except ImportError:
    _HAS_CREDITS = False
    def _print_rekov_credits(**_kw): pass

# ── ANSI ──────────────────────────────────────────────────────────────────────
RESET   = "\x1b[0m"
BOLD    = "\x1b[1m"
DIM     = "\x1b[2m"
TEAL    = "\x1b[38;5;43m"
GREEN   = "\x1b[32;1m"
YELLOW  = "\x1b[33;1m"
RED     = "\x1b[31;1m"
CYAN    = "\x1b[36;1m"
WHITE   = "\x1b[97;1m"
MAGENTA = "\x1b[35;1m"
BLUE    = "\x1b[34;1m"

def _c(code, t): return f"{code}{t}{RESET}"
def green(t):    return _c(GREEN,   t)
def red(t):      return _c(RED,     t)
def yellow(t):   return _c(YELLOW,  t)
def cyan(t):     return _c(CYAN,    t)
def teal(t):     return _c(TEAL,    t)
def dim(t):      return _c(DIM,     t)
def white(t):    return _c(WHITE,   t)
def bold(t):     return _c(BOLD,    t)
def magenta(t):  return _c(MAGENTA, t)


# ═══════════════════════════════════════════════════════════════════════════════
#  Display
# ═══════════════════════════════════════════════════════════════════════════════

def _clear():
    os.system("cls" if sys.platform == "win32" else "clear")


def _status_icon(success: int, total: int) -> str:
    if total == 0:
        return yellow("--")
    rate = success / total
    if rate >= 0.9:
        return green("ONLINE")
    if rate >= 0.5:
        return yellow("DEGRADED")
    return red("FAILING")


def _bar(success: int, total: int, width: int = 20) -> str:
    if total == 0:
        return dim("[" + "-" * width + "]")
    filled = int((success / total) * width)
    bar    = green("#" * filled) + dim("-" * (width - filled))
    return f"[{bar}]"


def _render_dashboard(s: dict, render_url: str, supabase_url: str):
    _clear()

    # Header
    _print_rekov_credits(compact=True, show_contributors=False)
    print()
    print(teal("  ╔══════════════════════════════════════════════════════╗"))
    print(teal("  ║") + white("   REKOV  AWAKE  SYSTEM  —  Live Monitor              ") + teal("║"))
    print(teal("  ╚══════════════════════════════════════════════════════╝"))
    print()

    # Uptime + total packets
    print(f"  {white('Uptime')}        {cyan(s['uptime_human'])}")
    print(f"  {white('Started')}       {dim(s['started_at'][:19].replace('T', ' '))} UTC")
    print(f"  {white('Total Packets')} {bold(str(s['total_packets']))}")
    print()
    print(dim("  " + "─" * 52))
    print()

    # Supabase
    sb = s["supabase"]
    sb_status = _status_icon(sb["success"], sb["total"])
    print(f"  {teal('SUPABASE')}  {sb_status}")
    print(f"  {dim('URL:')}      {dim(supabase_url[:50] + '...' if len(supabase_url) > 50 else supabase_url)}")
    print(f"  {white('Pings:')}    {sb['total']}  "
          f"{green(str(sb['success'])) + ' ok'}  "
          f"{(red(str(sb['fail'])) + ' fail') if sb['fail'] else dim('0 fail')}")
    print(f"  Health     {_bar(sb['success'], sb['total'])}")
    if sb["last_ok"]:
        ts  = sb["last_ok"][:19].replace("T", " ")
        ms  = sb.get("last_ms", "?")
        print(f"  {dim('Last OK:')}   {green(ts)} UTC  {dim(str(ms) + 'ms')}")
    if sb["last_err"]:
        print(f"  {dim('Last ERR:')}  {red(sb['last_err'][:60])}")
    print()

    # Render
    rd = s["render"]
    rd_status = _status_icon(rd["success"], rd["total"])
    print(f"  {magenta('RENDER')}    {rd_status}")
    print(f"  {dim('URL:')}      {dim(render_url[:50] + '...' if len(render_url) > 50 else render_url)}")
    print(f"  {white('Pings:')}    {rd['total']}  "
          f"{green(str(rd['success'])) + ' ok'}  "
          f"{(red(str(rd['fail'])) + ' fail') if rd['fail'] else dim('0 fail')}")
    print(f"  Health     {_bar(rd['success'], rd['total'])}")
    if rd["last_ok"]:
        ts  = rd["last_ok"][:19].replace("T", " ")
        ms  = rd.get("last_ms", "?")
        print(f"  {dim('Last OK:')}   {green(ts)} UTC  {dim(str(ms) + 'ms')}")
    if rd["last_err"]:
        print(f"  {dim('Last ERR:')}  {red(rd['last_err'][:60])}")
    print()

    # Footer watermark
    print(dim("  " + "─" * 52))
    print()
    print(f"  {dim('by')} {white('pheonix14')}  {dim('·')}  "
          f"{dim('github.com/pheonix14/rekov')}  {dim('·')}  "
          f"{dim('Ctrl+C to stop')}")
    print()


# ═══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="REKOV Awake System CLI — keep Supabase + Render alive",
    )
    parser.add_argument("--interval", type=int, default=300,
                        help="Ping interval in seconds (default: 300)")
    parser.add_argument("--once",     action="store_true",
                        help="Print stats snapshot once and exit")
    parser.add_argument("--json",     action="store_true",
                        help="Output machine-readable JSON stats and exit")
    args = parser.parse_args()

    keeper = AwakeKeeper(interval_s=args.interval, verbose=False)

    if args.once or args.json:
        # Run one ping cycle then exit
        keeper.start()
        time.sleep(2)  # let first pings fire
        s = get_stats()
        if args.json:
            print(json.dumps(s, indent=2))
        else:
            print(json.dumps(s, indent=2))
        keeper.stop()
        return

    # Live dashboard mode
    keeper.start()
    supabase_url = keeper.supabase_url
    render_url   = keeper.render_url

    try:
        while True:
            s = get_stats()
            _render_dashboard(s, render_url, supabase_url)
            time.sleep(10)   # refresh display every 10s
    except KeyboardInterrupt:
        print()
        print(yellow("  Awake system stopped."))
        keeper.stop()


if __name__ == "__main__":
    main()
