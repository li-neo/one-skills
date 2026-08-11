"""Build hooks for repository-root protocol resources."""

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

ROOT = Path(__file__).resolve().parent


class build_py(_build_py):
    def run(self) -> None:
        super().run()
        package = Path(self.build_lib) / "one_skills"
        shutil.copytree(
            ROOT / "schemas",
            package / "schemas",
            dirs_exist_ok=True,
        )
        shutil.copytree(
            ROOT / "migrations",
            package / "migrations",
            dirs_exist_ok=True,
        )
        shutil.copy2(ROOT / "SKILL.md", package / "SKILL.md")


setup(cmdclass={"build_py": build_py})
