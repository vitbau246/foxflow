"""Create or edit a trigger: when it fires, which profiles open and which workflows run.

The "When" part changes with the kind of trigger: the webhook URL (with Copy and
New key), the clipboard pattern, the watched folder, or the schedule.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft
from pydantic import ValidationError

from ...core.strings import get_string
from ...services.automation.model import TRIGGER_TYPES, Automation, Trigger, new_id, new_key
from ...services.automation.store import AutomationError, AutomationStore
from ..theme.colors import COLORS, FONT_BOLD, FONT_DATA, FONT_SEMIBOLD
from ..theme.styles import ACCENT_STYLE, DLG_FIELD_KWARGS, OUTLINE_STYLE

_LINE_HEIGHT = 40


def hook_url(base: str, automation: dict[str, Any]) -> str:
    return f"{base}/{automation['id']}?key={automation['trigger']['key']}"


def open_trigger_editor(
    page: ft.Page,
    store: AutomationStore,
    profiles: list[str],
    workflows: list[str],
    automation_id: str | None = None,
    on_saved: Callable[[str], None] | None = None,
    hook_base: str = "http://127.0.0.1:8000/api/v1/hooks",
    copy: Callable[[str], Any] | None = None,
) -> None:
    """`hook_base` is the webhook URL without the trigger's id; `copy(text)` copies it."""
    existing = store.get(automation_id) if automation_id else None
    new = existing is None
    data: dict[str, Any] = (
        existing.model_dump()
        if existing
        else {
            "id": new_id(),
            "name": "",
            "enabled": True,
            "trigger": Trigger().model_dump(),
            "profiles": [],
            "workflows": workflows[:1],
            "variables": {},
            "close_profile": True,
        }
    )
    trigger = data["trigger"]
    chosen = set(data["profiles"])
    chain: list[str] = list(data["workflows"])

    error_text = ft.Text("", size=12.5, color=COLORS["error"], visible=False, selectable=True)
    name = ft.TextField(value=data["name"], autofocus=new, **DLG_FIELD_KWARGS)
    enabled = ft.Checkbox(label=get_string("trg_enabled"), value=data["enabled"])
    close_profile = ft.Checkbox(label=get_string("trg_close"), value=data["close_profile"])
    when_box = ft.Column(spacing=8, tight=True)
    chain_box = ft.Column(spacing=6, tight=True)

    def update() -> None:
        with contextlib.suppress(Exception):
            page.update()

    def field(key: str, value: Any, hint: str = "", data_font: bool = True) -> ft.TextField:
        def on_change(e: ft.ControlEvent) -> None:
            trigger[key] = e.control.value or ""

        return ft.TextField(
            value="" if value is None else str(value),
            hint_text=hint,
            text_style=ft.TextStyle(font_family=FONT_DATA, size=13) if data_font else None,
            on_change=on_change,
            **DLG_FIELD_KWARGS,
        )

    def note(text: str) -> ft.Text:
        return ft.Text(text, size=12, color=COLORS["text_dim"])

    def draw_when() -> None:
        kind = trigger["type"]
        controls: list[ft.Control] = []
        if kind == "webhook":
            url = ft.Text(
                hook_url(hook_base, data),
                size=12,
                font_family=FONT_DATA,
                color=COLORS["text_main"],
                selectable=True,
            )

            async def do_copy(_: ft.ControlEvent) -> None:
                if copy:
                    result = copy(url.value or "")
                    if hasattr(result, "__await__"):
                        await result
                copy_btn.content = get_string("trg_copied")
                update()

            def new_key_click(_: ft.ControlEvent) -> None:
                trigger["key"] = new_key()
                draw_when()
                update()

            copy_btn = ft.TextButton(get_string("trg_copy"), icon=ft.Icons.COPY, on_click=do_copy)
            controls += [
                _label(get_string("trg_webhook_url")),
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                    border_radius=8,
                    bgcolor=COLORS["paper_sunk"],
                    content=url,
                ),
                ft.Row(
                    spacing=4,
                    controls=[
                        copy_btn,
                        ft.TextButton(
                            get_string("trg_new_key"), icon=ft.Icons.KEY, on_click=new_key_click
                        ),
                    ],
                ),
                note(get_string("trg_webhook_hint")),
            ]
            if new:
                controls.append(note(get_string("trg_webhook_save_first")))
        elif kind == "clipboard":
            controls += [
                _label(get_string("trg_clip_pattern")),
                field("pattern", trigger["pattern"], r"https?://"),
                note(get_string("trg_clip_hint")),
            ]
        elif kind == "file":
            controls += [
                _label(get_string("trg_folder")),
                field("folder", trigger["folder"]),
                _label(get_string("trg_file_pattern")),
                field("pattern", trigger["pattern"], "*.csv"),
                note(get_string("trg_file_hint")),
            ]
        else:

            def on_every(e: ft.ControlEvent) -> None:
                raw = (e.control.value or "").strip()
                trigger["every_minutes"] = int(raw) if raw.isdigit() else 0

            def on_at(e: ft.ControlEvent) -> None:
                trigger["at"] = [t.strip() for t in (e.control.value or "").split(",") if t.strip()]

            every = ft.TextField(
                value=str(trigger["every_minutes"] or 0),
                input_filter=ft.NumbersOnlyInputFilter(),
                on_change=on_every,
                **DLG_FIELD_KWARGS,
            )
            at = ft.TextField(
                value=", ".join(trigger["at"]),
                hint_text="08:30, 17:00",
                on_change=on_at,
                **DLG_FIELD_KWARGS,
            )
            controls += [
                ft.Row(
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Container(
                            expand=1,
                            content=ft.Column(
                                spacing=6,
                                tight=True,
                                controls=[_label(get_string("trg_every")), every],
                            ),
                        ),
                        ft.Container(
                            expand=2,
                            content=ft.Column(
                                spacing=6, tight=True, controls=[_label(get_string("trg_at")), at]
                            ),
                        ),
                    ],
                )
            ]
        when_box.controls = controls

    def on_type(e: ft.ControlEvent) -> None:
        trigger["type"] = e.control.value
        draw_when()
        update()

    def draw_chain() -> None:
        def pick(i: int, value: str | None) -> None:
            if value:
                chain[i] = value

        def drop(i: int) -> None:
            del chain[i]
            draw_chain()
            update()

        def add(_: ft.ControlEvent) -> None:
            unused = [w for w in workflows if w not in chain]
            if workflows:
                chain.append(unused[0] if unused else workflows[0])
            draw_chain()
            update()

        rows: list[ft.Control] = []
        for i, wf in enumerate(chain):
            rows.append(
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(
                            f"{i + 1}.",
                            width=22,
                            size=12.5,
                            font_family=FONT_DATA,
                            color=COLORS["text_dim"],
                        ),
                        ft.Dropdown(
                            value=wf,
                            text_size=13.5,
                            expand=True,
                            bgcolor=COLORS["input_bg"],
                            border_color=COLORS["rule_strong"],
                            focused_border_color=COLORS["sidebar"],
                            border_radius=8,
                            on_select=lambda e, i=i: pick(i, e.control.value),
                            options=[ft.dropdown.Option(w) for w in workflows],
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE,
                            icon_size=18,
                            icon_color=COLORS["text_sub"],
                            tooltip=get_string("run_remove_workflow"),
                            on_click=lambda _, i=i: drop(i),
                        ),
                    ],
                )
            )
        rows.append(
            ft.Row(
                controls=[
                    ft.TextButton(
                        get_string("run_add_workflow"),
                        icon=ft.Icons.ADD,
                        style=ft.ButtonStyle(color=COLORS["text_sub"]),
                        on_click=add,
                    )
                ]
            )
        )
        chain_box.controls = rows

    def toggle(profile: str, on: bool) -> None:
        if on:
            chosen.add(profile)
        else:
            chosen.discard(profile)

    def profile_line(profile: str) -> ft.Container:
        return ft.Container(
            height=_LINE_HEIGHT,
            padding=ft.Padding.only(left=4, right=12),
            border=ft.Border.only(bottom=ft.BorderSide(1, COLORS["card_border"])),
            content=ft.Row(
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Checkbox(
                        value=profile in chosen,
                        on_change=lambda e, p=profile: toggle(p, bool(e.control.value)),
                    ),
                    ft.Text(
                        profile,
                        expand=True,
                        size=14,
                        font_family=FONT_SEMIBOLD,
                        color=COLORS["text_main"],
                        no_wrap=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        tooltip=profile,
                    ),
                ],
            ),
        )

    def save(_: ft.ControlEvent) -> None:
        problem = ""
        if not (name.value or "").strip():
            problem = get_string("trg_need_name")
        elif not chosen:
            problem = get_string("trg_need_profile")
        elif not chain:
            problem = get_string("trg_need_workflow")
        automation = None
        if not problem:
            payload = {
                **data,
                "name": (name.value or "").strip(),
                "enabled": bool(enabled.value),
                "close_profile": bool(close_profile.value),
                # In the order of the profile list, not the order they were ticked.
                "profiles": [p for p in profiles if p in chosen] + sorted(chosen - set(profiles)),
                "workflows": chain,
                "trigger": trigger,
            }
            try:
                automation = store.save(Automation.model_validate(payload), create=new)
            except ValidationError as e:
                first = e.errors()[0]
                problem = first["msg"].removeprefix("Value error, ")
            except AutomationError as e:
                problem = str(e)
        if problem or automation is None:
            error_text.value = problem
            error_text.visible = True
            update()
            return
        close()
        if on_saved:
            on_saved(automation.name)

    def close(_: ft.ControlEvent | None = None) -> None:
        with contextlib.suppress(Exception):
            page.pop_dialog()

    draw_when()
    draw_chain()
    kind = ft.Dropdown(
        value=trigger["type"],
        text_size=13.5,
        bgcolor=COLORS["input_bg"],
        border_color=COLORS["rule_strong"],
        focused_border_color=COLORS["sidebar"],
        border_radius=8,
        on_select=on_type,
        options=[ft.dropdown.Option(t, get_string(f"trg_type_{t}")) for t in TRIGGER_TYPES],
    )
    checklist = ft.Container(
        bgcolor=COLORS["card_bg"],
        border=ft.Border.all(1, COLORS["card_border"]),
        border_radius=9,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=ft.Column(
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            height=min(200, max(1, len(profiles)) * (_LINE_HEIGHT + 1)),
            controls=[profile_line(p) for p in profiles],
        ),
    )
    dlg = ft.AlertDialog(
        modal=True,
        bgcolor=COLORS["card_bg"],
        shape=ft.RoundedRectangleBorder(radius=12),
        title_padding=ft.Padding.only(left=24, right=24, top=22, bottom=0),
        content_padding=ft.Padding.only(left=24, right=24, top=10, bottom=8),
        actions_padding=ft.Padding.only(left=24, right=24, top=8, bottom=20),
        title=ft.Column(
            spacing=4,
            tight=True,
            controls=[
                ft.Text(
                    get_string("trg_title_new" if new else "trg_title_edit"),
                    size=19,
                    font_family=FONT_BOLD,
                    color=COLORS["text_main"],
                ),
                ft.Text(get_string("trg_subtitle"), size=13.5, color=COLORS["text_sub"]),
            ],
        ),
        content=ft.Container(
            width=600,
            content=ft.Column(
                tight=True,
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    _label(get_string("trg_name")),
                    name,
                    enabled,
                    _heading(get_string("trg_when")),
                    kind,
                    when_box,
                    _heading(get_string("trg_then")),
                    _label(get_string("trg_profiles_label")),
                    checklist,
                    _label(get_string("trg_workflows_label")),
                    chain_box,
                    close_profile,
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                        border_radius=8,
                        bgcolor=COLORS["paper_sunk"],
                        content=ft.Text(
                            get_string("trg_vars_hint"), size=12.5, color=COLORS["text_sub"]
                        ),
                    ),
                    error_text,
                ],
            ),
        ),
        actions=[
            ft.OutlinedButton(get_string("cancel"), style=OUTLINE_STYLE, on_click=close),
            ft.Button(
                get_string("save_changes"), icon=ft.Icons.SAVE, style=ACCENT_STYLE, on_click=save
            ),
        ],
    )
    page.show_dialog(dlg)


def _label(text: str) -> ft.Text:
    return ft.Text(text, size=12.5, font_family=FONT_SEMIBOLD, color=COLORS["text_sub"])


def _heading(text: str) -> ft.Container:
    return ft.Container(
        padding=ft.Padding.only(top=8),
        content=ft.Text(text, size=14, font_family=FONT_SEMIBOLD, color=COLORS["text_main"]),
    )
