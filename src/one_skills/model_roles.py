"""Role-separated model configuration with an explicit single-model fallback."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .provider import OpenAICompatibleProvider, ProviderConfig


class ModelRoleError(ValueError):
    pass


@dataclass(frozen=True)
class ModelRoleSet:
    builder: ProviderConfig
    answer: ProviderConfig
    judge: ProviderConfig
    isolation_level: str

    def providers(self) -> dict[str, OpenAICompatibleProvider]:
        return {
            "builder": OpenAICompatibleProvider(self.builder),
            "answer": OpenAICompatibleProvider(self.answer),
            "judge": OpenAICompatibleProvider(self.judge),
        }

    def public_status(self) -> dict[str, Any]:
        return {
            "configured": True,
            "isolation_level": self.isolation_level,
            "roles": {
                "builder": {
                    "base_url": self.builder.base_url,
                    "model": self.builder.model,
                },
                "answer": {
                    "base_url": self.answer.base_url,
                    "model": self.answer.model,
                },
                "judge": {
                    "base_url": self.judge.base_url,
                    "model": self.judge.model,
                },
            },
        }


def _role_config(role: str) -> ProviderConfig | None:
    prefix = f"ONE_SKILLS_{role.upper()}"
    base_url = os.getenv(f"{prefix}_BASE_URL", "").rstrip("/")
    api_key = os.getenv(f"{prefix}_API_KEY", "")
    model = os.getenv(f"{prefix}_MODEL", "")
    values = (base_url, api_key, model)
    if not any(values):
        return None
    if not all(values):
        raise ModelRoleError(f"{role} role requires BASE_URL, API_KEY, and MODEL")
    return ProviderConfig(base_url=base_url, api_key=api_key, model=model)


def load_model_roles() -> ModelRoleSet | None:
    role_values = {
        role: _role_config(role)
        for role in ("builder", "answer", "judge")
    }
    configured = [value for value in role_values.values() if value is not None]
    if configured and len(configured) != 3:
        missing = [role for role, value in role_values.items() if value is None]
        raise ModelRoleError(
            "role-specific configuration must define all three roles; missing "
            + ", ".join(missing)
        )
    if len(configured) == 3:
        builder = role_values["builder"]
        answer = role_values["answer"]
        judge = role_values["judge"]
        assert builder is not None and answer is not None and judge is not None
        endpoints = {builder.base_url, answer.base_url, judge.base_url}
        models = {builder.model, answer.model, judge.model}
        isolation = (
            "provider-separated"
            if len(endpoints) == 3
            else "model-separated"
            if len(models) == 3
            else "model-shared/session-separated"
        )
        return ModelRoleSet(builder, answer, judge, isolation)

    fallback = ProviderConfig.from_environment()
    if fallback is None:
        return None
    return ModelRoleSet(
        fallback,
        fallback,
        fallback,
        "model-shared/session-separated",
    )


def model_status() -> dict[str, Any]:
    roles = load_model_roles()
    if roles is None:
        return {
            "configured": False,
            "isolation_level": "unavailable",
            "roles": {},
            "required": [
                "ONE_SKILLS_BUILDER_BASE_URL/API_KEY/MODEL",
                "ONE_SKILLS_ANSWER_BASE_URL/API_KEY/MODEL",
                "ONE_SKILLS_JUDGE_BASE_URL/API_KEY/MODEL",
            ],
            "fallback": "ONE_SKILLS_MODEL_BASE_URL/API_KEY/MODEL",
        }
    return roles.public_status()
