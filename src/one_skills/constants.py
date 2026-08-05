"""Protocol constants shared across one-skills."""

OBJECT_TYPES = (
    "auto",
    "person",
    "content",
    "methodology",
    "sop",
    "tool",
    "skill",
    "hybrid",
)
MODES = ("quick", "standard", "deep", "continuous")
PHASES = (
    "contract",
    "ingest",
    "map",
    "extract",
    "verify",
    "compile",
    "link",
    "test",
    "ship",
    "evolve",
)
PHASE_INDEX = {name: index for index, name in enumerate(PHASES)}

EVIDENCE_TYPES = (
    "quote",
    "verified_position",
    "observed_behavior",
    "third_party_view",
    "model_inference",
    "unknown",
)
INFERENCE_LEVELS = ("none", "low", "medium", "high")
PERMISSIONS = ("public", "authorized", "private-local", "unknown")
CONSENT_LEVELS = ("self", "consented", "work-authorized", "public-only", "prohibited")
TEST_TYPES = (
    "should_trigger",
    "should_not_trigger",
    "sibling_bait",
    "edge_case",
    "failure",
    "safety",
    "task_effect",
)
CANDIDATE_TYPES = ("framework", "principle", "case", "counterexample", "term")
RELATION_TYPES = (
    "depends_on",
    "contrasts_with",
    "composes_with",
    "conflicts_with",
    "routes_to",
    "supports",
    "derived_from",
    "invalidates",
)

TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".csv",
    ".tsv",
    ".xml",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".sh",
    ".toml",
    ".ini",
    ".sql",
}
HTML_SUFFIXES = {".html", ".htm", ".xhtml"}
ARCHIVE_SUFFIXES = {".docx", ".epub"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | HTML_SUFFIXES | ARCHIVE_SUFFIXES | {".pdf"}

MAX_LOCAL_BYTES = 100 * 1024 * 1024
MAX_URL_BYTES = 20 * 1024 * 1024
