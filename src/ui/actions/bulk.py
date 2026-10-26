from collections.abc import Callable

import flet as ft

from ...core.strings import get_string
from ...interfaces.protocols import IBrowserLauncher, IProfileManager
from ..dialogs import open_confirm_dialog
from ..state import AppState
from .browser import launch_or_stop
from .stop_first import StopThen


def bulk_delete_profiles(
    page: ft.Page,
    names: list[str],
    pm: IProfileManager,
    bl: IBrowserLauncher,
    log: Callable[[str], None],
    refresh: Callable[[], None],
    on_done: Callable[[], None],
    stop_then: StopThen,
) -> None:
    """Confirm, stop the running ones, then delete every one that has stopped."""
    if not names:
        return

    def do_bulk_delete() -> None:
        for name in names:
            # One that would not stop is logged by stop_then and kept.
            if not bl.is_running(name) and pm.delete_profile(name):
                log(get_string("deleted_profile", name=name))
        on_done()
        refresh()

    body = get_string("cannot_undo")
    if running := sum(1 for n in names if bl.is_running(n)):
        body = f"{body} {get_string('bulk_delete_running_note', count=running)}"
    open_confirm_dialog(
        page,
        "",
        lambda: stop_then(names, do_bulk_delete, partial=True),
        title=get_string("confirm_bulk_delete", count=len(names)),
        body=body,
    )


def bulk_launch_profiles(
    names: list[str],
    pm: IProfileManager,
    bl: IBrowserLauncher,
    state: AppState,
    log: Callable[[str], None],
) -> None:
    for name in names:
        if not bl.is_running(name) and not state.is_loading(name):
            launch_or_stop(name, pm, bl, state, log)


def bulk_stop_profiles(
    names: list[str],
    pm: IProfileManager,
    bl: IBrowserLauncher,
    state: AppState,
    log: Callable[[str], None],
) -> None:
    for name in names:
        if bl.is_running(name):
            launch_or_stop(name, pm, bl, state, log)
