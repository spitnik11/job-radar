"""Semantic re-ranking — cosine, graceful degradation, and blend math (no live Ollama in tests)."""

from app import semantic
from app.config import load_profile


def test_cosine():
    assert abs(semantic.cosine([1, 0], [1, 0]) - 1.0) < 1e-9
    assert abs(semantic.cosine([1, 0], [0, 1])) < 1e-9
    assert semantic.cosine([], [1, 2]) == 0.0


def test_rerank_graceful_without_backend(monkeypatch):
    monkeypatch.setattr(semantic, "embed", lambda t: None)      # backend down
    semantic._profile_emb.clear()
    items = [{"id": "a", "text": "x", "relevance": 90}, {"id": "b", "text": "y", "relevance": 80}]
    assert semantic.rerank(items, load_profile())["order"] == ["a", "b"]   # unchanged


def test_rerank_blends_semantic(monkeypatch):
    # profile embeds inline; job vectors come from the cache (rerank is cache-only)
    monkeypatch.setattr(semantic, "embed", lambda t: [1.0, 0.0])   # profile -> [1,0]
    monkeypatch.setattr(semantic, "_emb_cache", {"a": [1.0, 0.0], "b": [0.0, 1.0]})
    monkeypatch.setattr(semantic, "_cfg", lambda: ("x", "m", 0.25))
    semantic._profile_emb.clear()
    # a: 0.75*80 + 0.25*100 = 85 ; b: 0.75*82 + 0.25*0 = 61.5 -> semantic flips a ahead of b
    items = [{"id": "a", "text": "A job", "relevance": 80},
             {"id": "b", "text": "B job", "relevance": 82}]
    res = semantic.rerank(items, load_profile())
    assert res["order"] == ["a", "b"]
    assert res["scores"]["a"] == 100 and res["scores"]["b"] == 0
