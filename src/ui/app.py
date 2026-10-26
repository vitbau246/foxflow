import asyncio
import os
import time

import flet as ft

from ..core.config import DATA_DIR
from ..core.container import Container
from ..core.logging import get_logger
from ..core.strings import current_language, get_string, set_language
from ..interfaces.protocols import IBrowserLauncher, IProfileManager, IProxyService
from ..services.browser import fingerprint
from ..services.workflow import recording
from .actions.automation import AutomationHandlers
from .components import (
    build_content_area,
    build_empty_state,
    build_profile_card,
    build_sidebar,
    build_ui_refs,
    rebuild_bulk_bar,
)
from .components.automation import AutomationActions, AutomationData, AutomationPage
from .components.profile_card import build_header_row
from .components.sidebar import (
    build_filter_buttons,
    build_primary_button,
    build_view_buttons,
    primary_for,
    rail_section,
)
from .dialogs.mcp_guide import open_mcp_guide
from .dialogs.workflows import WorkflowServices
from .handlers import AppHandlers
from .refs import UIRefs
from .state import ITEMS_PER_PAGE, AppState
from .theme import COLORS, configure_page
from .theme.colors import FONT_SEMIBOLD
from .theme.page import ASSETS_DIR

logger = get_logger("app")

# While a run is active and the Automation page shows, it is redrawn this often.
AUTO_POLL_SECONDS = 1.5
# Saved workflows are read from disk at most this often (or when they change here).
WORKFLOWS_TTL_SECONDS = 1.5


