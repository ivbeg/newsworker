import csv
import io
import json

from typer.testing import CliRunner

from newsworker.core import app
from newsworker.dedup import DedupStore
from newsworker.watching import run_watch_iteration

URL = "https://news.example/list"


class _Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


class _Service:
    def __init__(self, items):
        self.items = items

    def get_feed(self, url, **kwargs):
        return {"title": "News", "link": url, "items": [dict(item) for item in self.items]}


class _Recorder:
    def __init__(self, name="recorder"):
        self.name = self.destination_identity = name
        self.sent = []

    def validate_config(self):
        return None

    def send(self, payload):
        from newsworker.delivery import DeliveryResult

        self.sent.append(payload.item)
        return DeliveryResult("success")


def test_history_records_versions_and_returns_only_changes(tmp_path):
    clock = _Clock()
    store = DedupStore(str(tmp_path / "w.sqlite3"), clock=clock)
    item = {"unique_id": "1", "title": "Budget", "link": "https://news.example/1"}
    assert store.record_items(URL, [item]) == []
    clock.now += 60
    assert store.record_items(URL, [item]) == []
    edited = {**item, "title": "Budget approved"}
    changed = store.record_items(URL, [edited])
    assert [(c["version"], c["updated"]) for c in changed] == [(2, True)]
    row = store.history(URL)[0]
    assert row["version"] == 2 and row["title"] == "Budget approved"
    assert row["last_seen"] > row["first_seen"]
    clock.now += 400 * 86400
    store.prune(30, history_days=365)
    assert store.history(URL) == []
    store.close()


def test_watch_delivers_updates_once_per_version_only_when_asked(tmp_path):
    store = DedupStore(str(tmp_path / "w.sqlite3"))
    item = {"unique_id": "1", "title": "Budget", "link": "https://news.example/1"}
    service = _Service([item])
    plain, updates = _Recorder("plain"), _Recorder("updates")
    for channel, deliver in ((plain, False), (updates, True)):
        service.items = [item]
        run_watch_iteration(
            service,
            URL + channel.name,
            "json",
            store,
            None,
            1,
            channels=[channel],
            deliver_updates=deliver,
        )
    for channel, deliver in ((plain, False), (updates, True)):
        service.items = [{**item, "title": "Budget approved"}]
        for _ in range(2):
            run_watch_iteration(
                service,
                URL + channel.name,
                "json",
                store,
                None,
                1,
                channels=[channel],
                deliver_updates=deliver,
            )
    assert [i["title"] for i in plain.sent] == ["Budget"]
    assert [(i["title"], i.get("updated")) for i in updates.sent] == [
        ("Budget", None),
        ("Budget approved", True),
    ]
    store.close()


def test_history_command_exports_jsonl_and_csv(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    store = DedupStore(str(cache / "seen.sqlite3"))
    store.record_items(
        URL, [{"unique_id": "1", "title": "Budget", "link": "https://news.example/1"}]
    )
    store.close()
    config = tmp_path / "config.yaml"
    config.write_text(f"cache_dir: {cache}\n")
    result = CliRunner().invoke(app, ["history", "-c", str(config)])
    assert result.exit_code == 0, result.output
    record = json.loads(result.output.splitlines()[0])
    assert record["title"] == "Budget" and record["first_seen"].endswith("+00:00")
    result = CliRunner().invoke(app, ["history", URL, "-f", "csv", "-c", str(config)])
    rows = list(csv.DictReader(io.StringIO(result.output)))
    assert rows[0]["link"] == "https://news.example/1"
    result = CliRunner().invoke(app, ["history", "--since", "2999-01-01", "-c", str(config)])
    assert result.output == ""
