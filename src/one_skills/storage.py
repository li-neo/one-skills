"""Content-addressed local object store."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Protocol
from urllib.parse import urlparse
from urllib.request import url2pathname

from .models import SourceDocument
from .utils import atomic_write


class BlobStore(Protocol):
    def put_source(self, source: SourceDocument) -> str:
        """Persist one immutable source and return its URI."""

    def exists(self, uri: str) -> bool:
        """Read back an object existence check."""


class LocalBlobStore:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put_source(self, source: SourceDocument) -> str:
        directory = self.root / source.content_hash[:2] / source.content_hash
        directory.mkdir(parents=True, exist_ok=True)
        original = Path(source.source)
        if original.is_file():
            suffix = original.suffix or ".bin"
            target = directory / f"raw{suffix}"
            if not target.exists():
                shutil.copyfile(original, target)
        else:
            target = directory / "captured.txt"
            if not target.exists():
                atomic_write(target, source.text + "\n")
        uri = target.as_uri()
        if not self.exists(uri):
            raise OSError(f"blob read-back verification failed: {uri}")
        return uri

    def exists(self, uri: str) -> bool:
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            return False
        value = f"//{parsed.netloc}{parsed.path}" if parsed.netloc else parsed.path
        return Path(url2pathname(value)).is_file()
