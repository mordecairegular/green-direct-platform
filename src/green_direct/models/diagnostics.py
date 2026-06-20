"""Lightweight structured diagnostics for input and run checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DiagnosticSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class InputDiagnostic:
    severity: DiagnosticSeverity
    source: str
    code: str
    message: str
    location: str | None = None
    suggestion: str | None = None


@dataclass
class InputDiagnostics:
    items: list[InputDiagnostic] = field(default_factory=list)

    def add(
        self,
        severity: DiagnosticSeverity,
        source: str,
        code: str,
        message: str,
        *,
        location: str | None = None,
        suggestion: str | None = None,
    ) -> None:
        self.items.append(
            InputDiagnostic(
                severity=severity,
                source=source,
                code=code,
                message=message,
                location=location,
                suggestion=suggestion,
            )
        )

    def extend(self, diagnostics: "InputDiagnostics") -> None:
        self.items.extend(diagnostics.items)

    def has_errors(self) -> bool:
        return any(item.severity is DiagnosticSeverity.ERROR for item in self.items)

    def warnings_as_messages(self) -> list[str]:
        return [item.message for item in self.items if item.severity is DiagnosticSeverity.WARNING]

    @classmethod
    def from_warning_messages(
        cls,
        messages: list[str],
        *,
        source: str,
        code: str,
    ) -> "InputDiagnostics":
        diagnostics = cls()
        for message in messages:
            diagnostics.add(DiagnosticSeverity.WARNING, source, code, message)
        return diagnostics
