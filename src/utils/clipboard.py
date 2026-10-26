"""Read the text on the system clipboard, without extra dependencies.

Windows: the Win32 clipboard through ctypes, with its sequence number to see
cheaply that something new was copied. macOS: pbpaste. Linux: wl-paste, xclip
or xsel, whichever is installed. Used only by clipboard triggers, which the
user sets up; nothing here sends the text anywhere.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

MAX_TEXT = 100_000


class ClipboardUnavailable(Exception):
    pass


def change_count() -> int | None:
    """A number that changes whenever something is copied, where the OS has one."""
    if sys.platform != "win32":
        return None
    import ctypes

    return int(ctypes.windll.user32.GetClipboardSequenceNumber())


def _windows() -> str | None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    cf_unicodetext = 13
    if not user32.IsClipboardFormatAvailable(cf_unicodetext):
        return None
    # Another program may hold the clipboard for a moment.
    for _ in range(5):
        if user32.OpenClipboard(None):
            break
        kernel32.Sleep(20)
    else:
        raise ClipboardUnavailable("the clipboard is in use by another program")
    try:
        handle = user32.GetClipboardData(cf_unicodetext)
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.wstring_at(pointer)[:MAX_TEXT]
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _command() -> list[str]:
    if sys.platform == "darwin":
        return ["pbpaste"]
    for cmd in (
        ["wl-paste", "--no-newline", "--type", "text"],
        ["xclip", "-selection", "clipboard", "-o"],
        ["xsel", "--clipboard", "--output"],
    ):
        if shutil.which(cmd[0]):
            return cmd
    raise ClipboardUnavailable("no clipboard tool found: install wl-clipboard, xclip or xsel")


def read_text() -> str | None:
    """The copied text, or None when the clipboard holds no text."""
    if sys.platform == "win32":
        return _windows()
    cmd = _command()
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ClipboardUnavailable(f"{cmd[0]}: {e}") from e
    if out.returncode != 0:
        # wl-paste / xclip exit non-zero on an empty clipboard or a non-text one.
        return None
    return out.stdout.decode("utf-8", "replace")[:MAX_TEXT]
