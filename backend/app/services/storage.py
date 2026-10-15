from __future__ import annotations

import os
import re
import secrets
from pathlib import Path
from typing import Protocol

_KEY_RE = re.compile(r"^[0-9a-f]{32}\.img$")


class Storage(Protocol):
    """Blob store behind a small interface so an S3-compatible backend can replace the local one."""

    def put(self, data: bytes) -> str: ...
    def read(self, key: str) -> bytes: ...
    def delete(self, key: str) -> bool: ...
    def exists(self, key: str) -> bool: ...
    def healthy(self) -> bool: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not _KEY_RE.match(key):  # keys are generated here; anything else is a traversal attempt
            raise ValueError("invalid storage key")
        return self.root / key

    def put(self, data: bytes) -> str:
        key = f"{secrets.token_hex(16)}.img"  # random, not derived from the client's filename
        path = self._path(key)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        return key

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> bool:
        try:
            self._path(key).unlink()
            return True
        except FileNotFoundError:
            return False

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def healthy(self) -> bool:
        return self.root.is_dir() and os.access(self.root, os.W_OK)
