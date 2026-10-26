from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..interfaces.protocols import IBrowserLauncher, IProfileManager, IProxyService
from .config import LOG_DIR, LOG_LEVEL
from .events import EventBus
from .logging import setup_logging

if TYPE_CHECKING:
    from ..services.ai.settings import AISettingsStore
    from ..services.workflow.runner import WorkflowRunner
    from ..services.workflow.store import WorkflowStore


class Container:
    def __init__(self) -> None:
        setup_logging(LOG_DIR, getattr(logging, LOG_LEVEL, logging.INFO))
        self._instances: dict = {}
        # The first API requests arrive on several worker threads at once; each
        # service must be built exactly once or they would hold separate state.
        self._lock = threading.RLock()

    def _get(self, key: str, build: Callable[[], object]):
        instance = self._instances.get(key)
        if instance is None:
            with self._lock:
                instance = self._instances.get(key)
                if instance is None:
                    instance = self._instances[key] = build()
        return instance

    @property
    def event_bus(self) -> EventBus:
        return self._get("eb", EventBus)

    @property
    def profile_manager(self) -> IProfileManager:
        from ..services.profile.manager import ProfileManager

        return self._get("pm", ProfileManager)

    @property
    def browser_launcher(self) -> IBrowserLauncher:
        from ..services.browser.launcher import BrowserLauncher

        return self._get("bl", BrowserLauncher)

    @property
    def workflow_store(self) -> WorkflowStore:
        from ..services.workflow.store import WorkflowStore

        return self._get("ws", WorkflowStore)

    @property
    def ai_settings(self) -> AISettingsStore:
        from ..services.ai.settings import AISettingsStore

        return self._get("ai", AISettingsStore)

    @property
    def workflow_runner(self) -> WorkflowRunner:
        from ..services.workflow.runner import WorkflowRunner

        return self._get(
            "wr",
            lambda: WorkflowRunner(
                self.workflow_store,
                self.profile_manager,
                self.browser_launcher,
                on_change=self.event_bus.emit,
                ai_settings=self.ai_settings,
            ),
        )

    @property
    def proxy_service(self) -> IProxyService:
        from ..services.proxy.service import ProxyService

        return self._get("ps", ProxyService)
