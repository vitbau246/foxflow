"""Settings of the optional AI text generation used by workflow "ai" steps.

Nothing is sent anywhere until an API key is set. The key is kept in
AI_SETTINGS_FILE (plain JSON in the working directory, like profiles.json) or
given by FOXFLOW_OPENAI_API_KEY, which wins and is never written to disk.
"""

from __future__ import annotations

import json
import os
import pathlib
import threading

from pydantic import BaseModel, Field, field_validator

from ...core.config import AI_SETTINGS_FILE, OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
from ...core.logging import get_logger

logger = get_logger("ai.settings")

DEFAULT_SYSTEM_PROMPT = (
    "You write text that a person types into a web page. Reply with that text only: "
    "no quotes, no explanations, no Markdown."
)


class AISettings(BaseModel):
    api_key: str = Field("", max_length=500)
    base_url: str = Field(OPENAI_BASE_URL, max_length=500)
    model: str = Field(OPENAI_MODEL, max_length=200)
    system_prompt: str = Field(DEFAULT_SYSTEM_PROMPT, max_length=10_000)
    # None leaves it to the model: some only accept their default.
    temperature: float | None = Field(None, ge=0, le=2)

    @field_validator("base_url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v.startswith(("https://", "http://")):
            raise ValueError("the base URL must start with https:// or http://")
        return v


class AISettingsStore:
    def __init__(self, path: str = AI_SETTINGS_FILE) -> None:
        self._path = pathlib.Path(path)
        self._lock = threading.Lock()

    def load(self) -> AISettings:
        """The saved settings, with FOXFLOW_OPENAI_API_KEY in place of the key if set."""
        settings = AISettings()
        with self._lock:
            if self._path.exists():
                try:
                    settings = AISettings.model_validate(
                        json.loads(self._path.read_text(encoding="utf-8"))
                    )
                except (OSError, ValueError) as e:
                    logger.warning("Ignoring unreadable %s: %s", self._path, e)
        if OPENAI_API_KEY:
            settings.api_key = OPENAI_API_KEY
        return settings

    def save(self, settings: AISettings) -> None:
        data = settings.model_dump()
        if OPENAI_API_KEY and data["api_key"] == OPENAI_API_KEY:
            data["api_key"] = ""  # the environment's key stays out of the file
        tmp = self._path.with_suffix(".json.tmp")
        with self._lock:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self._path)

    def public(self) -> dict:
        """Settings safe to show: the key only as a hint."""
        s = self.load()
        key = s.api_key
        return {
            "configured": bool(key),
            "key_hint": f"{key[:3]}…{key[-4:]}" if len(key) > 10 else ("set" if key else ""),
            "key_from_env": bool(OPENAI_API_KEY),
            "base_url": s.base_url,
            "model": s.model,
            "system_prompt": s.system_prompt,
            "temperature": s.temperature,
        }
