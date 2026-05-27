import pandas as pd

from green_direct.economy import EconomicParams
from green_direct.recommendation import (
    RecommendationParams,
    build_recommendation_portfolio,
    build_recommendation_result,
    calculate_load_side_benefit_table,
    select_engineering_representative,
    select_load_side_tradable_recommendation,
    select_power_side_firr_recommendation,
    select_single_entity_firr_recommendation,
)


def _summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "scenario_id": "S_HIGH_LOAD_LOW_FIRR",
                "pass_policy": True,
                "self_use_energy": 200.0,
                "green_load_rate": 0.60,
                "self_use_rate": 0.70,
                "curtail_rate": 0.02,
                "curtail_energy": 2.0,
                "wind_capacity": 10.0,
                "pv_capacity": 5.0,
                "bess_energy": 4.0,
            },
            {
                "scenario_id": "S_TRADABLE",
                "pass_policy": True,
                "self_use_energy": 100.0,
                "green_load_rate": 0.50,
                "self_use_rate": 0.65,
                "curtail_rate": 0.04,
                "curtail_energy": 4.0,
                "wind_capacity": 6.0,
                "pv_capacity": 5.0,
                "bess_energy": 2.0,
            },
            {
                "scenario_id": "S_LOW_CURTAIL",
                "pass_policy": True,
                "self_use_energy": 80.0,
                "green_load_rate": 0.45,
                "self_use_rate": 0.60,
                "curtail_rate": 0.01,
                "curtail_energy": 1.0,
                "wind_capacity": 4.0,
                "pv_capacity": 5.0,
                "bess_energy": 1.0,
            },
        ]
    )


def _power_economy() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "scenario_id": "S_HIGH_LOAD_LOW_FIRR",
                "firr": 0.05,
                "firr_status": "ok",
                "static_payback_year": 12.0,
                "construction_cash_outflow": 1000.0,
            },
            {
                "scenario_id": "S_TRADABLE",
                "firr": 0.08,
                "firr_status": "ok",
                "static_payback_year": 9.0,
                "construction_cash_outflow": 800.0,
            },
            {
                "scenario_id": "S_LOW_CURTAIL",
                "firr": 0.09,
                "firr_status": "ok",
                "static_payback_year": 8.0,
                "construction_cash_outflow": 700.0,
            },
        ]
    )


def _single_entity_economy() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "scenario_id": "S_HIGH_LOAD_LOW_FIRR",
                "single_entity_firr_pre_tax": 0.11,
                "single_entity_firr_status": "ok",
                "single_entity_static_payback_year": 8.0,
                "single_entity_dynamic_payback_year": 10.0,
                "single_entity_fnpv_pre_tax": 300.0,
            },
            {
                "scenario_id": "S_TRADABLE",
                "single_entity_firr_pre_tax": 0.13,
                "single_entity_firr_status": "ok",
                "single_entity_static_payback_year": 7.0,
                "single_entity_dynamic_payback_year": 9.0,
                "single_entity_fnpv_pre_tax": 500.0,
            },
            {
                "scenario_id": "S_LOW_CURTAIL",
                "single_entity_firr_pre_tax": 0.09,
                "single_entity_firr_status": "ok",
                "single_entity_static_payback_year": 10.0,
                "single_entity_dynamic_payback_year": 12.0,
                "single_entity_fnpv_pre_tax": 100.0,
            },
        ]
    )


def test_load_side_tradable_recommendation_filters_by_power_side_firr_threshold():
    table = calculate_load_side_benefit_table(
        _summary(),
        _power_economy(),
        RecommendationParams(
            load_side_avoided_charge_price=0.50,
            green_power_settlement_price_with_vat=0.30,
            min_power_side_acceptable_firr=0.07,
        ),
    )

    selected = select_load_side_tradable_recommendation(table)

    assert selected["scenario_id"] == "S_TRADABLE"
    assert selected["load_side_annual_benefit"] == 20.0
    assert selected["recommendation_status"] == "selected"


