"""Upload validation helpers for controlled pilot deployments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
from typing import Iterable


DEFAULT_MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class UploadValidationError(ValueError):
    """Raised when an uploaded file violates the configured upload policy."""


@dataclass(frozen=True)
class UploadFileInfo:
    """Safe metadata retained for one uploaded file."""

    name: str
    suffix: str
    size_bytes: int
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class UploadPolicy:
    """File type and size policy for user uploads."""

    allowed_suffixes: frozenset[str]
    max_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    allow_empty: bool = False

    def __post_init__(self) -> None:
        normalized = frozenset(_normalize_suffix(suffix) for suffix in self.allowed_suffixes)
        if not normalized:
            raise ValueError("allowed_suffixes must not be empty.")
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be positive.")
        object.__setattr__(self, "allowed_suffixes", normalized)


def _normalize_suffix(value: str) -> str:
    text = str(value).strip().lower()
    if not text:
        raise ValueError("suffix must not be empty.")
    return text if text.startswith(".") else f".{text}"


def _upload_name(uploaded_file: object) -> str:
    name = str(getattr(uploaded_file, "name", "") or "").strip()
    if not name:
        raise UploadValidationError("上传文件缺少文件名。")
    return name


def _upload_bytes(uploaded_file: object) -> bytes:
    getvalue = getattr(uploaded_file, "getvalue", None)
    if callable(getvalue):
        return bytes(getvalue())
    read = getattr(uploaded_file, "read", None)
    if callable(read):
        data = read()
        return data.encode("utf-8") if isinstance(data, str) else bytes(data)
    raise UploadValidationError("上传文件无法读取。")


def inspect_upload(uploaded_file: object, policy: UploadPolicy, *, label: str = "上传文件") -> UploadFileInfo:
    """Validate one uploaded file and return safe trace metadata."""

    name = _upload_name(uploaded_file)
    suffix = Path(name).suffix.lower()
    if suffix not in policy.allowed_suffixes:
        allowed = ", ".join(sorted(policy.allowed_suffixes))
        raise UploadValidationError(f"{label} `{name}` 文件类型不允许，仅支持：{allowed}。")

    payload = _upload_bytes(uploaded_file)
    size_bytes = len(payload)
    if size_bytes == 0 and not policy.allow_empty:
        raise UploadValidationError(f"{label} `{name}` 为空文件。")
    if size_bytes > policy.max_bytes:
        max_mb = policy.max_bytes / 1024 / 1024
        actual_mb = size_bytes / 1024 / 1024
        raise UploadValidationError(f"{label} `{name}` 超过大小限制：{actual_mb:.1f}MB > {max_mb:.1f}MB。")

    return UploadFileInfo(
        name=name,
        suffix=suffix,
        size_bytes=size_bytes,
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def filter_uploads(
    uploaded_files: Iterable[object] | None,
    policy: UploadPolicy,
    *,
    label: str = "上传文件",
) -> tuple[list[object], dict[int, UploadFileInfo], list[str]]:
    """Return valid files, info keyed by object id, and user-facing rejection messages."""

    valid_files: list[object] = []
    infos: dict[int, UploadFileInfo] = {}
    messages: list[str] = []
    for uploaded_file in uploaded_files or []:
        try:
            info = inspect_upload(uploaded_file, policy, label=label)
        except UploadValidationError as exc:
            messages.append(str(exc))
            continue
        valid_files.append(uploaded_file)
        infos[id(uploaded_file)] = info
    return valid_files, infos, messages
