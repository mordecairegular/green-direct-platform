from pathlib import Path

import pytest

from green_direct.services.local_store_utils import read_json, write_json


def test_write_json_creates_parent_directories_and_cleans_temp_files(tmp_path):
    path = tmp_path / "nested" / "record.json"

    write_json(path, {"value": "ok"})

    assert read_json(path) == {"value": "ok"}
    assert list(path.parent.glob(f".{path.name}.*.tmp")) == []


def test_write_json_keeps_existing_file_when_atomic_replace_fails(tmp_path, monkeypatch):
    path = tmp_path / "record.json"
    write_json(path, {"value": "old"})

    def fail_replace(self, target):
        raise RuntimeError("replace failed")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(RuntimeError, match="replace failed"):
        write_json(path, {"value": "new"})

    assert read_json(path) == {"value": "old"}
    assert list(path.parent.glob(f".{path.name}.*.tmp")) == []
