"""Candidate-only source discovery adapters.

Discovery never ingests content. It produces an auditable shortlist input that
must still pass Source Catalog review and the source-set quality gate.
"""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from .utils import load_json, slugify, utc_now


class SourceDiscoveryError(ValueError):
    pass


def _request_json(url: str) -> Any:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json, application/json",
            "User-Agent": "one-skills/0.3",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def discover_local(path: Path) -> list[dict[str, Any]]:
    root = path.expanduser().resolve()
    if not root.exists():
        raise SourceDiscoveryError(f"local discovery path does not exist: {root}")
    files = [root] if root.is_file() else sorted(item for item in root.rglob("*") if item.is_file())
    candidates: list[dict[str, Any]] = []
    for item in files:
        if any(part.startswith(".") for part in item.relative_to(root if root.is_dir() else root.parent).parts):
            continue
        media_type = mimetypes.guess_type(item.name)[0] or "application/octet-stream"
        candidates.append(
            {
                "id": slugify(item.stem) or f"source-{len(candidates) + 1}",
                "uri": item.as_uri(),
                "ingest": str(item),
                "title": item.stem,
                "creator": "",
                "revision": "",
                "license": None,
                "media_type": media_type,
                "byte_count": item.stat().st_size,
                "discovered_by": "local",
                "status": "candidate",
                "notes": "Local presence is not evidence of authority or usage rights.",
            }
        )
    return candidates


def discover_github(repository: str) -> list[dict[str, Any]]:
    value = repository.removeprefix("https://github.com/").strip("/")
    parts = value.split("/")
    if len(parts) < 2:
        raise SourceDiscoveryError("GitHub input must be owner/repository")
    owner, repo = parts[:2]
    metadata = _request_json(f"https://api.github.com/repos/{quote(owner)}/{quote(repo)}")
    commit = _request_json(
        f"https://api.github.com/repos/{quote(owner)}/{quote(repo)}/commits/{quote(metadata['default_branch'])}"
    )
    license_value = (metadata.get("license") or {}).get("spdx_id")
    return [
        {
            "id": slugify(f"{owner}-{repo}"),
            "uri": metadata["html_url"],
            "ingest": metadata["html_url"],
            "title": metadata["full_name"],
            "creator": metadata["owner"]["login"],
            "revision": commit["sha"],
            "license": license_value,
            "discovered_by": "github",
            "status": "candidate",
            "notes": (
                f"default_branch={metadata['default_branch']}; "
                "repository metadata is for discovery, not protected evidence"
            ),
        }
    ]


def discover_huggingface(identifier: str, kind: str = "dataset") -> list[dict[str, Any]]:
    if kind not in {"dataset", "model"}:
        raise SourceDiscoveryError("Hugging Face kind must be dataset or model")
    endpoint = "datasets" if kind == "dataset" else "models"
    metadata = _request_json(
        f"https://huggingface.co/api/{endpoint}/{quote(identifier, safe='/')}"
    )
    card = metadata.get("cardData") or {}
    return [
        {
            "id": slugify(identifier.replace("/", "-")),
            "uri": f"https://huggingface.co/{'datasets/' if kind == 'dataset' else ''}{identifier}",
            "ingest": f"https://huggingface.co/{'datasets/' if kind == 'dataset' else ''}{identifier}",
            "title": identifier,
            "creator": metadata.get("author", identifier.split("/", 1)[0]),
            "revision": metadata.get("sha", ""),
            "license": card.get("license"),
            "gated": bool(metadata.get("gated", False)),
            "private": bool(metadata.get("private", False)),
            "discovered_by": "huggingface",
            "status": "candidate",
            "notes": f"{kind} card metadata only; inspect files and rights before shortlist",
        }
    ]


def discover_manifest(path: Path) -> list[dict[str, Any]]:
    value = load_json(path)
    items = value.get("candidates") if isinstance(value, dict) else value
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise SourceDiscoveryError("manifest must be an array or contain candidates array")
    candidates: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        uri = item.get("uri")
        if not isinstance(uri, str) or not uri.strip():
            raise SourceDiscoveryError(f"manifest candidate {index} has no uri")
        candidates.append(
            {
                **item,
                "id": item.get("id") or f"source-{index}",
                "title": item.get("title") or uri,
                "discovered_by": "manifest",
                "status": "candidate",
            }
        )
    return candidates


def discover_sources(
    adapter: str,
    target: str,
    subject: str,
    research_questions: list[str],
    *,
    huggingface_kind: str = "dataset",
) -> dict[str, Any]:
    if not subject.strip() or not research_questions:
        raise SourceDiscoveryError("source discovery requires subject and research questions")
    if adapter == "local":
        candidates = discover_local(Path(target))
    elif adapter == "github":
        candidates = discover_github(target)
    elif adapter == "huggingface":
        candidates = discover_huggingface(target, huggingface_kind)
    elif adapter == "manifest":
        candidates = discover_manifest(Path(target))
    else:
        raise SourceDiscoveryError(f"unsupported discovery adapter: {adapter}")
    return {
        "schema_version": "1.0",
        "subject": subject.strip(),
        "research_questions": list(dict.fromkeys(research_questions)),
        "adapter": adapter,
        "candidates": candidates,
        "generated_at": utc_now(),
    }


def shortlist_sources(path: Path, selected_ids: list[str]) -> dict[str, Any]:
    value = load_json(path)
    selected = set(selected_ids)
    known = {item["id"] for item in value.get("candidates", [])}
    unknown = selected - known
    if unknown:
        raise SourceDiscoveryError(f"unknown source candidate IDs: {', '.join(sorted(unknown))}")
    shortlisted = []
    for item in value["candidates"]:
        status = "shortlisted" if item["id"] in selected else "excluded"
        shortlisted.append({**item, "status": status})
    return {**value, "candidates": shortlisted, "shortlisted_at": utc_now()}
