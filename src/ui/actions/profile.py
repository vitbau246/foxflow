from collections.abc import Callable

import flet as ft

from ...core.strings import get_string
from ...interfaces.protocols import IBrowserLauncher, IProfileManager, IProxyService
from ...services.browser import chrome_prefetch
from ...services.profile import cloning
from ...services.profile.manager import CloneError
from ...services.workflow.store import WorkflowStore
from ..dialogs import open_clone_dialog, open_confirm_dialog, open_profile_dialog


def delete_profile(
    page: ft.Page,
    name: str,
    pm: IProfileManager,
    log: Callable[[str], None],
    refresh: Callable[[], None],
) -> None:
    def do_delete() -> None:
        pm.delete_profile(name)
        log(get_string("deleted_profile", name=name))
        refresh()

    open_confirm_dialog(page, name, do_delete)


def edit_profile(
    page: ft.Page,
    name: str,
    pm: IProfileManager,
    bl: IBrowserLauncher,
    ps: IProxyService,
    log: Callable[[str], None],
    refresh: Callable[[], None],
    on_renamed: Callable[[str, str], None] | None = None,
) -> None:
    profile = pm.profiles.get(name)
    if not profile:
        return
    original = profile.name

    def on_save(
        new_name: str, new_proxy: str, new_os: str, timezone: str, locale: str, _engine: str
    ) -> str | None:
        if new_name != original and bl.is_running(original):
            return get_string("stop_before_rename")
        if pm.update_profile(original, new_name, new_proxy, new_os, timezone, locale):
            if new_name != original and on_renamed:
                on_renamed(original, new_name)
            log(get_string("updated_profile", old=original, new=new_name))
            refresh()
            return None
        return get_string("update_failed")

    open_profile_dialog(page, ps, on_save, profile)


def clone_profile(
    page: ft.Page,
    name: str,
    pm: IProfileManager,
    bl: IBrowserLauncher,
    store: WorkflowStore,
    log: Callable[[str], None],
    refresh: Callable[[], None],
) -> None:
    if name not in pm.profiles:
        return

    def on_clone(base: str, count: int, parts: set[str]) -> str | None:
        try:
            clones, workflows = cloning.clone(pm, bl, store, name, base, count, parts)
        except cloning.SourceRunningError:
            return get_string("clone_copy_data_running")
        except CloneError as e:
            refresh()  # copies made before a failure are real profiles
            return str(e)
        if len(clones) == 1:
            log(get_string("cloned_profile", name=name, copy=clones[0].name))
        else:
            log(get_string("cloned_profiles", name=name, count=len(clones)))
        if workflows:
            log(get_string("cloned_workflows", count=workflows))
        if clones[0].engine == "chrome":
            chrome_prefetch.start(log)
        refresh()
        return None

    open_clone_dialog(
        page,
        name,
        pm.clone_name(name),
        bl.is_running(name),
        pm.clone_names,
        on_clone,
        workflow_count=len(store.of_profile(name)),
    )


def add_profile(
    page: ft.Page,
    pm: IProfileManager,
    ps: IProxyService,
    log: Callable[[str], None],
    refresh: Callable[[], None],
) -> None:
    def on_save(
        name: str, proxy: str, os_type: str, timezone: str, locale: str, engine: str
    ) -> str | None:
        if engine == "chrome" and (reason := chrome_prefetch.unsupported_reason()):
            return get_string("chrome_engine_unsupported", reason=reason)
        if pm.add_profile(name, proxy, os_type, timezone, locale, engine):
            log(get_string("created_profile", name=name))
            if engine == "chrome":
                chrome_prefetch.start(log)
            refresh()
            return None
        return get_string("profile_exists")

    open_profile_dialog(page, ps, on_save)
