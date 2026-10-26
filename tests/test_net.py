import os
import urllib.request

import pytest

from src.core import env
from src.utils import net


@pytest.mark.parametrize(
    "url, loopback",
    [
        ("http://127.0.0.1:8000/api/v1/health", True),
        ("http://127.0.0.5:1/", True),
        ("http://localhost:8000/", True),
        ("http://[::1]:8000/", True),
        ("https://api.openai.com/v1", False),
        ("http://198.51.100.7:8000/", False),
    ],
)
def test_is_loopback(url, loopback):
    assert net.is_loopback(url) is loopback


def test_loopback_skips_the_system_proxy(monkeypatch):
    used = []
    monkeypatch.setattr(net._direct, "open", lambda req, timeout: used.append("direct"))
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: used.append("default"))
    net.urlopen(urllib.request.Request("http://127.0.0.1:9/action"), timeout=1)
    net.urlopen("https://example.com/", timeout=1)
    assert used == ["direct", "default"]


@pytest.fixture
def proxy_env(monkeypatch):
    """Undo apply_outbound_proxy's changes to os.environ after each test."""
    for name in (
        "FOXFLOW_HTTP_PROXY",
        "FOXPROFILE_HTTP_PROXY",
        "NO_PROXY",
        "no_proxy",
        *env._PROXY_VARS,
    ):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_without_a_proxy_everything_goes_direct(proxy_env):
    import requests

    proxy_env.setenv("HTTPS_PROXY", "http://198.51.100.9:3128")  # e.g. set by the system
    net.apply_outbound_proxy()
    assert net.outbound_proxy() == "" and net.proxy_label() == ""
    assert "HTTPS_PROXY" not in os.environ
    assert requests.utils.get_environ_proxies("https://api.ipify.org") == {}
    assert urllib.request.proxy_bypass("api.ipify.org")
    assert "FOXFLOW_HTTP_PROXY=http://host:port" in net.network_hint()


def test_foxflow_proxy_is_used_for_the_internet_only(proxy_env):
    import requests

    proxy_env.setenv("FOXFLOW_HTTP_PROXY", "user:pass@203.0.113.5:8800")
    net.apply_outbound_proxy()
    assert net.outbound_proxy() == "http://user:pass@203.0.113.5:8800"
    assert net.proxy_label() == "203.0.113.5:8800"
    assert (
        requests.utils.get_environ_proxies("https://api.ipify.org")["https"] == net.outbound_proxy()
    )
    assert requests.utils.get_environ_proxies("http://127.0.0.1:8000/") == {}
    hint = net.network_hint()
    assert "203.0.113.5:8800" in hint and "pass" not in hint


def test_legacy_name_still_works(proxy_env):
    proxy_env.setenv("FOXPROFILE_HTTP_PROXY", "http://203.0.113.5:8800")
    assert net.proxy_label() == "203.0.113.5:8800"


@pytest.mark.parametrize(
    "module",
    ["src.core.config", "src.server", "src.main", "src.mcp_server.server", "chrome_engine.fetch"],
)
def test_entry_points_import_in_a_fresh_interpreter(module):
    """In-process tests import modules in an order that can hide an import cycle."""
    import subprocess
    import sys

    done = subprocess.run(
        [sys.executable, "-c", f"import {module}"], capture_output=True, text=True, timeout=120
    )
    assert done.returncode == 0, done.stderr[-2000:]
