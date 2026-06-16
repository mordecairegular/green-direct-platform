from pathlib import Path

import pytest

from green_direct.services.local_store_utils import local_store_lock, read_json, write_json


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


def test_local_store_lock_blocks_same_lock_name_until_released(tmp_path):
    with local_store_lock(tmp_path, name="job_store"):
        with pytest.raises(TimeoutError, match="job_store"):
            with local_store_lock(
                tmp_path,
                name="job_store",
                timeout_seconds=0.01,
                poll_interval_seconds=0.001,
            ):
                pass

    with local_store_lock(tmp_path, name="job_store", timeout_seconds=0.01):
        pass
