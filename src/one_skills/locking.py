"""Cross-process locks for Pack filesystem transactions."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock, RLock, local


class LockTimeoutError(TimeoutError):
    pass


_GUARD = Lock()
_LOCAL_LOCKS: dict[Path, RLock] = {}
_DEPTH = local()


def _thread_lock(path: Path) -> RLock:
    with _GUARD:
        return _LOCAL_LOCKS.setdefault(path, RLock())


def _owner_is_alive(path: Path) -> bool:
    try:
        owner = json.loads(path.read_text(encoding="utf-8"))
        pid = int(owner["pid"])
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        try:
            return time.time() - path.stat().st_mtime < 5
        except OSError:
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True
    return True


@contextmanager
def file_lock(path: Path, timeout: float = 60.0) -> Generator[None, None, None]:
    """Acquire a reentrant local lock backed by an exclusive lock file."""
    lock_path = path.expanduser().resolve()
    thread_lock = _thread_lock(lock_path)
    with thread_lock:
        depths = getattr(_DEPTH, "values", {})
        depth = depths.get(lock_path, 0)
        if depth:
            depths[lock_path] = depth + 1
            _DEPTH.values = depths
            try:
                yield
            finally:
                depths[lock_path] -= 1
            return

        lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout
        while True:
            try:
                descriptor = os.open(
                    lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            except FileExistsError:
                if not _owner_is_alive(lock_path):
                    try:
                        lock_path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise LockTimeoutError(f"timed out waiting for lock: {lock_path}")
                time.sleep(0.05)
                continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "pid": os.getpid(),
                        "created_at": time.time(),
                    },
                    handle,
                )
            break

        depths[lock_path] = 1
        _DEPTH.values = depths
        try:
            yield
        finally:
            depths.pop(lock_path, None)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


def workspace_pack_lock_path(workspace: Path, slug: str) -> Path:
    return workspace.resolve() / ".one" / "locks" / "packs" / f"{slug}.lock"


def pack_lock_path(pack: Path) -> Path:
    resolved = pack.expanduser().resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / ".one" / "config.json").exists():
            return workspace_pack_lock_path(candidate, resolved.name)
    return resolved.parent / ".one-locks" / f"{resolved.name}.lock"


@contextmanager
def pack_lock(pack: Path, timeout: float = 60.0) -> Generator[None, None, None]:
    with file_lock(pack_lock_path(pack), timeout):
        yield
