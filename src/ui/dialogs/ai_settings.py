"""AI settings for workflow "AI text" steps: an OpenAI-compatible API."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable

import flet as ft

from ...core.strings import get_string
from ...services.ai.client import AIError, generate
from ...services.ai.settings import AISettings, AISettingsStore
from ...services.workflow.model import uses_ai
from ...services.workflow.store import WorkflowStore
from ...utils import net
from ..theme.colors import COLORS, FONT_BOLD, FONT_DATA, FONT_SEMIBOLD
from ..theme.styles import ACCENT_STYLE, DLG_FIELD_KWARGS, OUTLINE_STYLE

_DATA = ft.TextStyle(font_family=FONT_DATA, size=13)


def _field(label: str, control: ft.Control, hint: str | None = None) -> ft.Column:
    return ft.Column(
        spacing=6,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            ft.Container(
                padding=ft.Padding.only(top=8),
                content=ft.Text(
                    label, size=12.5, font_family=FONT_SEMIBOLD, color=COLORS["text_sub"]
                ),
            ),
            control,
            *([ft.Text(hint, size=12, color=COLORS["text_dim"])] if hint else []),
        ],
    )


def ai_setup_needed(
    page: ft.Page,
    ai: AISettingsStore | None,
    store: WorkflowStore,
    workflow: str,
    log: Callable[[str], None],
) -> str | None:
    """Before a run: None when `workflow` needs no AI or AI is set up.

    Otherwise the run would be refused, so this logs why, opens the AI settings
    and returns the message for the caller to show.
    """
    if ai is None:
        return None
    try:
        found = store.get(workflow)
        if found is None or not uses_ai(found) or ai.load().api_key:
            return None
    except Exception:  # an unreadable workflow: the run reports it
        return None
    message = get_string("wf_needs_ai")
    log(message)
    open_ai_settings_dialog(page, ai)
    return message


def open_ai_settings_dialog(
    page: ft.Page, store: AISettingsStore, on_saved: Callable[[], None] | None = None
) -> None:
    shown = store.public()
    current = store.load()
    key = ft.TextField(
        password=True,
        can_reveal_password=True,
        hint_text=shown["key_hint"] or "sk-...",
        disabled=shown["key_from_env"],
        text_style=_DATA,
        **DLG_FIELD_KWARGS,
    )
    base_url = ft.TextField(value=current.base_url, text_style=_DATA, **DLG_FIELD_KWARGS)
    model = ft.TextField(value=current.model, text_style=_DATA, **DLG_FIELD_KWARGS)
    system = ft.TextField(
        value=current.system_prompt, multiline=True, min_lines=2, max_lines=5, **DLG_FIELD_KWARGS
    )
    temperature = ft.TextField(
        value="" if current.temperature is None else str(current.temperature),
        keyboard_type=ft.KeyboardType.NUMBER,
        text_style=_DATA,
        **DLG_FIELD_KWARGS,
    )
    message = ft.Text("", size=12.5, visible=False, selectable=True)

    def say(text: str, ok: bool) -> None:
        message.value = text
        message.color = COLORS["success"] if ok else COLORS["error"]
        message.visible = True
        with contextlib.suppress(Exception):
            page.update()

    def build() -> AISettings:
        raw = (temperature.value or "").strip().replace(",", ".")
        return AISettings(
            api_key=(key.value or "").strip() or store.load().api_key,
            base_url=(base_url.value or "").strip(),
            model=(model.value or "").strip(),
            system_prompt=system.value or "",
            temperature=float(raw) if raw else None,
        )

    def save() -> bool:
        try:
            store.save(build())
        except ValueError as e:
            say(str(e).splitlines()[-1], ok=False)
            return False
        key.value = ""
        if on_saved:
            on_saved()
        return True

    def on_save(_: ft.ControlEvent) -> None:
        if save():
            page.pop_dialog()

    async def on_test(e: ft.ControlEvent) -> None:
        if not save():
            return
        e.control.disabled = True
        say(get_string("ai_testing"), ok=True)
        try:
            text = await asyncio.to_thread(generate, store.load(), "Say hello in five words.", 60)
            say(text, ok=True)
        except AIError as err:
            say(str(err), ok=False)
        finally:
            e.control.disabled = False
            with contextlib.suppress(Exception):
                page.update()

    def on_remove(_: ft.ControlEvent) -> None:
        settings = store.load()
        settings.api_key = ""
        store.save(settings)
        key.hint_text = "sk-..."
        say(get_string("ai_saved"), ok=True)
        if on_saved:
            on_saved()

    key_hint = (
        get_string("ai_key_env")
        if shown["key_from_env"]
        else get_string("ai_key_keep", hint=shown["key_hint"])
        if shown["configured"]
        else None
    )
    dlg = ft.AlertDialog(
        modal=True,
        bgcolor=COLORS["card_bg"],
        shape=ft.RoundedRectangleBorder(radius=12),
        title_padding=ft.Padding.only(left=24, right=24, top=22, bottom=0),
        content_padding=ft.Padding.only(left=24, right=24, top=4, bottom=8),
        actions_padding=ft.Padding.only(left=24, right=24, top=8, bottom=20),
        title=ft.Column(
            spacing=4,
            tight=True,
            controls=[
                ft.Text(
                    get_string("ai_title"),
                    size=19,
                    font_family=FONT_BOLD,
                    color=COLORS["text_main"],
                ),
                ft.Text(get_string("ai_subtitle"), size=13.5, color=COLORS["text_sub"]),
            ],
        ),
        content=ft.Container(
            width=520,
            content=ft.Column(
                tight=True,
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    _field(get_string("ai_key"), key, key_hint),
                    *(
                        [
                            ft.Row(
                                controls=[
                                    ft.TextButton(
                                        get_string("ai_remove_key"),
                                        style=ft.ButtonStyle(color=COLORS["text_sub"]),
                                        on_click=on_remove,
                                    )
                                ]
                            )
                        ]
                        if shown["configured"] and not shown["key_from_env"]
                        else []
                    ),
                    ft.Row(
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Container(
                                expand=3, content=_field(get_string("ai_base_url"), base_url)
                            ),
                            ft.Container(expand=2, content=_field(get_string("ai_model"), model)),
                        ],
                    ),
                    _field(get_string("ai_system"), system),
                    _field(
                        get_string("ai_temperature"),
                        temperature,
                        get_string("ai_temperature_hint"),
                    ),
                    ft.Container(
                        margin=ft.Margin.only(top=8),
                        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                        border_radius=8,
                        bgcolor=COLORS["warn_tint"],
                        content=ft.Row(
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                            controls=[
                                ft.Icon(
                                    ft.Icons.WARNING_AMBER_ROUNDED,
                                    size=16,
                                    color=COLORS["warning"],
                                ),
                                ft.Text(
                                    get_string("ai_privacy"),
                                    size=12.5,
                                    color=COLORS["warn_text"],
                                    expand=True,
                                ),
                            ],
                        ),
                    ),
                    _network_note(),
                    message,
                ],
            ),
        ),
        actions=[
            ft.OutlinedButton(get_string("ai_test"), style=OUTLINE_STYLE, on_click=on_test),
            ft.TextButton(
                get_string("cancel"),
                style=ft.ButtonStyle(color=COLORS["text_sub"]),
                on_click=lambda _: page.pop_dialog(),
            ),
            ft.Button(
                get_string("save_changes"), icon=ft.Icons.SAVE, style=ACCENT_STYLE, on_click=on_save
            ),
        ],
    )
    page.show_dialog(dlg)


def _network_note() -> ft.Container:
    """How AI requests leave this machine, and where to set a proxy if they need one."""
    proxy = net.proxy_label()
    return ft.Container(
        margin=ft.Margin.only(top=8),
        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        border_radius=8,
        bgcolor=COLORS["paper_sunk"],
        content=ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Icon(ft.Icons.PUBLIC, size=16, color=COLORS["text_sub"]),
                ft.Text(
                    get_string("ai_net_proxy", proxy=proxy)
                    if proxy
                    else get_string("ai_net_direct"),
                    size=12.5,
                    color=COLORS["text_sub"],
                    expand=True,
                ),
            ],
        ),
    )
