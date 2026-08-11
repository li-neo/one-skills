"""Central compatibility matrix for stable Pack contracts."""

CURRENT_PACK_VERSION = "1.0"
READABLE_PACK_VERSIONS = frozenset({"0.2", "0.3", "0.4", "1.0"})
CONSOLIDATED_PACK_VERSIONS = frozenset({"0.4", "1.0"})
SEMANTIC_PACK_VERSIONS = frozenset({"0.3", "0.4", "1.0"})
LEGACY_EXTERNAL_ASSET_VERSIONS = frozenset({"0.2", "0.3"})


def is_readable_pack_version(value: object) -> bool:
    return isinstance(value, str) and value in READABLE_PACK_VERSIONS


def uses_consolidated_assets(value: object) -> bool:
    return isinstance(value, str) and value in CONSOLIDATED_PACK_VERSIONS


def uses_semantic_contract(value: object) -> bool:
    return isinstance(value, str) and value in SEMANTIC_PACK_VERSIONS
