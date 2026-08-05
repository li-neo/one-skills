"""Optional OpenAI-compatible model provider for semantic distillation stages."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Protocol
from urllib.request import Request, urlopen


class ProviderError(RuntimeError):
    pass


class ModelProvider(Protocol):
    def complete_json(self, system: str, user: str, schema_name: str) -> dict[str, Any]:
        """Return one JSON object without markdown wrappers."""


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


def verify_candidate(
    provider: ModelProvider,
    candidate: dict[str, Any],
    evidence: list[dict[str, Any]],
    profile_contract: str,
) -> dict[str, Any]:
    result = provider.complete_json(
        (
            "You are an independent capability verifier. Judge only from supplied evidence. "
            "Do not reward eloquence. Return JSON with booleans cross_domain, predictive, "
            "distinctive, actionable, boundary; strings novel_question, derived_answer, reason."
        ),
        json.dumps(
            {
                "profile_contract": profile_contract,
                "candidate": candidate,
                "evidence": evidence,
            },
            ensure_ascii=False,
        ),
        "candidate-verification",
    )
    boolean_fields = ("cross_domain", "predictive", "distinctive", "actionable", "boundary")
    if any(not isinstance(result.get(field), bool) for field in boolean_fields):
        raise ProviderError("candidate verification must contain all boolean gates")
    for field in ("novel_question", "derived_answer", "reason"):
        if not isinstance(result.get(field), str) or not result[field].strip():
            raise ProviderError(f"candidate verification requires non-empty {field}")
    result["accepted"] = all(result[field] for field in boolean_fields)
    return result


def model_capability(
    provider: ModelProvider,
    candidate: dict[str, Any],
    evidence: list[dict[str, Any]],
    profile_contract: str,
) -> dict[str, Any]:
    result = provider.complete_json(
        (
            "Build an executable capability from a verified candidate. Return JSON with strings "
            "name, problem, trigger, output, done, fallback; arrays inputs, procedure, boundaries, "
            "failures. Use only supplied evidence and profile constraints."
        ),
        json.dumps(
            {
                "profile_contract": profile_contract,
                "candidate": candidate,
                "evidence": evidence,
            },
            ensure_ascii=False,
        ),
        "capability-ir",
    )
    string_fields = ("name", "problem", "trigger", "output", "done", "fallback")
    list_fields = ("inputs", "procedure", "boundaries", "failures")
    for field in string_fields:
        if not isinstance(result.get(field), str) or not result[field].strip():
            raise ProviderError(f"capability IR requires non-empty {field}")
    for field in list_fields:
        if (
            not isinstance(result.get(field), list)
            or not result[field]
            or any(not isinstance(item, str) or not item.strip() for item in result[field])
        ):
            raise ProviderError(f"capability IR requires non-empty string array {field}")
    return result
