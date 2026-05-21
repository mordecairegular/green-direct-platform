"""Result models."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from green_direct.models.diagnostics import InputDiagnostics


@dataclass
class ScenarioResult:
    """Simulation result for one scenario."""

    summary: dict
    hourly_detail: pd.DataFrame
    warnings: list[str]
    diagnostics: InputDiagnostics = field(default_factory=InputDiagnostics)
