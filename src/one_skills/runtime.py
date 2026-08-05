"""Runtime-neutral export adapters with plugin registration."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path, PurePosixPath
import zipfile


@dataclass(frozen=True)
class RuntimeAdapter:
    name: str
    skills_prefix: PurePosixPath

    def archive_path(self, skill_name: str, relative: Path) -> PurePosixPath:
        return self.skills_prefix / skill_name / PurePosixPath(relative.as_posix())


RUNTIME_ADAPTERS = {
    "generic": RuntimeAdapter("generic", PurePosixPath("skills")),
    "codex": RuntimeAdapter("codex", PurePosixPath(".codex/skills")),
    "claude": RuntimeAdapter("claude", PurePosixPath(".claude/skills")),
    "cursor": RuntimeAdapter("cursor", PurePosixPath(".cursor/skills")),
}
_LOADED_RUNTIME_ENTRIES: set[str] = set()


def register_runtime(adapter: RuntimeAdapter, replace: bool = False) -> None:
    if adapter.name in RUNTIME_ADAPTERS and not replace:
        raise ValueError(f"runtime already registered: {adapter.name}")
    RUNTIME_ADAPTERS[adapter.name] = adapter


def load_runtime_plugins() -> list[str]:
    loaded: list[str] = []
    discovered = entry_points()
    selected = (
        discovered.select(group="one_skills.runtimes")
        if hasattr(discovered, "select")
        else discovered.get("one_skills.runtimes", [])
    )
    for entry_point in selected:
        identity = f"{entry_point.name}:{entry_point.value}"
        if identity in _LOADED_RUNTIME_ENTRIES:
            continue
        value = entry_point.load()
        adapter = value() if callable(value) else value
        if not isinstance(adapter, RuntimeAdapter):
            raise TypeError(f"runtime plugin {entry_point.name} did not return RuntimeAdapter")
        register_runtime(adapter)
        _LOADED_RUNTIME_ENTRIES.add(identity)
        loaded.append(adapter.name)
    return loaded


def export_runtime(pack: Path, output: Path, runtime: str) -> Path:
    load_runtime_plugins()
    adapter = RUNTIME_ADAPTERS.get(runtime)
    if adapter is None:
        raise ValueError(f"unknown runtime adapter: {runtime}")
    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / f"{pack.name}-{runtime}.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for skill_dir in sorted(path.parent for path in (pack / "skills").glob("*/SKILL.md")):
            for source in sorted(skill_dir.rglob("*")):
                if source.is_file():
                    archive.write(
                        source,
                        adapter.archive_path(skill_dir.name, source.relative_to(skill_dir)),
                    )
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        expected_prefix = adapter.skills_prefix.as_posix().rstrip("/") + "/"
        if not names or not any(
            name.startswith(expected_prefix) and name.endswith("/SKILL.md") for name in names
        ):
            raise ValueError("runtime archive read-back verification failed")
    return archive_path
