from __future__ import annotations

import argparse
import unittest
from contextlib import redirect_stderr
from io import StringIO

from one_skills import __version__
from one_skills.cli import build_parser
from one_skills.resources import resource_file
from one_skills.versions import (
    CURRENT_PACK_VERSION,
    READABLE_PACK_VERSIONS,
)


class ReleaseContractTests(unittest.TestCase):
    def test_stable_cli_commands_remain_registered(self) -> None:
        parser = build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        stable = {
            "init",
            "distill",
            "inspect",
            "next",
            "update",
            "source",
            "semantic",
            "compile",
            "evaluate",
            "compare",
            "validate",
            "release",
            "install",
            "export",
            "migrate",
        }
        self.assertTrue(stable <= set(subparsers.choices))

    def test_compare_baseline_is_explicit(self) -> None:
        parser = build_parser()
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "compare",
                    "run",
                    "./packs/example",
                    "--suite",
                    "./suite.json",
                ]
            )

    def test_version_and_pack_compatibility_matrix(self) -> None:
        self.assertEqual(__version__, "1.0.0")
        self.assertEqual(CURRENT_PACK_VERSION, "1.0")
        self.assertEqual(
            READABLE_PACK_VERSIONS,
            {"0.2", "0.3", "0.4", "1.0"},
        )

    def test_protocol_resources_are_available(self) -> None:
        with resource_file("schemas", "pack.schema.json") as schema:
            self.assertIn('"1.0"', schema.read_text(encoding="utf-8"))
        with resource_file(
            "migrations",
            "postgres",
            "001_initial.sql",
        ) as migration:
            self.assertIn(
                "CREATE EXTENSION IF NOT EXISTS vector",
                migration.read_text(encoding="utf-8"),
            )
        with resource_file("SKILL.md") as skill:
            self.assertGreater(skill.stat().st_size, 100)


if __name__ == "__main__":
    unittest.main()
