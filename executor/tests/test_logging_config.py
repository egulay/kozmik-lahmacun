import logging
from datetime import datetime

from kozmik_executor.logging_config import MonthlyDailyFileHandler


def test_daily_files_are_created_inside_month_directories(tmp_path) -> None:
    timestamps = iter(
        [
            datetime(2026, 7, 31, 23, 59),
            datetime(2026, 8, 1, 0, 1),
        ]
    )
    handler = MonthlyDailyFileHandler(tmp_path, clock=lambda: next(timestamps))
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))

    handler.emit(logging.LogRecord("test", logging.INFO, "", 0, "first", (), None))
    handler.emit(logging.LogRecord("test", logging.INFO, "", 0, "second", (), None))
    handler.close()

    assert (tmp_path / "2026-07" / "2026-07-31.log").read_text() == "INFO first\n"
    assert (tmp_path / "2026-08" / "2026-08-01.log").read_text() == "INFO second\n"
