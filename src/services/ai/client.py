"""Generate a text with an OpenAI-compatible Chat Completions API.

Plain urllib, so any compatible server works (OpenAI, Azure OpenAI, OpenRouter,
a local LLM) and no SDK is needed. Requests follow the system proxy settings.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from ...utils import net
from .settings import AISettings

MAX_OUTPUT = 20_000


class AIError(Exception):
    pass


def generate(settings: AISettings, prompt: str, timeout: float = 60) -> str:
    """The model's reply to `prompt`, stripped; AIError on any failure."""
    if not settings.api_key:
        raise AIError("AI is not set up: add an API key in the AI settings")
    body: dict = {
        "model": settings.model,
        "messages": [
            *(
                [{"role": "system", "content": settings.system_prompt}]
                if settings.system_prompt.strip()
                else []
            ),
            {"role": "user", "content": prompt},
        ],
    }
    if settings.temperature is not None:
        body["temperature"] = settings.temperature
    request = urllib.request.Request(
        settings.base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as e:
        raise AIError(f"AI request failed (HTTP {e.code}): {_detail(e)}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise AIError(
            f"Cannot reach the AI service at {settings.base_url}: {reason}. {net.network_hint()}"
        ) from e
    except ValueError as e:
        raise AIError("The AI service did not answer with JSON") from e
    try:
        text = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise AIError("The AI service answered without a message") from e
    text = text.strip()
    # Models asked for "only the text" still like to quote it.
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'“”":
        text = text[1:-1].strip()
    if not text:
        raise AIError("The AI service returned an empty text")
    return text[:MAX_OUTPUT]


def _detail(error: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(error.read() or b"{}")
        message = payload.get("error", {}).get("message") or payload.get("message")
    except (ValueError, AttributeError):
        message = None
    return " ".join(str(message or error.reason).split())[:300]
