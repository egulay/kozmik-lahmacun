import os
from importlib.resources import files

import uvicorn

from kozmik_executor.logging_config import configure_logging


def print_banner() -> None:
    banner = files("kozmik_executor").joinpath("banner.txt").read_text(encoding="utf-8")
    print(banner.rstrip(), flush=True)


def main() -> None:
    print_banner()
    configure_logging()
    uvicorn.run(
        "kozmik_executor.main:app",
        host="0.0.0.0",
        port=int(os.getenv("EXECUTOR_PORT", "8000")),
        log_config=None,
        access_log=True,
    )


if __name__ == "__main__":
    main()
