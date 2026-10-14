"""Memo tests — append-only journal, deterministic recall, crash-safe."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from memo import Memo


@pytest.fixture
def memo(tmp_path):
    return Memo(tmp_path / "memo.jsonl")


def test_remember_and_recall_by_tag(memo):
    memo.remember("db-host", "postgres runs on mini2", tags=["infra", "db"])
    hits = memo.recall("db infra")
    assert hits[0]["key"] == "db-host"


def test_recall_keyword_overlap(memo):
    memo.remember("k1", "the fleet uses quic tunnels")
    hits = memo.recall("quic tunnels")
    assert hits and hits[0]["key"] == "k1"


def test_recall_no_match_returns_empty(memo):
    memo.remember("k", "something")
    assert memo.recall("zzz") == []


def test_forget_tombstones(memo):
    memo.remember("k", "secret stuff")
    memo.forget("k")
    assert memo.recall("secret") == []


def test_tombstone_preserves_history(memo):
    memo.remember("k", "v1")
    memo.forget("k")
    lines = memo.path.read_text().splitlines()
    assert len(lines) == 2  # both events still in the journal


def test_remember_same_key_twice_latest_wins(memo):
    memo.remember("k", "old")
    memo.remember("k", "new")
    hits = memo.recall("new")
    assert hits[0]["text"] == "new"
    assert len(hits) == 1


def test_pinned_surfaces_first(memo):
    memo.remember("a", "zebra crossing", tags=["z"])
    memo.remember("b", "unrelated words", tags=["q"])
    memo.pin("b")
    hits = memo.recall("zebra")
    assert hits[0]["key"] == "b"  # pinned beats relevance


def test_pinned_list(memo):
    memo.remember("k", "v")
    memo.pin("k")
    assert [r["key"] for r in memo.pinned()] == ["k"]


def test_unpin_via_forget_then_repin(memo):
    memo.remember("k", "v")
    memo.pin("k")
    memo.forget("k")
    assert memo.pinned() == []


def test_state_survives_reopen(tmp_path):
    m1 = Memo(tmp_path / "memo.jsonl")
    m1.remember("k", "persistent", tags=["t"])
    m1.pin("k")
    m2 = Memo(tmp_path / "memo.jsonl")
    assert m2.pinned()[0]["text"] == "persistent"
    assert m2.recall("persistent")[0]["key"] == "k"


def test_torn_last_line_is_skipped_not_fatal(tmp_path):
    p = tmp_path / "memo.jsonl"
    p.write_text(json.dumps({"op": "remember", "key": "k", "text": "v", "tags": [], "ts": 1}) + "\n" + '{"op": "rem')
    m = Memo(p)
    assert m.recall("v")[0]["key"] == "k"


def test_stats(memo):
    memo.remember("a", "1")
    memo.remember("b", "2")
    memo.forget("a")
    memo.pin("b")
    s = memo.stats()
    assert s == {"memories": 1, "tombstoned": 1, "pinned": 1}


def test_empty_key_or_text_raises(memo):
    with pytest.raises(ValueError):
        memo.remember("", "x")
    with pytest.raises(ValueError):
        memo.remember("k", "")


def test_journal_is_jsonl_diffable(memo):
    memo.remember("k", "v", tags=["t"])
    line = json.loads(memo.path.read_text().splitlines()[0])
    assert line["op"] == "remember"
    assert line["key"] == "k"
    assert "ts" in line
