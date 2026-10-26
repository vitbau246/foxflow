try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from src.core.env import apply_outbound_proxy, getenv

# FoxFlow's own internet requests use FOXFLOW_HTTP_PROXY, or no proxy at all;
# set before anything opens a connection, and inherited by the browser runners.
apply_outbound_proxy()


def _env(key: str, default: str) -> str:
    """Read FOXFLOW_<key> (or FoxProfile's FOXPROFILE_<key>)."""
    return getenv(key, default)


PROFILES_FILE = _env("PROFILES_FILE", "profiles.json")
DATA_DIR = _env("DATA_DIR", "camoufox_data")
LOG_DIR = _env("LOG_DIR", "logs")
LOG_LEVEL = _env("LOG_LEVEL", "INFO")
PROXY_CHECK_TIMEOUT = int(_env("PROXY_TIMEOUT", "10"))
LANGUAGE = _env("LANG", "en")

API_HOST = _env("API_HOST", "127.0.0.1")
API_PORT = int(_env("API_PORT", "8000"))

# Seconds the API waits for a launched browser to report ready or failed.
LAUNCH_WAIT_TIMEOUT = int(_env("LAUNCH_TIMEOUT", "90"))

FINGERPRINT_FILE = "fingerprint.json"

# Recorded workflows, one JSON file each.
WORKFLOWS_DIR = _env("WORKFLOWS_DIR", "workflows")

# Optional AI text generation for workflow "ai" steps (OpenAI-compatible API).
# Off until a key is set here or in the AI settings; the key here is never saved.
AI_SETTINGS_FILE = _env("AI_SETTINGS_FILE", "ai_settings.json")
OPENAI_API_KEY = _env("OPENAI_API_KEY", "")
OPENAI_BASE_URL = _env("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = _env("OPENAI_MODEL", "gpt-4o-mini")


def _headless(value: str) -> bool | str:
    """'true'/'false', or 'virtual' (Linux: hidden Xvfb display, more stealthy)."""
    value = value.strip().lower()
    if value == "virtual":
        return "virtual"
    return value in ("1", "true", "yes")


# Browsers open hidden when true; server mode turns this on by default.
HEADLESS = _headless(_env("HEADLESS", "false"))

# Reopen the tabs a profile had open when it was last stopped.
RESTORE_TABS = _env("RESTORE_TABS", "true").strip().lower() in ("1", "true", "yes")

# Shared secret for the REST API, the web panel and the MCP server. Required
# whenever the API listens on anything other than the loopback interface.
API_TOKEN = _env("API_TOKEN", "")
