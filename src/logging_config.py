"""
Structured Logging Configuration

Provides consistent JSON-structured logging across all modules.
Writes to both console (human-readable) and a log file (JSON lines).

Usage:
    from src.logging_config import setup_logging
    setup_logging()  # Call once at startup

    import logging
    logger = logging.getLogger("my_module")
    logger.info("Something happened", extra={"player": "Tiger Woods", "ev": 0.12})
"""

import json
import logging
import os
import sys
from datetime import datetime


LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)


class JsonFormatter(logging.Formatter):
    """Formats log records as JSON lines for machine parsing."""

    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include any extra fields
        for key in ["player", "tournament", "event_id", "ev", "roi",
                     "experiment_id", "duration_ms", "error"]:
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


class ConsoleFormatter(logging.Formatter):
    """Color-coded console output."""

    COLORS = {
        "DEBUG": "\033[90m",
        "INFO": "\033[37m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[41m\033[37m",
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, "")
        timestamp = datetime.now().strftime("%H:%M:%S")
        return f"{color}{timestamp} [{record.name}] {record.levelname}: {record.getMessage()}{self.RESET}"


def setup_logging(level: str = "INFO", log_file: str = None):
    """
    Configure logging for the application.

    Args:
        level: Minimum log level ("DEBUG", "INFO", "WARNING", "ERROR")
        log_file: Optional log file path. Defaults to logs/golf_model.log
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    root.handlers.clear()

    # Console handler (human-readable)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(ConsoleFormatter())
    console.setLevel(logging.INFO)
    root.addHandler(console)

    # File handler (JSON lines)
    if log_file is None:
        log_file = os.path.join(LOG_DIR, "golf_model.log")

    try:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(JsonFormatter())
        file_handler.setLevel(logging.DEBUG)
        root.addHandler(file_handler)
    except Exception:
        pass  # Silently skip if log file can't be created

    # Reduce noise from third-party libraries
    for name in ["urllib3", "httpcore", "httpx", "openai", "anthropic"]:
        logging.getLogger(name).setLevel(logging.WARNING)
