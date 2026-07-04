import os

from newsworker.settings import Settings


def test_defaults():
    s = Settings()
    assert s.port == 8787
    assert s.content_ttl == 3600
    assert s.spec_ttl == 0
    assert s.host == "127.0.0.1"
    assert s.allowed_hosts == []
    assert s.max_content_bytes == 10 * 1024 * 1024


def test_allowed_hosts_roundtrip(tmp_path):
    path = os.path.join(str(tmp_path), "config.yaml")
    Settings(allowed_hosts=["example.com", "news.example.org"]).save(path)
    reloaded = Settings.load(path)
    assert reloaded.allowed_hosts == ["example.com", "news.example.org"]


def test_load_creates_file_with_defaults(tmp_path):
    path = os.path.join(str(tmp_path), "config.yaml")
    assert not os.path.exists(path)
    s = Settings.load(path)
    assert os.path.exists(path)
    assert s.port == 8787


def test_save_and_reload_roundtrip(tmp_path):
    path = os.path.join(str(tmp_path), "config.yaml")
    s = Settings(port=9000, content_ttl=60, host="0.0.0.0")
    s.save(path)
    reloaded = Settings.load(path)
    assert reloaded.port == 9000
    assert reloaded.content_ttl == 60
    assert reloaded.host == "0.0.0.0"


def test_from_dict_ignores_unknown_keys():
    s = Settings.from_dict({"port": 1234, "bogus": "x"})
    assert s.port == 1234
    assert not hasattr(s, "bogus")


def test_resolved_cache_dir_expands_user():
    s = Settings(cache_dir="~/somewhere/cache")
    resolved = s.resolved_cache_dir()
    assert "~" not in resolved
