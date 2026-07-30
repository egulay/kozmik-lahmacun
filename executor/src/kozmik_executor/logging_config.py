from __future__ import annotations

import logging
import os
import re
import sys
from contextvars import ContextVar
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TextIO

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")
SAFE_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")


def safe_error_code(exception: Exception, fallback: str) -> str:
    value = str(exception)
    return value if SAFE_ERROR_CODE.fullmatch(value) else fallback


class CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id.get()
        return True


def set_correlation_id(value: str):
    return correlation_id.set(value)


def reset_correlation_id(token) -> None:
    correlation_id.reset(token)


class MonthlyDailyFileHandler(logging.Handler):
    """Write one log file per local calendar day inside a monthly directory."""

    def __init__(
        self,
        root_directory: str | Path,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__()
        self.root_directory = Path(root_directory).expanduser()
        self.clock = clock or (lambda: datetime.now().astimezone())
        self._active_path: Path | None = None
        self._stream: TextIO | None = None

    def _path(self, timestamp: datetime) -> Path:
        return (
            self.root_directory
            / timestamp.strftime("%Y-%m")
            / f"{timestamp.strftime('%Y-%m-%d')}.log"
        )

    def _ensure_stream(self) -> TextIO:
        target = self._path(self.clock())
        if target != self._active_path or self._stream is None:
            if self._stream is not None:
                self._stream.close()
            target.parent.mkdir(parents=True, exist_ok=True)
            self._stream = target.open("a", encoding="utf-8", buffering=1)
            self._active_path = target
        return self._stream

    def emit(self, record: logging.LogRecord) -> None:
        try:
            stream = self._ensure_stream()
            stream.write(self.format(record) + self.terminator)
            stream.flush()
        except Exception:
            self.handleError(record)

    @property
    def terminator(self) -> str:
        return "\n"

    def close(self) -> None:
        self.acquire()
        try:
            if self._stream is not None:
                self._stream.close()
                self._stream = None
        finally:
            self.release()
        super().close()


def configure_logging() -> None:
    level_name = os.getenv("PYTHON_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    formatter = logging.Formatter(
        "timestamp=%(asctime)s.%(msecs)03d service=kozmik-executor "
        "level=%(levelname)-5s correlationId=%(correlation_id)s "
        "thread=%(threadName)s logger=%(name)s message=%(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.addFilter(CorrelationFilter())
    console.setFormatter(formatter)
    file_handler = MonthlyDailyFileHandler(
        os.getenv("PYTHON_LOG_DIR", "logs/python")
    )
    file_handler.addFilter(CorrelationFilter())
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(console)
    root.addHandler(file_handler)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
        uvicorn_logger.setLevel(level)
