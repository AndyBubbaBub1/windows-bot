"""Start the MOEX bot web server.

This script launches the FastAPI application defined in
``moex_bot.web.app`` using Uvicorn.  It reads the host and port
from environment variables ``MOEX_API_HOST`` and ``MOEX_API_PORT``
with defaults ``0.0.0.0`` and ``8000``.
"""

from __future__ import annotations
from dotenv import load_dotenv
# Load environment variables from a .env file before anything else.  Use override=True
# to ensure values in the .env file take precedence over any variables already
# defined in the system environment.  Without this, variables such as
# MOEX_API_USER or MOEX_API_PASS left over from previous sessions could force
# authentication even when they are removed from the .env file.  See issue
# https://github.com/theskysource/moex-bot/issues for context.
load_dotenv(override=True)

import os
# Import the FastAPI app from the packaged ``moex_bot`` namespace.  This
# requires that the project is installed (e.g. via ``pip install -e .``).
from moex_bot.web.app import app


def main() -> None:
    host = os.getenv('MOEX_API_HOST', '0.0.0.0')
    port = int(os.getenv('MOEX_API_PORT', '8000'))
    try:
        import uvicorn
    except ImportError:
        raise SystemExit("Uvicorn is required to run the web server. Install it via pip.")
    uvicorn.run(app, host=host, port=port)


if __name__ == '__main__':
    main()