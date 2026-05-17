"""Result models."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class ScenarioResult:
    """Simulation result for one scenario."""

    summary: dict
    hourly_detail: pd.DataFrame
    warnings: list[str]
