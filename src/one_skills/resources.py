"""Access build-packaged protocol resources with source-checkout fallback."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from importlib import resources
from pathlib import Path


@contextmanager
def resource_file(*parts: str) -> Generator[Path, None, None]:
    target = resources.files("one_skills")
    for part in parts:
        if Path(part).name != part:
            raise ValueError(f"invalid resource path component: {part}")
        target = target.joinpath(part)
    if target.is_file():
        with resources.as_file(target) as path:
            yield path
        return
    fallback = Path(__file__).resolve().parents[2].joinpath(*parts)
    if not fallback.is_file():
        raise FileNotFoundError(
            "one-skills resource is not packaged: " + "/".join(parts)
        )
    yield fallback
