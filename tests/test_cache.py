import os
import time

from newsworker.cache import ContentCache, SpecCache, _evict, key_for
from newsworker.spec import FeedSpec, FieldRule


def _write(path, data, mtime):
    with open(path, "wb") as handle:
        handle.write(data)
    os.utime(path, (mtime, mtime))


def test_key_is_stable_and_hex():
    k1 = key_for("https://example.com/a")
    k2 = key_for("https://example.com/a")
    k3 = key_for("https://example.com/b")
    assert k1 == k2
    assert k1 != k3
    assert all(c in "0123456789abcdef" for c in k1)


def test_content_cache_set_get(tmp_path):
    cache = ContentCache(str(tmp_path), ttl=3600)
    url = "https://example.com/news"
    assert cache.get(url) is None
    cache.set(url, b"<html>hi</html>")
    assert cache.get(url) == b"<html>hi</html>"


def test_content_cache_expiry(tmp_path):
    cache = ContentCache(str(tmp_path), ttl=1)
    url = "https://example.com/news"
    cache.set(url, b"data")
    # Backdate the file mtime beyond the TTL.
    path = cache.path_for(url)
    old = time.time() - 10
    os.utime(path, (old, old))
    assert cache.get(url) is None


def test_spec_cache_never_expires_with_zero_ttl(tmp_path):
    cache = SpecCache(str(tmp_path), ttl=0)
    url = "https://example.com/news"
    spec = FeedSpec(source_url=url, title="T", fields={"date": FieldRule(selector=".d")})
    cache.set(url, spec)
    path = cache.path_for(url)
    old = time.time() - 10_000_000
    os.utime(path, (old, old))
    loaded = cache.get(url)
    assert loaded is not None
    assert loaded.title == "T"
    assert "date" in loaded.fields


def test_spec_cache_miss_returns_none(tmp_path):
    cache = SpecCache(str(tmp_path))
    assert cache.get("https://absent.example/x") is None


def test_evict_by_max_entries_removes_oldest(tmp_path):
    now = time.time()
    for i in range(4):
        _write(os.path.join(str(tmp_path), "e%d.bin" % i), b"x", now + i)
    _evict(str(tmp_path), "*.bin", max_entries=2)
    remaining = sorted(os.listdir(str(tmp_path)))
    assert remaining == ["e2.bin", "e3.bin"]  # two newest survive


def test_evict_by_max_bytes_removes_oldest(tmp_path):
    now = time.time()
    _write(os.path.join(str(tmp_path), "a.bin"), b"x" * 8, now)
    _write(os.path.join(str(tmp_path), "b.bin"), b"y" * 8, now + 1)
    _evict(str(tmp_path), "*.bin", max_bytes=10)  # 16 > 10 -> drop oldest
    assert os.listdir(str(tmp_path)) == ["b.bin"]


def test_evict_noop_when_unbounded(tmp_path):
    now = time.time()
    for i in range(5):
        _write(os.path.join(str(tmp_path), "e%d.bin" % i), b"x", now + i)
    _evict(str(tmp_path), "*.bin")  # no limits
    assert len(os.listdir(str(tmp_path))) == 5


def test_content_cache_set_triggers_eviction(tmp_path):
    cache = ContentCache(str(tmp_path), ttl=0, max_entries=1)
    cache.set("https://example.com/a", b"aa")
    # Backdate the first entry so it is unambiguously the oldest.
    os.utime(cache.path_for("https://example.com/a"), (time.time() - 100,) * 2)
    cache.set("https://example.com/b", b"bb")
    assert cache.get("https://example.com/a") is None
    assert cache.get("https://example.com/b") == b"bb"
