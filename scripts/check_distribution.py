#!/usr/bin/env python3
"""Verify stable release resources in wheel and sdist."""

from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path

VERSION = "1.0.0"
WHEEL_REQUIRED = {
    "one_skills/schemas/pack.schema.json",
    "one_skills/schemas/job-request.schema.json",
    "one_skills/migrations/postgres/001_initial.sql",
    "one_skills/SKILL.md",
    f"one_skills-{VERSION}.dist-info/licenses/LICENSE",
}
SDIST_REQUIRED = {
    f"one_skills-{VERSION}/schemas/pack.schema.json",
    f"one_skills-{VERSION}/migrations/postgres/001_initial.sql",
    f"one_skills-{VERSION}/SKILL.md",
    f"one_skills-{VERSION}/LICENSE",
    f"one_skills-{VERSION}/SECURITY.md",
}


def _missing(actual: set[str], required: set[str]) -> list[str]:
    return sorted(required - actual)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    wheels = list(args.directory.glob(f"one_skills-{VERSION}-*.whl"))
    sdists = list(args.directory.glob(f"one_skills-{VERSION}.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit("expected exactly one 1.0.0 wheel and sdist")
    with zipfile.ZipFile(wheels[0]) as archive:
        wheel_missing = _missing(set(archive.namelist()), WHEEL_REQUIRED)
    with tarfile.open(sdists[0]) as archive:
        sdist_missing = _missing(set(archive.getnames()), SDIST_REQUIRED)
    if wheel_missing or sdist_missing:
        raise SystemExit(
            f"distribution resources missing: wheel={wheel_missing}, "
            f"sdist={sdist_missing}"
        )
    print(
        f"distribution resources verified: {wheels[0].name}, {sdists[0].name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