class App:
    def __init__(self, container: Container | None = None) -> None:
        c = container or Container()
        self.pm: IProfileManager = c.profile_manager
        self.bl: IBrowserLauncher = c.browser_launcher
        self.ps: IProxyService = c.proxy_service
        self.state = AppState()
        self.page: ft.Page | None = None
        self._reconcile_started = False
        self.refs: UIRefs | None = None
        self.filter = "all"
        # What the main area shows: "automation" (the default) or "profiles".
        # Kept on the App so a rebuild (language switch) keeps it.
        self.view = "automation"
        self.auto_query = ""
        self._live_since: dict[str, str] = {}
        self._filter_column = ft.Column(spacing=2)
        self._view_column = ft.Column(spacing=2)
        self._header_slot = ft.Container()
        self.runner = c.workflow_runner
        self.store = c.workflow_store
        self._workflows: list[dict] | None = None
        self._workflows_read = 0.0
        self._auto_tick = 0.0
        self._view_key: tuple | None = None
        # Profiles recording or holding an unsaved recording, read off the UI thread.
        self._recordings: dict[str, dict] = {}
        c.event_bus.subscribe(self.state.schedule_refresh)
        services = WorkflowServices(
            self.bl, c.workflow_store, self.runner, self._log, ai=c.ai_settings
        )
        self.auto = AutomationHandlers(
            self.pm,
            self.bl,
            services,
            get_page=lambda: self.page,
            get_recording=lambda: set(self._recordings),
            on_changed=self._workflows_changed,
            # self.h is built just below; Launch goes through it like the row button.
            launch=lambda name: self.h.on_launch(name),
            is_loading=self.state.is_loading,
            add_profile=lambda on_created: self.h.open_add_dialog(on_created=on_created),
        )
        self.h = AppHandlers(
            pm=self.pm,
            bl=self.bl,
            ps=self.ps,
            state=self.state,
            get_page=lambda: self.page,
            get_refs=lambda: self.refs,
            log_fn=self._log,
            refresh_fn=self._refresh_profiles,
            get_page_profiles=self._get_page_profiles,
            workflows=services,
        )

    def run(self) -> None:
        ft.run(self._main, assets_dir=ASSETS_DIR)

    def _main(self, page: ft.Page) -> None:
        self.page = page
        configure_page(page)
        fp = ft.FilePicker()
        page.services.append(fp)
        self.clipboard = ft.Clipboard()
        page.services.append(self.clipboard)
        self._file_picker = fp
        self._build_ui()
        self.state._last_running_snapshot = self.bl.running_profile_names()
        if not self._reconcile_started:
            self._reconcile_started = True
            page.run_task(self._ui_reconcile_loop)
            page.run_task(self._watch_recordings)

    def _build_ui(self) -> None:
        """(Re)build every control; strings are read at build time."""
        assert self.page is not None
        self.refs = build_ui_refs(
            pm=self.pm,
            on_change_page=self._change_page,
            file_picker=self._file_picker,
            on_search=self._on_search,
        )
        self._filter_column = ft.Column(spacing=2)
        self._view_column = ft.Column(spacing=2)
        self._header_slot = ft.Container()
        self._primary_btn = build_primary_button(lambda _: self._on_primary())
        self.automation = AutomationPage(
            AutomationActions(
                on_run=lambda name: self.auto.open_run(workflow=name),
                on_edit=self.auto.edit,
                on_delete=self.auto.delete,
                on_stop=self.auto.stop,
                on_run_again=self.auto.run_again,
                on_log=self.auto.show_log,
                on_record=self.auto.record,
            ),
            on_search=self._on_auto_search,
        )
        self.page.title = get_string("window_title")
        self.page.controls.clear()
        root = self._build_root_layout(self.refs)
        # Before add: Flet validates on the first draw, and the primary button gets its label here.
        self._apply_view()
        self.page.add(root)
        self._restore_log()
        self._refresh_profiles()

    def _restore_log(self) -> None:
        """Refill a freshly built log pane (flush_log only returns new lines)."""
        r = self.refs
        assert r is not None
        lines = self.state.get_all_log_lines()[-6:]
        r.log_text.value = "\n".join(lines)
        r.log_column.height = max(72, len(lines) * 18 + 20)
        r.log_column.visible = bool(lines) and not self.state.log_collapsed
        r.log_toggle_btn.icon = (
            ft.Icons.KEYBOARD_ARROW_RIGHT
            if self.state.log_collapsed
            else ft.Icons.KEYBOARD_ARROW_DOWN
        )

    def _set_language(self, code: str) -> None:
        if code == current_language():
            return
        set_language(code)
        self.state.search_query = ""
        self.auto_query = ""
        self._build_ui()

    def _build_root_layout(self, r: UIRefs) -> ft.Row:
        self._filter_section = rail_section(get_string("filter_title"), self._filter_column)
        sidebar = build_sidebar(
            r.stats_text,
            r.running_text,
            r.log_text,
            r.log_column,
            r.log_toggle_btn,
            primary_button=self._primary_btn,
            on_import=self.h.on_import,
            on_export=lambda _: self.h.on_export_open(),
            on_mcp=lambda _: open_mcp_guide(self.page, self.clipboard),
            on_toggle_log=lambda _: self.h.toggle_log(),
            on_fullscreen_log=lambda _: self.h.open_log_fullscreen(),
            sections=[
                rail_section(get_string("view_title"), self._view_column),
                self._filter_section,
            ],
            language=current_language(),
            on_language=self._set_language,
        )
        self._profiles_content = build_content_area(
            r.content_subtitle,
            r.profile_list_area,
            r.prev_btn,
            r.next_btn,
            r.page_label,
            r.bulk_bar,
            r.search_field,
            header_slot=self._header_slot,
        )
        return ft.Row(
            expand=True,
            spacing=0,
            controls=[
                sidebar,
                self._profiles_content,
                self.automation.control,
            ],
        )

    # --- views ------------------------------------------------------------------

    def _apply_view(self) -> None:
        profiles = self.view == "profiles"
        self._profiles_content.visible = profiles
        self.automation.control.visible = not profiles
        self._filter_section.visible = profiles
        primary_for(self._primary_btn, self.view)

    def _on_view(self, view: str) -> None:
        if view == self.view:
            return
        self.view = view
        self._workflows = None
        self.automation.invalidate()
        self._apply_view()
        self._refresh_profiles()

    def _on_primary(self) -> None:
        if self.view == "profiles":
            self.h.open_add_dialog()
        else:
            self.auto.record()

    def _on_auto_search(self, query: str) -> None:
        self.auto_query = query
        self._refresh_profiles()

    def _workflows_changed(self) -> None:
        """A workflow was saved, deleted or started here: read them again and redraw."""
        self._workflows = None
        self.state.schedule_refresh()

    def _workflow_list(self) -> list[dict]:
        now = time.monotonic()
        if self._workflows is None or now - self._workflows_read >= WORKFLOWS_TTL_SECONDS:
            try:
                self._workflows = self.store.list()
            except Exception as e:
                logger.error("Could not read workflows: %s", e)
                self._workflows = self._workflows or []
            self._workflows_read = now
        return self._workflows

    # --- profiles ---------------------------------------------------------------

    def _on_search(self, query: str) -> None:
        self.state.search_query = query.strip().lower()
        self.state.current_page = 1
        self._refresh_profiles()

    def _on_filter(self, fid: str) -> None:
        self.filter = fid
        self.state.current_page = 1
        self._refresh_profiles()

    def _filter_tests(self) -> dict:
        return {
            "all": lambda p: True,
            "running": lambda p: self.bl.is_running(p.name),
            "proxy": lambda p: bool(p.proxy),
            "direct": lambda p: not p.proxy,
            "chrome": lambda p: p.engine == "chrome",
        }

    def _get_page_profiles(self) -> tuple[list, list, int]:
        all_profiles = self.pm.list_profiles()
        test = self._filter_tests().get(self.filter, lambda p: True)
        all_profiles = [p for p in all_profiles if test(p)]
        if q := self.state.search_query:
            all_profiles = [
                p for p in all_profiles if q in p.name.lower() or q in (p.proxy or "").lower()
            ]
        total = max(1, (len(all_profiles) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        self.state.current_page = min(self.state.current_page, total)
        start = (self.state.current_page - 1) * ITEMS_PER_PAGE
        return all_profiles, all_profiles[start : start + ITEMS_PER_PAGE], total

    def _refresh_profiles(self) -> None:
        """The app's one refresh: the rail, then whichever page shows."""
        assert self.refs is not None
        self._update_stats()
        self._flush_log()

        all_names = set(self.pm.profiles)
        for stale in self.state.selected_names() - all_names:
            self.state.toggle_selection(stale)

        running = self.bl.running_profile_names()
        # A failure mark lasts until the profile runs again or is gone.
        self.state.failed.intersection_update(all_names - running)
        for name in running - set(self._live_since):
            self._live_since[name] = time.strftime("%H:%M")
        for name in set(self._live_since) - running:
            del self._live_since[name]

        runs = self.runner.list(log=False)
        view_counts = {
            "automation": sum(1 for run in runs if run["active"]),
            "profiles": len(all_names),
        }
        # Rebuilt only on a change, so the nav is not swapped under the cursor.
        view_key = (self.view, view_counts, current_language())
        if view_key != self._view_key or not self._view_column.controls:
            self._view_key = view_key
            self._view_column.controls = build_view_buttons(self.view, view_counts, self._on_view)
        if self.view == "profiles":
            self._refresh_profile_table({run["profile"]: run for run in runs})
        else:
            self.automation.render(
                AutomationData(self._workflow_list(), runs, running, self.auto_query)
            )
        self._safe_update()

    def _refresh_profile_table(self, runs: dict[str, dict]) -> None:
        r = self.refs
        assert r is not None
        all_profiles, page_profiles, total_pages = self._get_page_profiles()
        everything = self.pm.list_profiles()
        tests = self._filter_tests()
        self._filter_column.controls = build_filter_buttons(
            self.filter,
            {fid: sum(1 for p in everything if test(p)) for fid, test in tests.items()},
            self._on_filter,
        )
        names = [p.name for p in page_profiles]
        all_sel = bool(names) and all(self.state.is_selected(n) for n in names)
        any_sel = any(self.state.is_selected(n) for n in names)
        self._header_slot.content = (
            build_header_row(
                all_sel,
                any_sel,
                lambda select: self.h.on_select_all_page() if select else self.h.on_deselect_page(),
            )
            if page_profiles
            else None
        )

        r.profile_list_area.controls = (
            [
                build_profile_card(
                    p,
                    self.state.is_loading(p.name),
                    self.bl.is_running(p.name),
                    self.h.on_launch,
                    self.h.on_edit,
                    self.h.on_delete,
                    is_selected=self.state.is_selected(p.name),
                    on_select=self.h.on_toggle_select,
                    on_cookies=self.h.on_cookies,
                    device=self._device_label(p.name),
                    since=self._live_since.get(p.name, ""),
                    failed=p.name in self.state.failed,
                    on_workflows=self.h.on_workflows,
                    on_clone=self.h.on_clone,
                    activity=self._activity(p.name, runs),
                )
                for p in page_profiles
            ]
            if page_profiles
            else [self._build_empty_or_no_results()]
        )
        rebuild_bulk_bar(
            r.bulk_bar,
            self.state,
            page_profiles,
            {
                "launch": self.h.on_bulk_launch,
                "run": lambda: self.auto.open_run(profiles=self.state.selected_names()),
                "stop": self.h.on_bulk_stop,
                "delete": self.h.on_bulk_delete,
                "select_page": self.h.on_select_all_page,
                "deselect_page": self.h.on_deselect_page,
                "clear": self.h.on_clear_selection,
            },
        )
        self._set_subtitle(r.content_subtitle)
        r.page_label.value = get_string(
            "page_of",
            current=self.state.current_page,
            total=total_pages,
        )
        r.prev_btn.disabled = self.state.current_page <= 1
        r.next_btn.disabled = self.state.current_page >= total_pages

    def _activity(self, name: str, runs: dict[str, dict]) -> str:
        rec = self._recordings.get(name)
        if rec and rec.get("recording"):
            return "● " + get_string("wf_recording", count=rec.get("step_count", 0))
        run = runs.get(name)
        if run and run["active"]:
            return get_string(
                "wf_row_running",
                workflow=run["workflow"],
                step=run["step"],
                total=run["step_total"],
            )
        return ""

    async def _watch_recordings(self) -> None:
        """Follow recordings started anywhere (this app, the web panel, the API)."""
        while self.page:
            try:
                found = await asyncio.to_thread(recording.overview, self.bl, list(self.pm.profiles))
                current = {r["profile"]: r for r in found if r.get("recording")}
                if current != self._recordings:
                    self._recordings = current
                    self.state.schedule_refresh()
            except Exception as e:
                logger.debug("Recording status unavailable: %s", e)
            await asyncio.sleep(2)

    @staticmethod
    def _device_label(name: str) -> str:
        info = fingerprint.summary(os.path.join(DATA_DIR, name))
        if not info:
            return ""
        cpu = f"{info['hardware_concurrency']} CPU"
        return f"{info['screen']} · {cpu}" if info.get("screen") else cpu

    def _build_empty_or_no_results(self) -> ft.Control:
        if self.pm.profiles:
            return ft.Container(
                padding=ft.Padding.symmetric(vertical=56, horizontal=24),
                alignment=ft.Alignment(0, 0),
                content=ft.Column(
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                    controls=[
                        ft.Text(
                            get_string("no_search_results", query=self.state.search_query)
                            if self.state.search_query
                            else get_string("no_filter_results"),
                            size=14,
                            color=COLORS["text_sub"],
                        ),
                        ft.OutlinedButton(
                            get_string("clear_filters"),
                            on_click=lambda _: self._clear_filters(),
                        ),
                    ],
                ),
            )
        return build_empty_state(lambda _: self.h.open_add_dialog())

    def _clear_filters(self) -> None:
        self.filter = "all"
        self.state.search_query = ""
        if self.refs and self.refs.search_field is not None:
            self.refs.search_field.value = ""
        self._refresh_profiles()

    def _change_page(self, delta: int) -> None:
        self.state.current_page += delta
        self._refresh_profiles()

    def _set_subtitle(self, text: ft.Text) -> None:
        """ "10 profile · 2 đang chạy", the running count in stamp violet."""
        c, r = len(self.pm.profiles), self.bl.running_count()
        head = get_string("profiles_configured", count=c) + " · "
        text.value = None
        text.spans = (
            [
                ft.TextSpan(head),
                ft.TextSpan(str(r), ft.TextStyle(color=COLORS["live"], font_family=FONT_SEMIBOLD)),
                ft.TextSpan(" " + get_string("profiles_running_suffix")),
            ]
            if r
            else [ft.TextSpan(head + get_string("profiles_none_running"))]
        )

    def _update_stats(self) -> None:
        r = self.refs
        if r:
            cnt = self.bl.running_count()
            r.stats_text.value = get_string(
                "total_profiles",
                count=len(self.pm.profiles),
            )
            r.running_text.value = (
                get_string("browsers_running", count=cnt)
                if cnt
                else get_string("no_active_sessions")
            )

    def _log(self, message: str) -> None:
        logger.info(message)
        if self.state.add_log(message):
            self.state.schedule_refresh()

    def _flush_log(self) -> None:
        text = self.state.flush_log()
        if text is not None and self.refs:
            lines = text.split("\n")
            sidebar_lines = lines[-6:]
            self.refs.log_text.value = "\n".join(sidebar_lines)
            self.refs.log_column.height = max(72, len(sidebar_lines) * 18 + 20)
            self.refs.log_column.visible = bool(sidebar_lines) and not self.state.log_collapsed

    def _safe_update(self) -> None:
        if not self.page:
            return
        try:
            with self.state._ui_update_lock:
                self.page.update()
        except Exception as e:
            logger.error("Error updating UI: %s", e)

    def _auto_due(self) -> bool:
        """Every AUTO_POLL_SECONDS while a run is active and the Automation page shows."""
        now = time.monotonic()
        if self.view != "automation" or now - self._auto_tick < AUTO_POLL_SECONDS:
            return False
        self._auto_tick = now
        return any(run["active"] for run in self.runner.list(log=False))

    async def _ui_reconcile_loop(self) -> None:
        while self.page:
            try:
                running_now = self.bl.running_profile_names()
                changed = running_now != self.state._last_running_snapshot
                if changed:
                    self.state._last_running_snapshot = running_now
                if changed or self.state.consume_refresh() or self._auto_due():
                    self._refresh_profiles()
            except Exception as e:
                logger.error("Error in UI reconcile loop: %s", e)
            await asyncio.sleep(0.12)
