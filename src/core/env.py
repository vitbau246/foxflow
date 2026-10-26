"""FOXFLOW_* environment variables, still honouring FoxProfile's FOXPROFILE_* names.

No side effects on import: server mode reads it before `src.core.config` loads.
"""

import os

PREFIX = "FOXFLOW_"
LEGACY_PREFIX = "FOXPROFILE_"


def getenv(key: str, default: str | None = None) -> str | None:
    """FOXFLOW_<key>, else the legacy FOXPROFILE_<key>, else `default`."""
    value = os.getenv(PREFIX + key)
    if value is None:
        value = os.getenv(LEGACY_PREFIX + key)
    return default if value is None else value
