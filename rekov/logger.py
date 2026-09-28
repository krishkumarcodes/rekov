"""
REKOV System Logger — Rich Terminal Color System

Color Scheme:
  DARK GREEN  = Service is working / healthy / success
  RED         = Service dead / error / failed
  YELLOW      = Unknown / warning / not confirmed
  BLUE        = Update / info / progress / compiling
  GREY        = Debug noise (suppressed in normal use)
"""

import logging
import sys
import os
import io
from datetime import datetime


# ── ANSI Color Codes ──────────────────────────────────────────────────────────
class _C:
    DARK_GREEN   = "\x1b[32;1m"      # Bold dark green  — WORKING
    RED          = "\x1b[31;1m"      # Bold red         — DEAD
    BRIGHT_RED   = "\x1b[91;1m"      # Bright red       — CRITICAL
    YELLOW       = "\x1b[33;1m"      # Bold yellow      — UNKNOWN
    BLUE         = "\x1b[34;1m"      # Bold blue        — UPDATE
    CYAN         = "\x1b[36;20m"     # Cyan             — INFO
    GREY         = "\x1b[38;20m"     # Grey             — DEBUG
    RESET        = "\x1b[0m"


# ── Custom Level Numbers ──────────────────────────────────────────────────────
SUCCESS_LEVEL = 25   # dark green (working)
UPDATE_LEVEL  = 15   # blue (compiling, updates)

logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")
logging.addLevelName(UPDATE_LEVEL,  "UPDATE")

def _success(self, message, *args, **kws):
    if self.isEnabledFor(SUCCESS_LEVEL):
        self._log(SUCCESS_LEVEL, message, args, **kws)

def _update(self, message, *args, **kws):
    if self.isEnabledFor(UPDATE_LEVEL):
        self._log(UPDATE_LEVEL, message, args, **kws)

logging.Logger.success = _success
logging.Logger.update  = _update


# ── Color Formatter ───────────────────────────────────────────────────────────
class ColorFormatter(logging.Formatter):
    """
    Maps log levels to terminal colors:
      SUCCESS (25) -> DARK GREEN  (service working)
      ERROR   (40) -> RED         (service dead)
      CRITICAL(50) -> BRIGHT RED  (fatal)
      WARNING (30) -> YELLOW      (unknown)
      UPDATE  (15) -> BLUE        (compile/update)
      INFO    (20) -> CYAN        (neutral info)
      DEBUG   (10) -> GREY        (noise)
    """
    _FMT = "%(asctime)s  %(levelname)-8s  %(message)s"

    _LEVEL_COLORS = {
        logging.DEBUG:   _C.GREY,
        UPDATE_LEVEL:    _C.BLUE,
        logging.INFO:    _C.CYAN,
        SUCCESS_LEVEL:   _C.DARK_GREEN,
        logging.WARNING: _C.YELLOW,
        logging.ERROR:   _C.RED,
        logging.CRITICAL: _C.BRIGHT_RED,
    }

    def format(self, record):
        color = self._LEVEL_COLORS.get(record.levelno, _C.CYAN)
        fmt   = color + self._FMT + _C.RESET
        return logging.Formatter(fmt, datefmt="%H:%M:%S").format(record)


# ── Safe UTF-8 Stream Handler (Windows) ──────────────────────────────────────
class SafeStreamHandler(logging.StreamHandler):
    """Forces UTF-8 output on Windows consoles."""
    def __init__(self):
        stream = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )
        super().__init__(stream)

    def emit(self, record):
        try:
            msg = self.format(record)
            self.stream.write(msg + self.terminator)
            self.stream.flush()
        except Exception:
            self.handleError(record)


# ── Logger Setup ──────────────────────────────────────────────────────────────
def setup_logger(name: str = "rekov_system") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    # Console — colored
    ch = SafeStreamHandler()
    ch.setLevel(UPDATE_LEVEL)          # Show UPDATE and above in terminal
    ch.setFormatter(ColorFormatter())
    logger.addHandler(ch)

    # File — plain text
    log_dir = os.path.join(os.path.dirname(__file__), "data", "logs")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file  = os.path.join(log_dir, f"system_{timestamp}.log")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)

    return logger


# ── Ready-to-use singleton ────────────────────────────────────────────────────
sys_logger = setup_logger()
