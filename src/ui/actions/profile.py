from collections.abc import Callable

import flet as ft

from ...core.strings import get_string
from ...interfaces.protocols import IBrowserLauncher, IProfileManager, IProxyService
from ...services.browser import chrome_prefetch
from ...services.profile import cloning
from ...services.profile.manager import CloneError
from ...services.workflow.store import WorkflowStore
from ..dialogs import open_clone_dialog, open_confirm_dialog, open_profile_dialog
from ..dialogs.profile import PENDING, Pending
from .stop_first import StopThen


def delete_profile(
    page: ft.Page,
    name: str,
    pm: IProfileManager,
    bl: IBrowserLauncher,
    log: Callable[[str], None],
    refresh: Callable[[], None],
    stop_then: StopThen,
) -> None:
    """Confirm, stop the browser if it runs, then delete."""

    def do_delete() -> None:
        if pm.delete_profile(name):
            log(get_string("deleted_profile", name=name))
        refresh()

    body = get_string("cannot_undo")
    if bl.is_running(name):
        body = f"{body} {get_string('delete_running_note')}"
    open_confirm_dialog(page, name, lambda: stop_then([name], do_delete), body=body)


def edit_profile(
    page: ft.Page,
    name: str,
    pm: IProfileManager,
    bl: IBrowserLauncher,
    ps: IProxyService,
    log: Callable[[str], None],
    refresh: Callable[[], None],
    stop_then: StopThen,
    on_renamed: Callable[[str, str], None] | None = None,
) -> None:
    profile = pm.profiles.get(name)
    if not profile:
        return
    original = profile.name

    def save(new_name: str, new_proxy: str, new_os: str, timezone: str, locale: str) -> str | None:
        if pm.update_profile(original, new_name, new_proxy, new_os, timezone, locale):
            if new_name != original and on_renamed:
                on_renamed(original, new_name)
            log(get_string("updated_profile", old=original, new=new_name))
            refresh()
            return None
        return get_string("update_failed")

    def on_save(
        new_name: str, new_proxy: str, new_os: str, timezone: str, locale: str, _engine: str
    ) -> str | Pending | None:
        fields = (new_name, new_proxy, new_os, timezone, locale)
        if new_name == original or not bl.is_running(original):
            return save(*fields)
        # The data dir is renamed with the profile: offer to stop the browser first.
        open_confirm_dialog(
            page,
            original,
            lambda: stop_then([original], lambda: finish(save(*fields))),
            title=get_string("edit_profile"),
            body=get_string("stop_first_rename", name=original),
            action_label=get_string("stop_and_save"),
            action_icon=ft.Icons.STOP_ROUNDED,
            ink=True,
        )
        return PENDING

    finish = open_profile_dialog(page, ps, on_save, profile)


def clone_profile(
    page: ft.Page,
    name: str,
    pm: IProfileManager,
    bl: IBrowserLauncher,
    store: WorkflowStore,
    log: Callable[[str], None],
    refresh: Callable[[], None],
    stop_then: StopThen,
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
        on_stop_browser=lambda done: stop_then(
            [name], lambda: done(not bl.is_running(name)), partial=True
        ),
    )


def add_profile(
    page: ft.Page,
    pm: IProfileManager,
    ps: IProxyService,
    log: Callable[[str], None],
    refresh: Callable[[], None],
    on_created: Callable[[str], None] | None = None,
) -> None:
    """The create dialog; `on_created(name)` runs once it has closed on success."""

    def on_save(
        name: str, proxy: str, os_type: str, timezone: str, locale: str, engine: str
    ) -> str | Pending | None:
        if engine == "chrome" and (reason := chrome_prefetch.unsupported_reason()):
            return get_string("chrome_engine_unsupported", reason=reason)
        if not pm.add_profile(name, proxy, os_type, timezone, locale, engine):
            return get_string("profile_exists")
        log(get_string("created_profile", name=name))
        if engine == "chrome":
            chrome_prefetch.start(log)
        refresh()
        if on_created is None:
            return None
        finish(None)  # closed first, so on_created can open the next dialog
        on_created(name)
        return PENDING

    finish = open_profile_dialog(page, ps, on_save)
