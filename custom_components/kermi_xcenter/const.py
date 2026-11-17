"""Constants for the Kermi x-center (local, read-only) integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "kermi_xcenter"
MANUFACTURER: Final = "Kermi"

CONF_SCAN_INTERVAL: Final = "scan_interval"
DEFAULT_SCAN_INTERVAL: Final = 30  # seconds
MIN_SCAN_INTERVAL: Final = 15  # seconds
MAX_SCAN_INTERVAL: Final = 3600  # seconds

# Exponential back-off on consecutive failures, capped at 15 minutes.
MAX_BACKOFF: Final = timedelta(minutes=15)

REQUEST_TIMEOUT: Final = 15  # seconds per HTTP request

# The x-center API rejects or silently empties very large reads.
READ_CHUNK_SIZE: Final = 40

# Writes (only when the user enabled them in the options; default off).
CONF_ALLOW_WRITES: Final = "allow_writes"
CONF_CONFIRM_WRITES: Final = "confirm_writes"
WRITE_MIN_INTERVAL: Final = 300  # seconds between two writes of one datapoint
