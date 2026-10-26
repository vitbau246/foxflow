from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, Request

if TYPE_CHECKING:
    from ..core.container import Container
    from ..core.events import EventBus
    from ..interfaces import IBrowserLauncher, IProfileManager, IProxyService
    from ..services.ai.settings import AISettingsStore
    from ..services.automation.engine import AutomationEngine
    from ..services.automation.store import AutomationStore
    from ..services.workflow.runner import WorkflowRunner
    from ..services.workflow.store import WorkflowStore


def _container(request: Request) -> Container:
    return request.app.state.container


def get_profile_manager(
    container: Container = Depends(_container),
) -> IProfileManager:
    return container.profile_manager


def get_browser_launcher(
    container: Container = Depends(_container),
) -> IBrowserLauncher:
    return container.browser_launcher


def get_proxy_service(
    container: Container = Depends(_container),
) -> IProxyService:
    return container.proxy_service


def get_event_bus(
    container: Container = Depends(_container),
) -> EventBus:
    return container.event_bus


def get_workflow_store(
    container: Container = Depends(_container),
) -> WorkflowStore:
    return container.workflow_store


def get_workflow_runner(
    container: Container = Depends(_container),
) -> WorkflowRunner:
    return container.workflow_runner


def get_ai_settings(
    container: Container = Depends(_container),
) -> AISettingsStore:
    return container.ai_settings


def get_automation_store(
    container: Container = Depends(_container),
) -> AutomationStore:
    return container.automation_store


def get_automation_engine(
    container: Container = Depends(_container),
) -> AutomationEngine:
    return container.automation_engine
