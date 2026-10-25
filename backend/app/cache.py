"""Parse cache keyed by the SHA-256 of the PDF (SPEC §7.2).

In memory on the server; mirrored to disk under `.cache/` for scripts and eval.
The cache holds the *raw* parse (before blind.py runs), so a fix to blind.py
applies without new API calls. Each entry is tagged with the parse model and
prompt version, and a tag mismatch counts as a miss, so changing either one
re-parses instead of serving stale output.
"""

import hashlib
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

from app.models import ParsedResume


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class DiskCache:
    """One JSON file per key under `<root>/<namespace>/`."""

    def __init__(self, root: Path, namespace: str):
        self.dir = root / namespace
        self.dir.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def get(self, key: str) -> Any | None:
        p = self.path(key)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def put(self, key: str, value: Any) -> None:
        p = self.path(key)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)


class ParseCache:
    def __init__(self, tag: str, disk_root: Path | None = None, max_memory_items: int = 1000):
        self.tag = tag
        self._memory: OrderedDict[str, ParsedResume] = OrderedDict()
        self._max = max_memory_items
        self._disk = DiskCache(disk_root, "parse") if disk_root else None

    def get(self, sha: str) -> ParsedResume | None:
        if sha in self._memory:
            self._memory.move_to_end(sha)
            return self._memory[sha]
        if self._disk:
            entry = self._disk.get(sha)
            if entry and entry.get("tag") == self.tag:
                parsed = ParsedResume.model_validate(entry["parsed"])
                self._remember(sha, parsed)
                return parsed
        return None

    def put(self, sha: str, parsed: ParsedResume) -> None:
        self._remember(sha, parsed)
        if self._disk:
            self._disk.put(sha, {"sha256": sha, "tag": self.tag, "parsed": parsed.model_dump()})

    def _remember(self, sha: str, parsed: ParsedResume) -> None:
        self._memory[sha] = parsed
        self._memory.move_to_end(sha)
        while len(self._memory) > self._max:
            self._memory.popitem(last=False)
