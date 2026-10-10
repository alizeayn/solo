"""``python -m app`` entry point: run the API with uvicorn."""

from __future__ import annotations

import uvicorn

from .config import get_settings
from .main import create_app


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        create_app(settings),
        host=settings.app_host,
        port=settings.app_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
