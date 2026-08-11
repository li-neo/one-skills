"""Stable provenance fingerprints used by evaluation and release gates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core_assets import load_source_manifest
from .utils import stable_json_hash


def source_set_fingerprint(manifest: dict[str, Any]) -> str:
    sources = [
        {
            "source_id": item.get("source_id"),
            "document_id": item.get("document_id"),
            "document_version": item.get("document_version"),
            "content_hash": item.get("content_hash"),
            "active": item.get("active", True),
            "revoked_at": item.get("revoked_at"),
            "source_role": item.get("source_role"),
            "access_level": item.get("access_level"),
        }
        for item in manifest.get("sources", [])
    ]
    return stable_json_hash(
        sorted(
            sources,
            key=lambda item: (
                str(item["source_id"]),
                int(item["document_version"] or 0),
            ),
        )
    )


def current_source_set_hash(pack: Path) -> str:
    return source_set_fingerprint(load_source_manifest(pack))
