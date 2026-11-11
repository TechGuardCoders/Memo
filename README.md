# Memo

**Per-user memory between sessions — agents forget everything; Memo is the fix.**

A small, honest memory journal: JSONL append-only, stdlib-only, deterministic recall.

```python
from memo import Memo

m = Memo("agent-memory.jsonl")
m.remember("db-host", "postgres runs on mini2", tags=["infra", "db"])
m.pin("db-host")                       # always surfaces
m.recall("database infra")             # ranked: pinned > tag hits > keyword overlap
m.forget("db-host")                    # tombstone — history preserved, never deleted
m.stats()                              # {'memories': 0, 'tombstoned': 1, 'pinned': 0}
```

## Design decisions

- **Append-only JSONL**: memories are events, not rows — crash-safe, git-diffable, auditable. A torn last line after a crash is skipped, not fatal.
- **Tombstones, not deletes**: `forget` writes a forget-event; the audit trail survives. (The NK-NODE memory_journal pattern, generalized.)
- **Deterministic recall**: no embeddings, no network, no magic. Zero-relevance memories are *not* padded into results — noise in recall is worse than silence.
- **Pins beat relevance**: a pinned memory surfaces first, always.

## Part of the TechGuardCoders portfolio

Generalizes the memory journal inside [NK-NODE](https://github.com/TechGuardCoders/NK-NODE) into a standalone any-agent dependency. Pairs with **Triage** (route) and **Forerunner** (monitor) — remember, decide, watch.

## Tests

```bash
python -m pytest tests/ -q   # 14 tests
```

Tests caught two real bugs during the build: tombstones not applying in-session (state only loaded on reopen), and recall padding results with zero-relevance memories.

## Docker

Multi-stage, multi-arch image (amd64 + arm64), runs as non-root.

```bash
# Build for your local arch
docker build -t memo .

# Build for both arches with buildx
docker buildx build --platform linux/amd64,linux/arm64 -t memo .

# Run
docker run --rm memo 
```
