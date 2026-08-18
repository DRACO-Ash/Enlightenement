"""Container entrypoint. gunicorn imports ``app`` from here.

Excluded from the COVERAGE metric only (see sonar-project.properties): it is process
wiring that no in-process test can execute without starting a real worker. It stays
fully analysed for violations.
"""

from __future__ import annotations

import logging

from enlightenment.app import create_app

logging.basicConfig(level=logging.INFO, format="%(message)s")

app = create_app()
