"""FOXFLOW_* environment variables, still honouring FoxProfile's FOXPROFILE_* names.

No side effects on import: server mode reads it before `src.core.config` loads.
"""

import os
from urllib.parse import urlsplit

PREFIX = "FOXFLOW_"
LEGACY_PREFIX = "FOXPROFILE_"


def getenv(key: str, default: str | None = None) -> str | None:
    """FOXFLOW_<key>, else the legacy FOXPROFILE_<key>, else `default`."""
    value = os.getenv(PREFIX + key)
    if value is None:
        value = os.getenv(LEGACY_PREFIX + key)
    return default if value is None else value


# FoxFlow's own internet requests: FOXFLOW_HTTP_PROXY, or no proxy at all (see src/utils/net.py).
_PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
_LOOPBACK = "localhost,127.0.0.1,::1"


def outbound_proxy() -> str:
    """FOXFLOW_HTTP_PROXY as a URL (http:// added when missing), or ""."""
    proxy = (getenv("HTTP_PROXY") or "").strip()
    return proxy if not proxy or "://" in proxy else "http://" + proxy


def proxy_label(proxy: str | None = None) -> str:
    """host:port of the outbound proxy, never its credentials; "" when there is none."""
    proxy = outbound_proxy() if proxy is None else proxy
    if not proxy:
        return ""
    parts = urlsplit(proxy if "://" in proxy else "http://" + proxy)
    return f"{parts.hostname}:{parts.port}" if parts.port else parts.hostname or ""


def apply_outbound_proxy() -> None:
    """Point this process (and the ones it starts) at FOXFLOW_HTTP_PROXY, or at no proxy.

    urllib and requests (also inside Camoufox) read these variables; NO_PROXY=*
    also keeps them off the Windows system proxy.
    """
    proxy = outbound_proxy()
    for name in _PROXY_VARS:
        os.environ.pop(name, None)
    if proxy:
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ[name] = proxy
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = _LOOPBACK if proxy else "*"
