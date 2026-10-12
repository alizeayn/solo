"""``python -m app`` entry point: run the API with uvicorn."""

from __future__ import annotations

import uvicorn

from .config import get_settings
from .main import create_app


def main() -> None:
    settings = get_settings()
    tls: dict[str, str] = {}
    if settings.https_enabled:
        # Serving TLS directly is what makes voice input possible from another
        # device: browsers expose the microphone only in a secure context, so a
        # plain http:// LAN address silently blocks it.
        tls["ssl_certfile"] = str(settings.ssl_certfile)
        tls["ssl_keyfile"] = str(settings.ssl_keyfile)
    uvicorn.run(
        create_app(settings),
        host=settings.app_host,
        port=settings.app_port,
        log_level=settings.log_level.lower(),
        **tls,
    )


if __name__ == "__main__":
    main()
