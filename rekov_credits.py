"""
rekov_credits.py
================
REKOV startup banner + live contributor credits.

Call print_rekov_credits() at the top of any REKOV entry point.
Contributors are fetched live from GitHub; falls back to hardcoded list
if the API is unreachable (offline / rate-limited / slow).
"""

import sys
import json
import urllib.request
import urllib.error
from typing import Optional

# ── GitHub repo ───────────────────────────────────────────────────────────────
_GITHUB_REPO = "pheonix14/rekov"
_GITHUB_API  = f"https://api.github.com/repos/{_GITHUB_REPO}/contributors"

# ── Hardcoded fallback (shown when GitHub API is unavailable) ─────────────────
_HARDCODED_CONTRIBUTORS = [
    {
        "login":  "pheonix14",
        "role":   "Lead — Backend Architecture, AI Integration & RITMO Engine",
        "url":    "https://github.com/pheonix14",
    },
]

# ── ANSI ──────────────────────────────────────────────────────────────────────
class _A:
    RESET    = "\x1b[0m"
    BOLD     = "\x1b[1m"
    DIM      = "\x1b[2m"
    TEAL     = "\x1b[38;5;43m"
    CYAN     = "\x1b[36;1m"
    GREEN    = "\x1b[32;1m"
    YELLOW   = "\x1b[33;1m"
    WHITE    = "\x1b[97;1m"
    MAGENTA  = "\x1b[35;1m"
    BLUE     = "\x1b[34;1m"

def _t(code, text): return f"{code}{text}{_A.RESET}"

# ── ASCII art ─────────────────────────────────────────────────────────────────
REKOV_ASCII = r"""
 ██████╗ ███████╗██╗  ██╗ ██████╗ ██╗   ██╗
 ██╔══██╗██╔════╝██║ ██╔╝██╔═══██╗██║   ██║
 ██████╔╝█████╗  █████╔╝ ██║   ██║██║   ██║
 ██╔══██╗██╔══╝  ██╔═██╗ ██║   ██║╚██╗ ██╔╝
 ██║  ██║███████╗██║  ██╗╚██████╔╝ ╚████╔╝
 ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝ ╚═════╝   ╚═══╝"""


# ═══════════════════════════════════════════════════════════════════════════════
#  Contributor fetch
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_contributors(timeout: int = 3) -> list:
    """
    Fetch contributor list from GitHub API.

    Returns list of {"login": str, "contributions": int, "html_url": str}.
    Falls back to _HARDCODED_CONTRIBUTORS silently if API is unreachable.
    """
    try:
        req = urllib.request.Request(
            _GITHUB_API,
            headers={
                "User-Agent":  "REKOV-Credits/1.0",
                "Accept":      "application/vnd.github.v3+json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
            if isinstance(data, list) and data:
                return [
                    {
                        "login":         c.get("login", ""),
                        "contributions": c.get("contributions", 0),
                        "html_url":      c.get("html_url", ""),
                    }
                    for c in data
                    if c.get("type") != "Bot"
                ]
    except Exception:
        pass

    # Fallback — show only pheonix14 (as per project owner's preference)
    return [
        {
            "login":         h["login"],
            "contributions": None,
            "html_url":      h.get("url", f"https://github.com/{h['login']}"),
            "_role":         h.get("role", ""),
        }
        for h in _HARDCODED_CONTRIBUTORS
    ]


# ═══════════════════════════════════════════════════════════════════════════════
#  Banner printer
# ═══════════════════════════════════════════════════════════════════════════════

def print_rekov_credits(
    show_contributors: bool = True,
    fetch_live: bool = True,
    compact: bool = False,
) -> None:
    """
    Print the REKOV ASCII banner + project credits to stdout.

    Args:
        show_contributors: if False, skip the contributors section
        fetch_live:        if False, use hardcoded fallback only (faster startup)
        compact:           if True, print a single-line header instead of full art
    """
    # ── Compact mode (used inside sub-banners like RITMO) ─────────────────────
    if compact:
        line = _t(_A.TEAL + _A.BOLD, " REKOV") + "  " + _t(_A.DIM, "by") + " " + _t(_A.WHITE + _A.BOLD, "pheonix14")
        print(f"  {line}")
        return

    # ── Full ASCII banner ──────────────────────────────────────────────────────
    print()
    for line in REKOV_ASCII.splitlines():
        print(_t(_A.TEAL, line))
    print()
    print(
        "  " +
        _t(_A.DIM, "Hospital AI System  ·  ") +
        _t(_A.WHITE + _A.BOLD, "by ") +
        _t(_A.CYAN + _A.BOLD, "pheonix14") +
        _t(_A.DIM, "  ·  github.com/pheonix14/rekov")
    )
    print()
    print(
        "  " +
        _t(_A.DIM, "─" * 50)
    )
    print()

    if not show_contributors:
        return

    # ── Contributors ──────────────────────────────────────────────────────────
    contribs = fetch_contributors(timeout=3) if fetch_live else [
        {"login": h["login"], "contributions": None,
         "html_url": f"https://github.com/{h['login']}", "_role": h.get("role", "")}
        for h in _HARDCODED_CONTRIBUTORS
    ]

    print(_t(_A.WHITE + _A.BOLD, "  Contributors"))
    print()

    for c in contribs:
        login = c.get("login", "")
        contr = c.get("contributions")
        url   = c.get("html_url", f"https://github.com/{login}")
        role  = c.get("_role", "")

        contrib_str = (
            _t(_A.DIM, f"  {contr} commits") if contr is not None else ""
        )
        role_str = (
            _t(_A.DIM, f"  ·  {role}") if role else ""
        )

        # pheonix14 always gets bold + star treatment
        if login == "pheonix14":
            print(
                f"  {_t(_A.YELLOW, '*')} "
                f"{_t(_A.WHITE + _A.BOLD, login)}"
                f"{contrib_str}"
                f"{role_str}"
            )
        else:
            print(
                f"  {_t(_A.DIM, '·')} "
                f"{_t(_A.CYAN, login)}"
                f"{contrib_str}"
                f"{role_str}"
            )

    print()
    print("  " + _t(_A.DIM, "─" * 50))
    print()


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI entry point (python rekov_credits.py)
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print_rekov_credits()
