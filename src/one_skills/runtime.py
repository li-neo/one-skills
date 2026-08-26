"""Runtime-neutral export adapters."""

from __future__ import annotations

from dataclasses import dataclass
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


def export_runtime(pack: Path, output: Path, runtime: str) -> Path:
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
