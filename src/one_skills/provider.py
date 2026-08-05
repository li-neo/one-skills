"""Optional OpenAI-compatible model provider for semantic distillation stages."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any
from urllib.request import Request, urlopen


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    base_url: str
    api_key: str
    model: str
    timeout: int = 120

    @classmethod
    def from_environment(cls) -> "ProviderConfig | None":
        base_url = os.getenv("ONE_SKILLS_MODEL_BASE_URL", "").rstrip("/")
        api_key = os.getenv("ONE_SKILLS_MODEL_API_KEY", "")
        model = os.getenv("ONE_SKILLS_MODEL", "")
        if not all((base_url, api_key, model)):
            return None
        return cls(base_url=base_url, api_key=api_key, model=model)


class OpenAICompatibleProvider:
    def __init__(self, config: ProviderConfig):
        self.config = config

    def complete_json(
        self,
        system: str,
        user: str,
        schema_name: str,
    ) -> dict[str, Any]:
        payload = {
            "model": self.config.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        request = Request(
            f"{self.config.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "one-skills/0.1",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            value = json.loads(content)
        except (OSError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ProviderError(f"{schema_name} model response could not be parsed") from exc
        if not isinstance(value, dict):
            raise ProviderError(f"{schema_name} model response must be a JSON object")
        return value
