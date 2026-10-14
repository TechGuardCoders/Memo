"""
Memo — per-user memory between sessions.

Agents forget everything between runs. Memo is a small, honest memory
journal: JSONL-backed, stdlib-only, with the three operations that matter:

    remember(key, text, tags=[])   -> append a memory (never overwrite)
    recall(query, k=5)             -> ranked recall (tag match > recency)
    forget(key)                    -> tombstone (history preserved)

Design decisions:
- JSONL append-only: memories are events, not rows — crash-safe, git-diffable
- recall is deterministic: exact tag hits first, then keyword overlap,
  then recency. No embeddings, no network, no magic.
- tombstones, not deletes: audit trail survives (NK-NODE's
  memory_journal pattern, generalized)
- pinned memories always surface first

Public API:
    Memo(path)                     -> open/create a journal
    .remember/.recall/.forget/.pin/.pinned/.stats
"""
from __future__ import annotations

import json
import time
from pathlib import Path

__version__ = "0.1.0"


def _now() -> float:
    return time.time()


class Memo:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        self._tombstones: set[str] = set()
        self._pinned: set[str] = set()
        self._load_state()

    # ---------------------------------------------------------------- io

    def _append(self, record: dict) -> None:
        record["ts"] = _now()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _load_state(self) -> None:
        """Replay the journal to rebuild tombstones/pins (append-only log)."""
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue  # torn last line after a crash — skip, don't die
            if r.get("op") == "forget":
                self._tombstones.add(r["key"])
                self._pinned.discard(r["key"])
            elif r.get("op") == "pin":
                self._pinned.add(r["key"])
                self._tombstones.discard(r["key"])

    # ---------------------------------------------------------------- ops

    def remember(self, key: str, text: str, tags: list[str] | None = None) -> dict:
        if not key or not text:
            raise ValueError("key and text are required")
        rec = {"op": "remember", "key": key, "text": text, "tags": tags or []}
        self._append(rec)
        return rec

    def forget(self, key: str) -> None:
        self._append({"op": "forget", "key": key})
        self._tombstones.add(key)
        self._pinned.discard(key)

    def pin(self, key: str) -> None:
        self._append({"op": "pin", "key": key})
        self._pinned.add(key)
        self._tombstones.discard(key)

    def _live_memories(self) -> list[dict]:
        """Latest remember per key, minus tombstones."""
        latest: dict[str, dict] = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("op") == "remember":
                latest[r["key"]] = r
        return [r for k, r in latest.items()
                if k not in self._tombstones]

    # ---------------------------------------------------------------- recall

    def recall(self, query: str, k: int = 5) -> list[dict]:
        """Ranked recall: pinned first, then tag hits, keyword overlap, recency."""
        q_words = set(query.lower().split())
        scored = []
        for r in self._live_memories():
            tags = set(t.lower() for t in r.get("tags", []))
            words = set(r["text"].lower().split()) | tags
            overlap = len(q_words & words)
            tag_hit = len(q_words & tags)
            score = tag_hit * 10 + overlap
            if r["key"] in self._pinned:
                score += 1000
            if score <= 0:
                continue  # no relevance, no recall — don't pad with noise
            scored.append((score, r["ts"], r))
        scored.sort(key=lambda t: (-t[0], -t[1]))
        return [r for _, _, r in scored[:k]]

    def pinned(self) -> list[dict]:
        return [r for r in self._live_memories() if r["key"] in self._pinned]

    def stats(self) -> dict:
        live = self._live_memories()
        return {"memories": len(live), "tombstoned": len(self._tombstones),
                "pinned": len(self._pinned)}
