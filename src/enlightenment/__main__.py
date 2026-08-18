"""Local development listener: ``python -m enlightenment``.

Reads PORT from the environment defaulting to 8080. Binds every interface when a team
token is configured and loopback when it is not, so single-user local mode with
authentication off is never reachable off the machine. The container does not use this
module: its launch command binds ``0.0.0.0`` explicitly.
"""

from __future__ import annotations

import logging

import uvicorn

from enlightenment.app import create_app
from enlightenment.config import load_config


def main() -> None:
    """Start the development server."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = load_config()
    uvicorn.run(create_app(config=settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
