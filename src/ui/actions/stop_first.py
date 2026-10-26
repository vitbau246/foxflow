"""Stop browsers before an operation that needs them stopped, instead of refusing it."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from typing import Protocol

import flet as ft

from ...core.logging import get_logger
from ...core.strings import get_string
from ...interfaces.protocols import IBrowserLauncher
from ..state import AppState

logger = get_logger("ui")


class StopThen(Protocol):
    """stop_then below with the page, launcher, state and log already bound."""

    def __call__(
        self, names: Iterable[str], then: Callable[[], None], *, partial: bool = False
    ) -> None: ...


def stop_then(
    page: ft.Page,
    names: Iterable[str],
    bl: IBrowserLauncher,
    state: AppState,
    log: Callable[[str], None],
    then: Callable[[], None],
    *,
    stop_runs: Callable[[list[str]], None] | None = None,
    partial: bool = False,
) -> None:
    """Stop the running ones among `names` as the row's Stop does, then call `then`.

    The browsers are stopped off the UI thread and `then` runs once they have
    exited. One that is still running afterwards is logged, and `then` is not
    called, unless `partial` (then `then` must itself skip the ones still running).
    """
    running = [n for n in dict.fromkeys(names) if bl.is_running(n)]
    if not running:
        then()
        return
    if stop_runs:
        # A run would take the stopped browser for a failure and start it again.
        stop_runs(running)
    for name in running:
        log(get_string("stopping_profile", name=name))
        state.set_loading(name, True)
    state.schedule_refresh()

    def stop_all() -> list[str]:
        failed = []
        for name in running:
            try:
                bl.stop_profile(name)
            except Exception as e:
                logger.error("Could not stop %s: %s", name, e)
            finally:
                state.set_loading(name, False)
            if bl.is_running(name):
                failed.append(name)
        return failed

    async def run() -> None:
        failed = await asyncio.to_thread(stop_all)
        state.schedule_refresh()
        for name in failed:
            log(get_string("stop_failed", name=name))
        if partial or not failed:
            then()

    page.run_task(run)
