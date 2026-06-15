import hashlib

import pytest

from green_direct.services.upload_policy import (
    UploadPolicy,
    UploadValidationError,
    filter_uploads,
    inspect_upload,
)


class DummyUpload:
    def __init__(self, name: str, payload: bytes):
        self.name = name
        self._payload = payload

    def getvalue(self) -> bytes:
        return self._payload


def test_inspect_upload_returns_safe_trace_metadata():
    upload = DummyUpload("load_curve.csv", b"hour,load\n1,2\n")

    info = inspect_upload(upload, UploadPolicy(frozenset({".csv"}), max_bytes=1024), label="负荷曲线")

    assert info.name == "load_curve.csv"
    assert info.suffix == ".csv"
    assert info.size_bytes == len(upload.getvalue())
    assert info.sha256 == hashlib.sha256(upload.getvalue()).hexdigest()


def test_inspect_upload_rejects_disallowed_suffix_size_and_empty_payload():
    with pytest.raises(UploadValidationError, match="文件类型不允许"):
        inspect_upload(DummyUpload("load.exe", b"x"), UploadPolicy(frozenset({".csv"})), label="负荷曲线")

    with pytest.raises(UploadValidationError, match="超过大小限制"):
        inspect_upload(DummyUpload("load.csv", b"12345"), UploadPolicy(frozenset({".csv"}), max_bytes=4), label="负荷曲线")

    with pytest.raises(UploadValidationError, match="空文件"):
        inspect_upload(DummyUpload("load.csv", b""), UploadPolicy(frozenset({".csv"}), max_bytes=4), label="负荷曲线")


def test_filter_uploads_keeps_valid_files_and_reports_rejections():
    valid = DummyUpload("load.csv", b"ok")
    invalid = DummyUpload("load.xls", b"no")

    files, infos, messages = filter_uploads([valid, invalid], UploadPolicy(frozenset({".csv"})), label="技术曲线")

    assert files == [valid]
    assert infos[id(valid)].name == "load.csv"
    assert len(messages) == 1
    assert "load.xls" in messages[0]
