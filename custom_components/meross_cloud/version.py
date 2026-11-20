import json
import logging
import os

_LOGGER = logging.getLogger(__name__)

MEROSS_INTEGRATION_VERSION = "N/A"
try:
    fname = os.path.join(os.path.dirname(__file__), "manifest.json")
    with open(fname, "rt") as f:
        data = json.load(f)
        MEROSS_INTEGRATION_VERSION = data.get("version")
except Exception:  # noqa: BLE001 - diagnostics must not fail on bad manifest
    _LOGGER.error("Failed to retrieve integration version")

_LOGGER.info("Integration Version: %s", MEROSS_INTEGRATION_VERSION)
