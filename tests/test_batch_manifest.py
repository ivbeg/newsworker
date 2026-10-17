"""Batch manifests in JSON and CSV."""

import json

import pytest

from newsworker.batch import BatchResult, write_manifest


def test_manifest_json_csv(tmp_path):
    records = [
        BatchResult("https://a", "success", output_path="a.json", item_count=2),
        BatchResult("https://b", "failure", error_type="Timeout", error="timed out"),
    ]
    json_path = tmp_path / "manifest.json"
    csv_path = tmp_path / "manifest.csv"
    write_manifest(records, str(json_path), "json")
    write_manifest(records, str(csv_path), "csv")
    assert json.loads(json_path.read_text())[1]["status"] == "failure"
    assert "error_type" in csv_path.read_text()
    with pytest.raises(ValueError):
        write_manifest(records, str(tmp_path / "x"), "xml")
