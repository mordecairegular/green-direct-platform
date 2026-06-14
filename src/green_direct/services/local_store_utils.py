"""Shared helpers for local file-backed pilot stores."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import json
from pathlib import Path
import re
from typing import Any, Mapping


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
    path.write_text(
        json.dumps(json_value(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