def test_load_side_recommendation_is_pending_when_threshold_is_blank():
    table = calculate_load_side_benefit_table(
        _summary(),
        _power_economy(),
        RecommendationParams(
            load_side_avoided_charge_price=0.50,
            green_power_settlement_price_with_vat=0.30,
            min_power_side_acceptable_firr=None,
        ),
    )

    selected = select_load_side_tradable_recommendation(table)

    assert selected["recommendation_status"] == "pending"
    assert selected["scenario_id"] == ""
    assert "缺少" in selected["recommendation_reason"]


def test_engineering_representative_defaults_to_low_curtail_policy_passed_candidate():
    selected = select_engineering_representative(
        _summary(),
        "low_curtail",
        power_economy_summary=_power_economy(),
        economic_params=EconomicParams(),
    )

    assert selected["scenario_id"] == "S_LOW_CURTAIL"
    assert selected["recommendation_status"] == "selected"


def test_power_side_firr_recommendation_selects_highest_policy_passed_reliable_firr():
    selected = select_power_side_firr_recommendation(
        _summary(),
        _power_economy(),
        economic_params=EconomicParams(),
    )

    assert selected["scenario_id"] == "S_LOW_CURTAIL"
    assert selected["recommendation_status"] == "selected"
    assert "电源侧 FIRR 最优" in selected["recommendation_labels"]


def test_single_entity_firr_recommendation_selects_highest_policy_passed_reliable_firr():
    selected = select_single_entity_firr_recommendation(
        _summary(),
        _single_entity_economy(),
        power_economy_summary=_power_economy(),
        economic_params=EconomicParams(),
    )

    assert selected["scenario_id"] == "S_TRADABLE"
    assert selected["recommendation_status"] == "selected"
    assert "同一主体 FIRR 最优" in selected["recommendation_labels"]


def test_recommendation_result_builds_four_default_seats_after_economy_run():
    portfolio, _ = build_recommendation_result(
        _summary(),
        _power_economy(),
        RecommendationParams(
            load_side_avoided_charge_price=0.50,
            green_power_settlement_price_with_vat=0.30,
            min_power_side_acceptable_firr=0.07,
        ),
        single_entity_summary=_single_entity_economy(),
        economic_params=EconomicParams(),
    )

    labels = "；".join(portfolio["recommendation_labels"].astype(str).tolist())
    assert "同一主体 FIRR 最优" in labels
    assert "电源侧 FIRR 最优" in labels
    assert "负荷侧可成交收益最优" in labels
    assert "低弃电工程代表" in labels
    assert set(portfolio["recommendation_status"]) == {"selected"}


def test_duplicate_seat_merge_keeps_metrics_from_later_matching_seats():
    portfolio, _ = build_recommendation_result(
        _summary(),
        _power_economy(),
        RecommendationParams(
            load_side_avoided_charge_price=0.50,
            green_power_settlement_price_with_vat=0.30,
            min_power_side_acceptable_firr=0.07,
        ),
        single_entity_summary=_single_entity_economy(),
        economic_params=EconomicParams(),
    )

    selected = portfolio[portfolio["scenario_id"] == "S_TRADABLE"].iloc[0]
    assert "同一主体 FIRR 最优" in selected["recommendation_labels"]
    assert "负荷侧可成交收益最优" in selected["recommendation_labels"]
    assert selected["single_entity_firr_pre_tax"] == 0.13
    assert selected["load_side_annual_benefit"] == 20.0
    assert selected["load_side_saving_price"] == 0.20


def test_recommendation_portfolio_merges_duplicate_scenario_labels():
    portfolio = build_recommendation_portfolio(
        [
            {
                "seat_id": "load_side_tradable_benefit",
                "recommendation_labels": "负荷侧可成交收益最优",
                "recommendation_status": "selected",
                "scenario_id": "S_TRADABLE",
                "recommendation_reason": "负荷侧收益最高。",
            },
            {
                "seat_id": "engineering_min_investment",
                "recommendation_labels": "政策达标最小投资",
                "recommendation_status": "selected",
                "scenario_id": "S_TRADABLE",
                "recommendation_reason": "投资最低。",
            },
        ]
    )

    selected = portfolio[portfolio["scenario_id"] == "S_TRADABLE"].iloc[0]
    assert "负荷侧可成交收益最优" in selected["recommendation_labels"]
    assert "政策达标最小投资" in selected["recommendation_labels"]
    assert len(portfolio) == 1
