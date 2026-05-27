"""Recommendation V1 scenario seats.

Recommendation reads technical and economic summaries. It must not mutate
hourly dispatch results or silently recompute technical metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

import pandas as pd

from green_direct.economy import EconomicParams


ENGINEERING_VIEW_LABELS = {
    "low_curtail": "低弃电工程代表",
    "min_investment": "政策达标最小投资",
    "high_green_load": "高绿电占比",
    "high_self_use": "高自发自用",
}


@dataclass(frozen=True)
class RecommendationParams:
    """Shared inputs for Recommendation V1."""

    load_side_avoided_charge_price: float
    green_power_settlement_price_with_vat: float
    environmental_value_per_kwh: float = 0.0
    min_power_side_acceptable_firr: float | None = 0.07
    engineering_view: str = "low_curtail"


def _scenario_id_series(frame: pd.DataFrame) -> pd.Series:
    if "scenario_id" not in frame.columns:
        raise ValueError("summary must include scenario_id.")
    return frame["scenario_id"].astype(str)


def _policy_candidates(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return summary.copy()
    data = summary.copy()
    data["scenario_id"] = _scenario_id_series(data)
    if "pass_policy" in data.columns:
        return data[data["pass_policy"] == True].copy()  # noqa: E712
    return data


def _numeric_column(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(default).astype(float)


def estimate_initial_investment_with_vat(
    summary: pd.DataFrame,
    params: EconomicParams,
) -> pd.Series:
    """Estimate Year 0 construction investment from technical capacities."""

    return (
        _numeric_column(summary, "wind_capacity") * params.wind_capex_per_kw_with_vat
        + _numeric_column(summary, "pv_capacity") * params.pv_capex_per_kw_with_vat
        + _numeric_column(summary, "bess_energy") * params.bess_capex_per_kwh_with_vat
        + params.dedicated_connection_line_investment_with_vat
        + params.other_fixed_asset_investment_with_vat
    )


def _merge_power_economy(
    summary: pd.DataFrame,
    power_economy_summary: pd.DataFrame | None,
    economic_params: EconomicParams | None,
) -> pd.DataFrame:
    data = summary.copy()
    data["scenario_id"] = _scenario_id_series(data)
    if economic_params is not None:
        data["estimated_initial_investment_with_vat"] = estimate_initial_investment_with_vat(
            data,
            economic_params,
        )
    else:
        data["estimated_initial_investment_with_vat"] = pd.NA

    if power_economy_summary is None or power_economy_summary.empty:
        data["firr"] = pd.NA
        data["firr_status"] = pd.NA
        data["static_payback_year"] = pd.NA
        data["dynamic_payback_year"] = pd.NA
        data["fnpv"] = pd.NA
        data["construction_cash_outflow"] = data["estimated_initial_investment_with_vat"]
        return data

    econ_columns = [
        column
        for column in [
            "scenario_id",
            "firr",
            "firr_status",
            "static_payback_year",
            "dynamic_payback_year",
            "fnpv",
            "construction_cash_outflow",
        ]
        if column in power_economy_summary.columns
    ]
    econ = power_economy_summary[econ_columns].copy()
    econ["scenario_id"] = _scenario_id_series(econ)
    merged = data.merge(econ, on="scenario_id", how="left")
    if "construction_cash_outflow" not in merged.columns:
        merged["construction_cash_outflow"] = merged["estimated_initial_investment_with_vat"]
    else:
        merged["construction_cash_outflow"] = merged["construction_cash_outflow"].fillna(
            merged["estimated_initial_investment_with_vat"]
        )
    for column in ["firr", "firr_status", "static_payback_year", "dynamic_payback_year", "fnpv"]:
        if column not in merged.columns:
            merged[column] = pd.NA
    return merged


def _merge_single_entity_economy(
    summary: pd.DataFrame,
    single_entity_summary: pd.DataFrame | None,
    *,
    power_economy_summary: pd.DataFrame | None = None,
    economic_params: EconomicParams | None = None,
) -> pd.DataFrame:
    data = _merge_power_economy(summary, power_economy_summary, economic_params)
    if single_entity_summary is None or single_entity_summary.empty:
        data["single_entity_firr_pre_tax"] = pd.NA
        data["single_entity_firr_status"] = pd.NA
        data["single_entity_static_payback_year"] = pd.NA
        data["single_entity_dynamic_payback_year"] = pd.NA
        data["single_entity_fnpv_pre_tax"] = pd.NA
        return data

    econ_columns = [
        column
        for column in [
            "scenario_id",
            "single_entity_firr_pre_tax",
            "single_entity_firr_status",
            "single_entity_static_payback_year",
            "single_entity_dynamic_payback_year",
            "single_entity_fnpv_pre_tax",
            "initial_investment_basis",
            "construction_cash_outflow_with_vat",
            "annual_self_use_saving",
            "annual_avoided_grid_purchase_cash_saving",
            "annual_environmental_value",
            "annual_grid_export_revenue_without_vat",
            "annual_operating_cost_basis",
            "net_avoided_grid_cost_price",
            "avoided_grid_purchase_cash_price",
        ]
        if column in single_entity_summary.columns
    ]
    econ = single_entity_summary[econ_columns].copy()
    econ["scenario_id"] = _scenario_id_series(econ)
    merged = data.merge(econ, on="scenario_id", how="left")
    for column in [
        "single_entity_firr_pre_tax",
        "single_entity_firr_status",
        "single_entity_static_payback_year",
        "single_entity_dynamic_payback_year",
        "single_entity_fnpv_pre_tax",
    ]:
        if column not in merged.columns:
            merged[column] = pd.NA
    return merged


def _finite_numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    values = pd.to_numeric(frame[column], errors="coerce")
    return values.map(lambda value: isfinite(float(value)) if pd.notna(value) else False)


def _sort_by_available_columns(
    candidates: pd.DataFrame,
    sort_plan: list[tuple[str, bool]],
) -> pd.DataFrame:
    columns = [column for column, _ in sort_plan if column in candidates.columns]
    ascending = [ascending for column, ascending in sort_plan if column in candidates.columns]
    if not columns:
        return candidates
    return candidates.sort_values(columns, ascending=ascending, na_position="last")


def calculate_load_side_benefit_table(
    summary: pd.DataFrame,
    power_economy_summary: pd.DataFrame | None,
    params: RecommendationParams,
    *,
    economic_params: EconomicParams | None = None,
) -> pd.DataFrame:
    """Calculate load-side benefit and tradability flags for all scenarios."""

    data = _merge_power_economy(summary, power_economy_summary, economic_params)
    self_use_energy = _numeric_column(data, "self_use_energy")
    saving_price = (
        float(params.load_side_avoided_charge_price)
        - float(params.green_power_settlement_price_with_vat)
    )
    data["load_side_avoided_charge_price"] = float(params.load_side_avoided_charge_price)
    data["green_power_settlement_price_with_vat"] = float(
        params.green_power_settlement_price_with_vat
    )
    data["load_side_saving_price"] = saving_price
    data["load_side_environmental_value"] = (
        self_use_energy * float(params.environmental_value_per_kwh)
    )
    data["load_side_cash_saving_without_environment"] = self_use_energy * saving_price
    data["load_side_annual_benefit"] = (
        data["load_side_cash_saving_without_environment"] + data["load_side_environmental_value"]
    )
    data["power_side_firr_threshold"] = (
        pd.NA if params.min_power_side_acceptable_firr is None else params.min_power_side_acceptable_firr
    )

    if params.min_power_side_acceptable_firr is None:
        data["load_side_tradable"] = False
        data["load_side_tradable_status"] = "missing_min_power_side_firr"
        return data

    if "firr_status" in data.columns:
        firr_reliable = data["firr_status"].astype(str).eq("ok")
    else:
        firr_reliable = data["firr"].notna()
    firr_numeric = pd.to_numeric(data["firr"], errors="coerce")
    policy_ok = data["pass_policy"] == True if "pass_policy" in data.columns else True  # noqa: E712
    benefit_positive = data["load_side_annual_benefit"] > 0
    power_side_ok = firr_reliable & (firr_numeric >= float(params.min_power_side_acceptable_firr))
    data["load_side_tradable"] = policy_ok & benefit_positive & power_side_ok
    data["load_side_tradable_status"] = "ok"
    data.loc[~policy_ok, "load_side_tradable_status"] = "policy_failed"
    data.loc[policy_ok & ~benefit_positive, "load_side_tradable_status"] = "load_side_benefit_not_positive"
    data.loc[
        policy_ok & benefit_positive & ~firr_reliable,
        "load_side_tradable_status",
    ] = "power_side_firr_not_reliable"
    data.loc[
        policy_ok & benefit_positive & firr_reliable & ~power_side_ok,
        "load_side_tradable_status",
    ] = "power_side_firr_below_threshold"
    return data


def _base_recommendation_row(
    *,
    seat_id: str,
    seat_label: str,
    status: str,
    reason: str,
    risk_note: str = "",
) -> dict[str, Any]:
    return {
        "seat_id": seat_id,
        "recommendation_labels": seat_label,
        "recommendation_status": status,
        "scenario_id": "",
        "recommendation_reason": reason,
        "risk_note": risk_note,
    }


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def select_load_side_tradable_recommendation(load_side_table: pd.DataFrame) -> dict[str, Any]:
    """Select the load-side tradable benefit recommendation seat."""

    seat = _base_recommendation_row(
        seat_id="load_side_tradable_benefit",
        seat_label="负荷侧可成交收益最优",
        status="pending",
        reason="待电源侧经济性评价和电源侧最低可接受 FIRR。",
    )
    if load_side_table.empty:
        return {**seat, "recommendation_status": "no_candidate", "recommendation_reason": "没有可推荐候选方案。"}
    if load_side_table["load_side_tradable_status"].eq("missing_min_power_side_firr").all():
        return {
            **seat,
            "recommendation_reason": "缺少电源侧最低可接受 FIRR，无法判断负荷侧方案可成交性。",
        }
    candidates = load_side_table[load_side_table["load_side_tradable"] == True].copy()  # noqa: E712
    if candidates.empty:
        reason_counts = (
            load_side_table["load_side_tradable_status"].value_counts(dropna=False).to_dict()
            if "load_side_tradable_status" in load_side_table.columns
            else {}
        )
        return {
            **seat,
            "recommendation_status": "no_candidate",
            "recommendation_reason": f"没有同时满足负荷侧收益为正和电源侧 FIRR 门槛的方案：{reason_counts}",
        }

    sort_columns = [
        "load_side_annual_benefit",
        "firr",
        "static_payback_year",
        "construction_cash_outflow",
        "green_load_rate",
        "curtail_rate",
    ]
    sort_columns = [column for column in sort_columns if column in candidates.columns]
    ascending = []
    for column in sort_columns:
        ascending.append(column in {"static_payback_year", "construction_cash_outflow", "curtail_rate"})
    best = candidates.sort_values(sort_columns, ascending=ascending, na_position="last").iloc[0]
    row = best.to_dict()
    row.update(
        {
            "seat_id": "load_side_tradable_benefit",
            "recommendation_labels": "负荷侧可成交收益最优",
            "recommendation_status": "selected",
            "recommendation_reason": "在电源侧 FIRR 达到最低可接受水平的候选集中，负荷侧年度综合用能收益最高。",
            "risk_note": "",
        }
    )
    return row


def select_power_side_firr_recommendation(
    summary: pd.DataFrame,
    power_economy_summary: pd.DataFrame | None,
    *,
    economic_params: EconomicParams | None = None,
) -> dict[str, Any]:
    """Select the power-side FIRR recommendation seat."""

    seat = _base_recommendation_row(
        seat_id="power_side_firr_best",
        seat_label="电源侧 FIRR 最优",
        status="pending",
        reason="待电源侧经济性评价。",
    )
    if summary.empty:
        return {**seat, "recommendation_status": "no_candidate", "recommendation_reason": "没有技术候选方案。"}
    if power_economy_summary is None or power_economy_summary.empty:
        return seat

    merged = _merge_power_economy(summary, power_economy_summary, economic_params)
    candidates = _policy_candidates(merged)
    if candidates.empty:
        return {
            **seat,
            "recommendation_status": "no_candidate",
            "recommendation_reason": "没有政策达标方案，无法选择电源侧 FIRR 最优方案。",
        }
    if "firr" not in candidates.columns:
        return seat

    firr_reliable = _finite_numeric(candidates, "firr")
    if "firr_status" in candidates.columns:
        firr_reliable &= candidates["firr_status"].astype(str).eq("ok")
    candidates = candidates[firr_reliable].copy()
    if candidates.empty:
        return {
            **seat,
            "recommendation_status": "no_candidate",
            "recommendation_reason": "政策达标方案中没有 FIRR 状态为 ok 且数值可靠的电源侧经济性结果。",
        }

    best = _sort_by_available_columns(
        candidates,
        [
            ("firr", False),
            ("static_payback_year", True),
            ("dynamic_payback_year", True),
            ("fnpv", False),
            ("construction_cash_outflow", True),
            ("green_load_rate", False),
            ("curtail_rate", True),
        ],
    ).iloc[0]
    row = best.to_dict()
    row.update(
        {
            "seat_id": "power_side_firr_best",
            "recommendation_labels": "电源侧 FIRR 最优",
            "recommendation_status": "selected",
            "recommendation_reason": "在政策达标且电源侧 FIRR 可可靠计算的候选集中，FIRR 最高。",
            "risk_note": "",
        }
    )
    return row


def select_single_entity_firr_recommendation(
    summary: pd.DataFrame,
    single_entity_summary: pd.DataFrame | None,
    *,
    power_economy_summary: pd.DataFrame | None = None,
    economic_params: EconomicParams | None = None,
) -> dict[str, Any]:
    """Select the same-investor FIRR recommendation seat."""

    seat = _base_recommendation_row(
        seat_id="single_entity_firr_best",
        seat_label="同一主体 FIRR 最优",
        status="pending",
        reason="待同一主体税前经济性评价。",
    )
    if summary.empty:
        return {**seat, "recommendation_status": "no_candidate", "recommendation_reason": "没有技术候选方案。"}
    if single_entity_summary is None or single_entity_summary.empty:
        return seat

    merged = _merge_single_entity_economy(
        summary,
        single_entity_summary,
        power_economy_summary=power_economy_summary,
        economic_params=economic_params,
    )
    candidates = _policy_candidates(merged)
    if candidates.empty:
        return {
            **seat,
            "recommendation_status": "no_candidate",
            "recommendation_reason": "没有政策达标方案，无法选择同一主体 FIRR 最优方案。",
        }
    if "single_entity_firr_pre_tax" not in candidates.columns:
        return seat

    firr_reliable = _finite_numeric(candidates, "single_entity_firr_pre_tax")
    if "single_entity_firr_status" in candidates.columns:
        firr_reliable &= candidates["single_entity_firr_status"].astype(str).eq("ok")
    candidates = candidates[firr_reliable].copy()
    if candidates.empty:
        return {
            **seat,
            "recommendation_status": "no_candidate",
            "recommendation_reason": "政策达标方案中没有 FIRR 状态为 ok 且数值可靠的同一主体经济性结果。",
        }

    best = _sort_by_available_columns(
        candidates,
        [
            ("single_entity_firr_pre_tax", False),
            ("single_entity_static_payback_year", True),
            ("single_entity_dynamic_payback_year", True),
            ("single_entity_fnpv_pre_tax", False),
            ("initial_investment_basis", True),
            ("green_load_rate", False),
            ("curtail_rate", True),
        ],
    ).iloc[0]
    row = best.to_dict()
    row.update(
        {
            "seat_id": "single_entity_firr_best",
            "recommendation_labels": "同一主体 FIRR 最优",
            "recommendation_status": "selected",
            "recommendation_reason": "在政策达标且同一主体税前 FIRR 可可靠计算的候选集中，FIRR 最高。",
            "risk_note": "",
        }
    )
    return row


def _sort_engineering_candidates(candidates: pd.DataFrame, view: str) -> pd.DataFrame:
    if view == "min_investment":
        columns = ["construction_cash_outflow", "green_load_rate", "curtail_rate"]
        ascending = [True, False, True]
    elif view == "high_green_load":
        columns = ["green_load_rate", "self_use_energy", "construction_cash_outflow"]
        ascending = [False, False, True]
    elif view == "high_self_use":
        columns = ["self_use_rate", "curtail_rate", "construction_cash_outflow"]
        ascending = [False, True, True]
    else:
        columns = ["curtail_rate", "curtail_energy", "construction_cash_outflow", "green_load_rate"]
        ascending = [True, True, True, False]
    columns = [column for column in columns if column in candidates.columns]
    return candidates.sort_values(columns, ascending=ascending, na_position="last")


def select_engineering_representative(
    summary: pd.DataFrame,
    view: str,
    *,
    power_economy_summary: pd.DataFrame | None = None,
    economic_params: EconomicParams | None = None,
) -> dict[str, Any]:
    """Select one policy-compliant engineering representative scenario."""

    view = view if view in ENGINEERING_VIEW_LABELS else "low_curtail"
    label = ENGINEERING_VIEW_LABELS[view]
    base = _base_recommendation_row(
        seat_id=f"engineering_{view}",
        seat_label=label,
        status="pending",
        reason="等待技术方案汇总。",
    )
    if summary.empty:
        return {**base, "recommendation_status": "no_candidate", "recommendation_reason": "没有技术候选方案。"}

    merged = _merge_power_economy(summary, power_economy_summary, economic_params)
    candidates = _policy_candidates(merged)
    if candidates.empty:
        return {
            **base,
            "recommendation_status": "no_candidate",
            "recommendation_reason": "没有政策达标方案，无法选择工程代表方案。",
        }

    best = _sort_engineering_candidates(candidates, view).iloc[0]
    row = best.to_dict()
    row.update(
        {
            "seat_id": f"engineering_{view}",
            "recommendation_labels": label,
            "recommendation_status": "selected",
            "engineering_view": view,
            "recommendation_reason": f"在政策达标方案中按“{label}”视角排序得到。",
            "risk_note": "",
        }
    )
    return row


def build_recommendation_portfolio(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Merge selected rows that hit the same scenario into one display card."""

    if not rows:
        return pd.DataFrame()
    selected = [row for row in rows if row.get("recommendation_status") == "selected" and row.get("scenario_id")]
    pending = [row for row in rows if row not in selected]
    merged: dict[str, dict[str, Any]] = {}
    for row in selected:
        sid = str(row["scenario_id"])
        if sid not in merged:
            merged[sid] = dict(row)
            continue
        current = merged[sid]
        current["seat_id"] = f"{current.get('seat_id', '')},{row.get('seat_id', '')}"
        current["recommendation_labels"] = "；".join(
            item
            for item in [current.get("recommendation_labels", ""), row.get("recommendation_labels", "")]
            if item
        )
        current["recommendation_reason"] = "；".join(
            item
            for item in [current.get("recommendation_reason", ""), row.get("recommendation_reason", "")]
            if item
        )
        for key, value in row.items():
            if key in {
                "seat_id",
                "recommendation_labels",
                "recommendation_status",
                "recommendation_reason",
                "recommendation_rank",
            }:
                continue
            if key == "risk_note":
                if value and value not in str(current.get("risk_note", "")):
                    current["risk_note"] = "；".join(
                        item for item in [current.get("risk_note", ""), value] if item
                    )
                continue
            if key not in current or _is_missing(current.get(key)):
                current[key] = value
    ordered = list(merged.values()) + pending
    for index, row in enumerate(ordered, start=1):
        row["recommendation_rank"] = index
    return pd.DataFrame(ordered)


def build_recommendation_result(
    summary: pd.DataFrame,
    power_economy_summary: pd.DataFrame | None,
    params: RecommendationParams,
    *,
    single_entity_summary: pd.DataFrame | None = None,
    economic_params: EconomicParams | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build portfolio and load-side detail table."""

    load_side = calculate_load_side_benefit_table(
        summary,
        power_economy_summary,
        params,
        economic_params=economic_params,
    )
    rows = [
        select_single_entity_firr_recommendation(
            summary,
            single_entity_summary,
            power_economy_summary=power_economy_summary,
            economic_params=economic_params,
        ),
        select_power_side_firr_recommendation(
            summary,
            power_economy_summary,
            economic_params=economic_params,
        ),
        select_load_side_tradable_recommendation(load_side),
        select_engineering_representative(
            summary,
            params.engineering_view,
            power_economy_summary=power_economy_summary,
            economic_params=economic_params,
        ),
    ]
    return build_recommendation_portfolio(rows), load_side
