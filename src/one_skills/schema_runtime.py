"""Packaged JSON Schema loading and Draft 2020-12 validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


class SchemaValidationError(ValueError):
    pass


@dataclass(frozen=True)
class SchemaIssue:
    path: str
    message: str
    validator: str


def _source_schema_root() -> Path:
    return Path(__file__).resolve().parents[2] / "schemas"


def _schema_names() -> list[str]:
    packaged = resources.files("one_skills").joinpath("schemas")
    if packaged.is_dir():
        return sorted(
            item.name
            for item in packaged.iterdir()
            if item.name.endswith(".json")
        )
    return sorted(path.name for path in _source_schema_root().glob("*.json"))


def _schema_text(name: str) -> str:
    if Path(name).name != name or not name.endswith(".json"):
        raise ValueError(f"invalid schema name: {name}")
    packaged = resources.files("one_skills").joinpath("schemas").joinpath(name)
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")
    path = _source_schema_root() / name
    if not path.is_file():
        raise FileNotFoundError(f"JSON Schema is not packaged: {name}")
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _schema_registry() -> tuple[dict[str, dict[str, Any]], Registry]:
    schemas: dict[str, dict[str, Any]] = {}
    registry = Registry()
    for name in _schema_names():
        schema = json.loads(_schema_text(name))
        Draft202012Validator.check_schema(schema)
        schema_id = schema.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            raise SchemaValidationError(f"{name} has no $id")
        schemas[name] = schema
        registry = registry.with_resource(
            schema_id,
            Resource.from_contents(schema),
        )
    return schemas, registry


def validate_schema(value: Any, schema_name: str) -> list[SchemaIssue]:
    schemas, registry = _schema_registry()
    if schema_name not in schemas:
        raise ValueError(f"unknown JSON Schema: {schema_name}")
    json_value = json.loads(
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    )
    validator = Draft202012Validator(
        schemas[schema_name],
        registry=registry,
    )
    issues: list[SchemaIssue] = []
    for error in sorted(
        validator.iter_errors(json_value),
        key=lambda item: (list(item.absolute_path), item.message),
    ):
        location = "$"
        for part in error.absolute_path:
            location += f"[{part}]" if isinstance(part, int) else f".{part}"
        issues.append(
            SchemaIssue(
                path=location,
                message=error.message,
                validator=str(error.validator),
            )
        )
    return issues


def require_schema(value: Any, schema_name: str, label: str = "value") -> None:
    issues = validate_schema(value, schema_name)
    if not issues:
        return
    first = issues[0]
    raise SchemaValidationError(
        f"{label} does not match {schema_name} at {first.path}: {first.message}"
    )
