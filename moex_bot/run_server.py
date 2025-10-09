"""Start the MOEX bot web server.

This script launches the FastAPI application defined in
``moex_bot.web.app`` using Uvicorn.  It reads the host and port
from environment variables ``MOEX_API_HOST`` and ``MOEX_API_PORT``
with defaults ``0.0.0.0`` and ``8000``.
"""

from __future__ import annotations
import os

from dotenv import load_dotenv


def main() -> None:
    # Load variables from .env before importing the FastAPI app so that configuration
    # reads (e.g. admin credentials) use the latest overrides.
    load_dotenv(override=True)
    from moex_bot.web.app import app

    host = os.getenv('MOEX_API_HOST', '0.0.0.0')
    port = int(os.getenv('MOEX_API_PORT', '8000'))
    try:
        import uvicorn
    except ImportError:
        raise SystemExit("Uvicorn is required to run the web server. Install it via pip.")
    uvicorn.run(app, host=host, port=port)


if __name__ == '__main__':
    main()