"""How FoxFlow itself reaches the network.

FoxFlow's own internet requests (the AI API, the Chrome engine and GeoIP
downloads, exit-IP and Check IP lookups for profiles without a proxy of their
own) go through FOXFLOW_HTTP_PROXY when it is set, and directly otherwise: the
system proxy (Windows registry) and HTTP(S)_PROXY are ignored. Browsers are not
affected: their traffic follows each profile's proxy.

Loopback (FoxFlow's own API, a browser's control server) is always reached
directly; a corporate proxy would otherwise answer for 127.0.0.1.
"""

import urllib.request
from urllib.parse import urlsplit

# The proxy settings live with the env helpers: src.core.config applies them at import.
from ..core.env import apply_outbound_proxy, outbound_proxy, proxy_label  # noqa: F401

_direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def is_loopback(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    return host in ("localhost", "::1") or host.startswith("127.")


def network_hint() -> str:
    """What to check when FoxFlow cannot reach the internet."""
    label = proxy_label()
    if label:
        return (
            f"FoxFlow connects through FOXFLOW_HTTP_PROXY ({label}); check that this proxy works."
        )
    return (
        "If this machine reaches the internet through a proxy, set "
        "FOXFLOW_HTTP_PROXY=http://host:port in .env and restart FoxFlow."
    )


def log_network(logger) -> None:
    """Say at startup how FoxFlow reaches the internet."""
    label = proxy_label()
    if label:
        logger.info("Internet requests go through FOXFLOW_HTTP_PROXY %s", label)
    else:
        logger.info(
            "Internet requests go direct (no proxy). If this machine needs one, "
            "set FOXFLOW_HTTP_PROXY=http://host:port in .env"
        )


def urlopen(request: urllib.request.Request | str, timeout: float):
    """urllib.request.urlopen, but loopback addresses are always reached directly."""
    url = request.full_url if isinstance(request, urllib.request.Request) else request
    if is_loopback(url):
        return _direct.open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)
