"""ASGI entry point: `uvicorn splitkit.api.main:app`. Fails fast if config is missing."""

import logging

from splitkit.api.app import create_app
from splitkit.api.settings import Settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
app = create_app(Settings.from_env())
