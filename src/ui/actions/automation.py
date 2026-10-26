"""What the Automation page, the Run dialog and the bulk bar's Run workflow do."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable

import flet as ft

from ...core.strings import get_string
from ...interfaces.protocols import IBrowserLauncher, IProfileManager
from ..dialogs.ai_settings import ai_setup_needed
from ..dialogs.confirm import open_confirm_dialog
from ..dialogs.record_workflow import open_record_dialog
from ..dialogs.run_log import open_run_log
from ..dialogs.run_workflow import open_run_dialog
from ..dialogs.workflow_editor import open_workflow_editor
from ..dialogs.workflows import WorkflowServices, open_workflows_dialog


class AutomationHandlers:
    def __init__(
        self,
        pm: IProfileManager,
        bl: IBrowserLauncher,
        services: WorkflowServices,
        get_page: Callable[[], ft.Page | None],
        get_recording: Callable[[], set[str]],
        on_changed: Callable[[], None],
        launch: Callable[[str], None] | None = None,
        is_loading: Callable[[str], bool] | None = None,
        add_profile: Callable[[Callable[[str], None]], None] | None = None,
    ) -> None:
        """`get_recording`: profiles recording now; `on_changed`: workflows or runs changed.

        `add_profile(on_created)` opens the create-profile dialog.
        """
        self._pm = pm
        self._bl = bl
        self._wf = services
        self._get_page = get_page
        self._get_recording = get_recording
        self._changed = on_changed
        self._launch = launch
        self._is_loading = is_loading
        self._add_profile = add_profile

    def _page(self) -> ft.Page:
        page = self._get_page()
        assert page is not None
        return page

    def open_run(self, workflow: str | None = None, profiles: Iterable[str] = ()) -> None:
        """The Run dialog, for one workflow (row) or for the selected profiles (bulk bar).

        With no workflow to pick yet, Record workflow opens instead.
        """
        if workflow is None and not self._wf.store.list():
            self.record(note=get_string("rec_first_workflow"))
            return
        names = sorted(self._pm.profiles, key=str.casefold)
        open_run_dialog(
            self._page(),
            self._wf,
            names,
            self._bl.running_profile_names(),
            self._get_recording(),
            workflow=workflow,
            preselect=profiles,
            on_started=self._changed,
        )

    def run_again(self, workflow: str, profile: str, chain: list[str] | None = None) -> None:
        """Run the workflow (or the whole chain it was part of) in the profile again."""
        order = chain or [workflow]
        for name in dict.fromkeys(order):
            if ai_setup_needed(self._page(), self._wf.ai, self._wf.store, name, self._wf.log):
                return
        workflow = " → ".join(order)

        async def start() -> None:
            try:
                if len(order) == 1:
                    await asyncio.to_thread(self._wf.runner.start, order[0], profile, {})
                else:
                    await asyncio.to_thread(self._wf.runner.start_chain, order, profile, {})
            except Exception as e:  # WorkflowError, or the browser went away
                self._wf.log(
                    get_string("wf_run_failed", workflow=workflow, name=profile, error=str(e))
                )
                return
            self._wf.log(get_string("wf_started", workflow=workflow, name=profile))
            self._changed()

        self._page().run_task(start)

    def stop(self, profile: str) -> None:
        if self._wf.runner.stop(profile):
            self._wf.log(get_string("wf_stopping", name=profile))
        self._changed()

    def show_log(self, profile: str) -> None:
        open_run_log(self._page(), self._wf.runner, profile, on_stop=self.stop)

    def edit(self, workflow: str) -> None:
        open_workflow_editor(
            self._page(), self._wf.store, workflow, on_saved=self._changed, ai_settings=self._wf.ai
        )

    def delete(self, workflow: str) -> None:
        def confirmed() -> None:
            if self._wf.store.delete(workflow):
                self._wf.log(get_string("wf_deleted", name=workflow))
            self._changed()

        open_confirm_dialog(
            self._page(),
            workflow,
            confirmed,
            title=get_string("wf_confirm_delete", name=workflow),
        )

    def record(self, note: str = "") -> None:
        """Pick a profile; it is launched if needed and recording starts in its browser.

        With no profile yet, one can be created there and recording starts in it.
        """
        add = self._add_profile
        open_record_dialog(
            self._page(),
            list(self._pm.profiles),
            self._bl.running_profile_names(),
            self.record_in,
            on_new_profile=(lambda: add(self.record_in)) if add else None,
            note=note,
        )

    def record_in(self, profile: str) -> None:
        """The profile's workflows dialog, launching it and recording once it is up."""
        open_workflows_dialog(
            self._page(),
            profile,
            self._wf,
            on_close=self._changed,
            launch=self._launch,
            is_loading=self._is_loading,
            auto_record=True,
        )
