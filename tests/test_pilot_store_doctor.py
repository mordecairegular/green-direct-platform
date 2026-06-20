import json

from green_direct.services import run_pilot_store_doctor


def test_pilot_store_doctor_passes_for_empty_writable_store(tmp_path):
    result = run_pilot_store_doctor(tmp_path)

    assert result.status == "pass"
    checks = {check.name: check.status for check in result.checks}
    assert checks == {
        "store:directory": "pass",
        "store:json_roundtrip": "pass",
        "store:payload_write": "pass",
        "store:lock": "pass",
        "store:json_metadata": "pass",
        "store:audit_jsonl": "pass",
    }
    assert list((tmp_path / ".doctor").glob("*")) == []


def test_pilot_store_doctor_fails_for_corrupt_metadata_json(tmp_path):
    bad_path = tmp_path / "auth" / "credentials" / "broken.json"
    bad_path.parent.mkdir(parents=True)
    bad_path.write_text("{not json", encoding="utf-8")

    result = run_pilot_store_doctor(tmp_path)

    assert result.status == "fail"
    checks = {check.name: check for check in result.checks}
    assert checks["store:json_metadata"].status == "fail"
    assert "broken.json" in checks["store:json_metadata"].message


def test_pilot_store_doctor_fails_for_corrupt_audit_jsonl(tmp_path):
    audit_path = tmp_path / "audit" / "global.jsonl"
    audit_path.parent.mkdir(parents=True)
    audit_path.write_text(json.dumps({"ok": True}) + "\n{not json\n", encoding="utf-8")

    result = run_pilot_store_doctor(tmp_path)

    assert result.status == "fail"
    checks = {check.name: check for check in result.checks}
    assert checks["store:audit_jsonl"].status == "fail"
    assert "global.jsonl:2" in checks["store:audit_jsonl"].message
