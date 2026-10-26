"""Record what the user does in a running profile's browser as workflow steps.

Runs inside the runner process, next to the control server. recorder.js is
injected into every frame and reports trusted clicks, typing, selections, key
presses and scrolls through a Playwright binding; navigations come from the
browser itself. Text the user selects, or an element the mouse rests on, is
offered as a "Get text" step; the page asks here for the variable name to
suggest (get_text_name) and sends the step once the user accepts. The steps so far are written to recording.json in the profile
directory after every change, so closing the browser does not lose them.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import pathlib
import time
from typing import Any
from urllib.parse import urlsplit

from ..workflow.model import VARIABLE_NAME, new_step_id

RECORDING_FILE = "recording.json"
BINDING = "__foxflowRecord"
_SCRIPT = (pathlib.Path(__file__).parent / "recorder.js").read_text(encoding="utf-8")

# A navigation this soon after a click or key press is that action's result.
NAV_WINDOW_S = 3.0
# Recorded pauses become the steps' delays, within these bounds.
MIN_DELAY_MS, MAX_DELAY_MS = 200, 5_000
MAX_RECORDED_STEPS = 500


def recording_path(profile_dir: str) -> pathlib.Path:
    return pathlib.Path(profile_dir) / RECORDING_FILE


def load_draft(profile_dir: str) -> dict[str, Any] | None:
    """The last recording saved for a profile, or None."""
    path = recording_path(profile_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        return None
    return data


def discard_draft(profile_dir: str) -> None:
    with contextlib.suppress(OSError):
        recording_path(profile_dir).unlink()


def _http(url: str) -> bool:
    return urlsplit(url).scheme in ("http", "https")


def _delay(gap_s: float) -> int:
    ms = round(gap_s * 10) * 100  # whole tenths of a second read better in the editor
    return int(min(MAX_DELAY_MS, max(MIN_DELAY_MS, ms)))


def _label(event: dict[str, Any]) -> str:
    """What the step acts on, for people: the button's text, the field's name...

    The interfaces show it next to the translated action ("Click", "Bấm").
    """
    kind = event["type"]
    hint = str(event.get("hint") or event.get("tag") or "")
    if kind == "select":
        return str(event.get("option") or event.get("value") or hint)
    if kind == "press":
        key = str(event.get("key", ""))
        return f"{key} ({hint})" if hint else key
    return hint


def _short_url(url: str) -> str:
    parts = urlsplit(url)
    text = (parts.hostname or "") + (parts.path if parts.path != "/" else "")
    return text[:80]


class Recorder:
    """One per browser context; start() and stop() may be called repeatedly."""

    def __init__(self, context: Any, profile_dir: str | None = None) -> None:
        self._context = context
        self._profile_dir = profile_dir
        self._installed = False
        self.active = False
        self.steps: list[dict[str, Any]] = []
        self.started_at = ""
        self._tabs: list[Any] = []
        self._current_tab = 0
        self._last_at = 0.0
        self._last_action: dict[str, Any] | None = None
        self._last_action_at = 0.0
        # Language of the "Get text" offer shown in the page.
        self.lang = "en"

    # --- lifecycle --------------------------------------------------------

    async def start(self, start_page: Any, lang: str = "en") -> dict[str, Any]:
        self.lang = lang if lang in ("en", "vi") else "en"
        if not self._installed:
            await self._context.expose_binding(BINDING, self._on_binding)
            await self._context.add_init_script(script=_SCRIPT)
            self._context.on("page", self._on_page)
            for page in self._context.pages:
                self._watch(page)
            self._installed = True
        self.steps = []
        self._tabs = [start_page]
        self._current_tab = 0
        self._last_at = time.monotonic()
        self._last_action = None
        self._last_action_at = 0.0
        self.started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.active = True
        if _http(start_page.url):
            self._append(
                {"action": "navigate", "value": start_page.url, "label": _short_url(start_page.url)}
            )
            self.steps[0]["delay_ms"] = 0
            self._mark_action()
        else:
            self._save()
        # Pages that were already open never ran the init script.
        for page in self._open_pages():
            for frame in page.frames:
                with contextlib.suppress(Exception):
                    await frame.evaluate(_SCRIPT)
        return self.status()

    async def stop(self) -> dict[str, Any]:
        if self.active:
            for page in self._open_pages():
                for frame in page.frames:
                    # Sends the field being typed in, then stops listening.
                    with contextlib.suppress(Exception):
                        await frame.evaluate(
                            "() => window.__foxflowRecorder && window.__foxflowRecorder.stop()"
                        )
            await asyncio.sleep(0.1)
        self.active = False
        self._save()
        return {**self.status(), "steps": list(self.steps)}

    def status(self) -> dict[str, Any]:
        return {
            "recording": self.active,
            "started_at": self.started_at,
            "step_count": len(self.steps),
            "recent": [f"{s['action']} {s['label']}".strip() for s in self.steps[-5:]],
        }

    # --- browser events ---------------------------------------------------

    def _open_pages(self) -> list[Any]:
        return [p for p in self._context.pages if not p.is_closed()]

    def _watch(self, page: Any) -> None:
        page.on("framenavigated", lambda frame, page=page: self._on_navigated(page, frame))

    def _on_page(self, page: Any) -> None:
        self._watch(page)
        if self.active and page not in self._tabs:
            self._tabs.append(page)

    def _tab_of(self, page: Any) -> int:
        if page not in self._tabs:
            self._tabs.append(page)
        return self._tabs.index(page)

    def _on_navigated(self, page: Any, frame: Any) -> None:
        if not self.active or frame is not page.main_frame or not _http(frame.url):
            return
        url = frame.url
        now = time.monotonic()
        tab = self._tab_of(page)
        last = self.steps[-1] if self.steps else None
        if (
            last is not None
            and last is self._last_action
            and now - self._last_action_at < NAV_WINDOW_S
            and last.get("_tab") == tab
        ):
            # Where the click / Enter / opened URL led; redirects keep the last stop.
            last["expect_url"] = url
            self._save()
            return
        if last and last["action"] == "navigate" and last["value"] == url:
            return
        self._switch_to(tab)
        self._append({"action": "navigate", "value": url, "label": _short_url(url)}, tab)
        self._mark_action()

    async def _on_binding(self, source: dict[str, Any], event: Any) -> Any:
        if not isinstance(event, dict) or event.get("type") == "ping":
            return self.active
        if event.get("type") == "get_text_name":
            return {"name": self.next_text_name(), "lang": self.lang} if self.active else None
        if not self.active or len(self.steps) >= MAX_RECORDED_STEPS:
            return False
        page = source.get("page")
        frame = source.get("frame")
        if page is None:
            return False
        tab = self._tab_of(page)
        frame_ref = ""
        if frame is not None and frame is not page.main_frame:
            frame_ref = frame.name or frame.url
        self._record(event, tab, frame_ref)
        return True

    def next_text_name(self) -> str:
        """text1, text2...: the first not yet saved into by this recording."""
        used = {s.get("save_as") for s in self.steps}
        n = 1
        while f"text{n}" in used:
            n += 1
        return f"text{n}"

    # --- turning events into steps ----------------------------------------

    def _record(self, event: dict[str, Any], tab: int, frame: str) -> None:
        kind = event.get("type")
        selectors = [s for s in event.get("selectors") or [] if isinstance(s, str)][:6]
        step: dict[str, Any] = {
            "selectors": selectors,
            "frame": frame,
            "label": _label(event)[:300],
        }
        if kind == "fill":
            value = str(event.get("value", ""))
            last = self.steps[-1] if self.steps else None
            if (
                last
                and last["action"] == "fill"
                and last.get("_tab") == tab
                and last["frame"] == frame
                and last["selectors"][:1] == selectors[:1]
            ):
                last["value"] = value
                self._save()
                return
            keystrokes = int(event.get("keystrokes") or 0)
            typing_ms = float(event.get("typing_ms") or 0)
            # One input event for a long value is a paste or autofill: fill at once.
            per_char = typing_ms / (keystrokes - 1) if keystrokes > 2 else 0
            step.update(
                action="fill",
                value=value,
                sensitive=bool(event.get("sensitive")),
                char_delay_ms=int(min(300, per_char)) if per_char >= 20 else 0,
            )
        elif kind == "click":
            step["action"] = "click"
            hover = event.get("hover")
            if isinstance(hover, dict):
                # The click target only appeared while this was hovered (a hover menu).
                step["hover_selectors"] = [
                    s for s in hover.get("selectors") or [] if isinstance(s, str)
                ][:6]
        elif kind == "get_text":
            name = str(event.get("save_as") or "").strip()
            if not VARIABLE_NAME.match(name) or name == "profile":
                name = self.next_text_name()
            if not step["label"]:
                step["label"] = " ".join(str(event.get("text") or "").split())[:60]
            step.update(action="get_text", value="", save_as=name)
        elif kind == "select":
            step.update(action="select", value=str(event.get("value", "")))
        elif kind in ("check", "uncheck"):
            step["action"] = kind
        elif kind == "press":
            key = str(event.get("key", ""))
            if not key:
                return
            step.update(action="press", value=key)
        elif kind == "scroll":
            step.update(
                action="scroll",
                value=f"{int(event.get('x') or 0)},{int(event.get('y') or 0)}",
                selectors=[],
            )
            last = self.steps[-1] if self.steps else None
            if last and last["action"] == "scroll" and last.get("_tab") == tab:
                last["value"], last["label"] = step["value"], step["label"]
                self._save()
                return
        else:
            return
        self._switch_to(tab)
        self._append(step, tab)
        if kind in ("click", "press", "select", "check", "uncheck"):
            self._mark_action()

    def _mark_action(self) -> None:
        """The newest step may navigate; a navigation right after it is its result."""
        self._last_action = self.steps[-1]
        self._last_action_at = time.monotonic()

    def _switch_to(self, tab: int) -> None:
        if tab != self._current_tab:
            self._current_tab = tab
            self._append(
                {"action": "switch_tab", "value": str(tab), "label": f"Switch to tab {tab + 1}"},
                tab,
            )

    def _append(self, step: dict[str, Any], tab: int = 0) -> None:
        now = time.monotonic()
        step.setdefault("selectors", [])
        step.setdefault("frame", "")
        step.update(
            id=new_step_id(),
            delay_ms=_delay(now - self._last_at),
            expect_url="",
            _tab=tab,
        )
        step.setdefault("value", "")
        self._last_at = now
        self.steps.append(step)
        self._save()

    def _save(self) -> None:
        if not self._profile_dir:
            return
        path = recording_path(self._profile_dir)
        tmp = path.with_suffix(".json.tmp")
        data = {"recording": self.active, "started_at": self.started_at, "steps": self.steps}
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            pass


def clean_steps(raw: list[Any]) -> list[dict[str, Any]]:
    """Recorded steps without the recorder's bookkeeping, ready for a Workflow."""
    return [
        {k: v for k, v in step.items() if not k.startswith("_")}
        for step in raw
        if isinstance(step, dict) and step.get("action")
    ]
