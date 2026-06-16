"""Shared helpers for local file-backed pilot stores."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping
from uuid import uuid4


_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def validate_path_segment(value: str, field_name: str) -> str:
    text = str(value)
    if not _SAFE_SEGMENT.fullmatch(text):
        raise ValueError(f"{field_name} contains unsafe path characters.")
    return text


def json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): json_value(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(json_value(payload), ensure_ascii=False, indent=2, sort_keys=True)
    tmp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
