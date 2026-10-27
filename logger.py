from __future__ import annotations
import sys
import time
import logging
from pathlib import Path
from contextlib import contextmanager

# Ensure UTF-8 output on Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


class CustomFormatter(logging.Formatter):
    """Clean, high-observability log formatter with module tags and timestamps."""

    COLORS = {
        logging.DEBUG: "\033[90m",    # Gray
        logging.INFO: "\033[36m",     # Cyan
        logging.WARNING: "\033[33m",  # Yellow
        logging.ERROR: "\033[31m",    # Red
        logging.CRITICAL: "\033[35m", # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
        level = record.levelname.ljust(7)
        module_tag = f"[{record.name.upper()}]".ljust(11)
        color = self.COLORS.get(record.levelno, "")
        reset = self.RESET if color else ""
        return f"{color}[{timestamp}] [{level}] {module_tag} {record.getMessage()}{reset}"


class FileFormatter(logging.Formatter):
    """Plain file formatter without ANSI color codes."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
        level = record.levelname.ljust(7)
        module_tag = f"[{record.name.upper()}]".ljust(11)
        return f"[{timestamp}] [{level}] {module_tag} {record.getMessage()}"


def setup_logger(name: str, log_file: Path | str | None = None) -> logging.Logger:
    """Set up and return a structured logger with both console and optional file output."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid adding duplicate handlers on multiple calls
    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(CustomFormatter())
        logger.addHandler(console_handler)

    if log_file:
        file_path = Path(log_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        # Check if file handler already exists for this file
        existing_files = [
            getattr(h, "baseFilename", None)
            for h in logger.handlers
            if isinstance(h, logging.FileHandler)
        ]
        if str(file_path.resolve()) not in existing_files:
            file_handler = logging.FileHandler(str(file_path), encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(FileFormatter())
            logger.addHandler(file_handler)

    return logger


@contextmanager
def log_step(logger: logging.Logger, step_name: str):
    """Context manager for measuring and logging execution time of critical steps."""
    logger.info(f"▶ START: {step_name}")
    t0 = time.time()
    try:
        yield
        elapsed = time.time() - t0
        logger.info(f"✔ DONE:  {step_name} (took {elapsed:.2f}s)")
    except Exception as e:
        elapsed = time.time() - t0
        logger.error(f"✖ FAILED: {step_name} after {elapsed:.2f}s - Error: {e}")
        raise
