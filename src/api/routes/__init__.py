from .automations import hooks_router
from .automations import router as automations_router
from .browser import router as browser_router
from .mcp_setup import router as mcp_setup_router
from .page import router as page_router
from .profiles import router as profiles_router
from .proxy import router as proxy_router
from .workflows import router as workflows_router

__all__ = [
    "automations_router",
    "hooks_router",
    "browser_router",
    "mcp_setup_router",
    "page_router",
    "profiles_router",
    "proxy_router",
    "workflows_router",
]
