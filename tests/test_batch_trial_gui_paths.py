from pathlib import Path
import sys

from green_direct.ui.batch_trial_gui import application_dir, bundled_resource_dir


def test_application_dir_uses_exe_parent_when_frozen(monkeypatch, tmp_path):
    exe = tmp_path / "GreenDirectBatchTrial.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))

    assert application_dir() == tmp_path


def test_bundled_resource_dir_uses_meipass_when_frozen(monkeypatch, tmp_path):
    internal = tmp_path / "_internal"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(internal), raising=False)

    assert bundled_resource_dir() == internal


def test_bundled_resource_dir_uses_cwd_in_source_run(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.chdir(tmp_path)

    assert bundled_resource_dir() == Path.cwd()
