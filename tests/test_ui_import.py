from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

import pandas as pd


def test_streamlit_app_imports():
    import green_direct.ui.app as app

    assert callable(app.main)


def test_workflow_page_normalizes_legacy_and_unknown_values():
    import green_direct.ui.app as app

    class DummyStreamlit:
        def __init__(self, page):
            self.session_state = {"workflow_page": page}

    legacy = DummyStreamlit("技术仿真")
    assert app._normalize_workflow_page(legacy) == "方案仿真"
    assert legacy.session_state["workflow_page"] == "方案仿真"

    unknown = DummyStreamlit("不存在的页面")
    assert app._normalize_workflow_page(unknown) == "欢迎页"
    assert unknown.session_state["workflow_page"] == "欢迎页"


def test_go_to_workflow_page_maps_alias_and_reruns():
    import green_direct.ui.app as app

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {}
            self.did_rerun = False

        def rerun(self):
            self.did_rerun = True

    dummy = DummyStreamlit()
    app._go_to_workflow_page(dummy, "经济性评价")

    assert dummy.session_state["_workflow_page_target"] == "经济性测算"
    assert dummy.did_rerun is True


def test_welcome_start_button_does_not_mutate_radio_state_after_instantiation():
    from streamlit.testing.v1 import AppTest

    app_test = AppTest.from_file("src/green_direct/ui/app.py")
    app_test.run(timeout=10)

    next(button for button in app_test.button if button.label == "开始方案仿真").click().run(timeout=10)

    assert len(app_test.exception) == 0


def test_technical_next_button_does_not_mutate_radio_state_after_instantiation():
    from streamlit.testing.v1 import AppTest

    summary = pd.DataFrame(
        [
            {
                "scenario_id": "S0001",
                "pv_capacity": 1.0,
                "wind_capacity": 1.0,
                "bess_power": 1.0,
                "bess_energy": 2.0,
                "pass_policy": True,
                "green_load_rate": 0.3,
                "curtail_rate": 0.1,
                "grid_import_rate": 0.2,
                "self_use_rate": 0.8,
                "export_rate": 0.05,
            }
        ]
    )
    batch_result = SimpleNamespace(
        summary=summary,
        hourly_details={"S0001": pd.DataFrame({"timestamp": pd.date_range("2020-01-01", periods=24, freq="h")})},
        warnings=[],
        errors=pd.DataFrame(),
        scenario_count=1,
    )

    app_test = AppTest.from_file("src/green_direct/ui/app.py")
    app_test.session_state["workflow_page"] = "方案仿真"
    app_test.session_state["batch_result"] = batch_result
    app_test.run(timeout=10)
    next(button for button in app_test.button if button.label == "进入经济性测算").click().run(timeout=10)

    assert len(app_test.exception) == 0


def test_workflow_page_applies_queued_target_before_radio_render():
    import green_direct.ui.app as app

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {"workflow_page": "欢迎页", "_workflow_page_target": "方案仿真"}

    dummy = DummyStreamlit()

    assert app._normalize_workflow_page(dummy) == "方案仿真"
    assert dummy.session_state["workflow_page"] == "方案仿真"
    assert "_workflow_page_target" not in dummy.session_state


def test_simple_markdown_report_mentions_typical_day_method():
    from green_direct.ui.app import _build_simple_report_markdown

    summary = pd.DataFrame(
        [
            {
                "scenario_id": "S0001",
                "方案类型": "风光储方案",
                "pv_capacity": 10.0,
                "wind_capacity": 5.0,
                "bess_power": 2.0,
                "bess_energy": 4.0,
                "pass_policy": True,
                "green_load_rate": 0.4,
                "self_use_rate": 0.7,
                "export_rate": 0.1,
                "curtail_rate": 0.05,
            }
        ]
    )

    report = _build_simple_report_markdown(
        summary=summary,
        selected_scenario_id="S0001",
        economy_summary=None,
        single_entity_summary=None,
    ).decode("utf-8-sig")

    assert "季节中心日法" in report
    assert "S0001" in report


def test_topbar_data_range_uses_hourly_detail_timestamp():
    from green_direct.ui.app import _data_range_status

    batch_result = SimpleNamespace(
        hourly_details={
            "S0001": pd.DataFrame(
                {
                    "timestamp": pd.date_range("2024-01-01", periods=24, freq="h"),
                }
            )
        }
    )

    value, detail = _data_range_status(batch_result)

    assert value == "2024-01-01 ~ 2024-01-01"
    assert detail == "24 小时"


def test_recommendation_status_display_does_not_mark_no_candidate_as_ok():
    from green_direct.ui.app import _recommendation_status_display

    assert _recommendation_status_display("selected") == ("已入选", "ok")
    assert _recommendation_status_display("no_candidate") == ("无候选", "warn")
    assert _recommendation_status_display("pending") == ("待排序", "pending")


def test_first_report_scenario_prefers_valid_recommendation_portfolio_id():
    from green_direct.ui.app import _first_report_scenario_id

    summary = pd.DataFrame({"scenario_id": ["S0001", "S0002"]})
    recommendation_result = SimpleNamespace(
        portfolio=pd.DataFrame({"scenario_id": ["S9999", "S0002"]})
    )

    assert _first_report_scenario_id(summary, recommendation_result) == "S0002"


def test_default_export_scenario_prefers_current_then_recommendation():
    from green_direct.ui.app import _default_export_scenario_id

    recommendation_result = SimpleNamespace(
        portfolio=pd.DataFrame({"scenario_id": ["S9999", "S0002", "S0003"]})
    )

    assert _default_export_scenario_id(["S0001", "S0002", "S0003"], "S0003", recommendation_result) == "S0003"
    assert _default_export_scenario_id(["S0001", "S0002", "S0003"], None, recommendation_result) == "S0002"
    assert _default_export_scenario_id(["S0001", "S0002"], "S9999", None) == "S0001"


def test_dashboard_representative_summary_follows_portfolio_order():
    from green_direct.ui.app import _representative_summary_for_dashboard

    summary = pd.DataFrame(
        {
            "scenario_id": ["S0001", "S0002", "S0003"],
            "pv_capacity": [5.0, 10.0, 15.0],
            "wind_capacity": [0.0, 5.0, 10.0],
            "bess_power": [0.0, 2.0, 4.0],
            "bess_energy": [0.0, 8.0, 16.0],
        }
    )
    recommendation_result = SimpleNamespace(
        portfolio=pd.DataFrame({"scenario_id": ["S0003", "S9999", "S0001"]})
    )

    dashboard_summary = _representative_summary_for_dashboard(summary, recommendation_result)

    assert dashboard_summary["scenario_id"].tolist() == ["S0003", "S0001"]


def test_compact_dashboard_figures_use_real_fields():
    from green_direct.ui.app import _build_compact_policy_comparison_figure, _build_compact_typical_day_figure

    comparison = pd.DataFrame(
        {
            "scenario_id": ["S0001", "S0002"],
            "pv_capacity": [5.0, 10.0],
            "wind_capacity": [0.0, 5.0],
            "bess_power": [0.0, 2.0],
            "bess_energy": [0.0, 8.0],
            "green_load_rate": [0.34, 0.65],
            "self_use_rate": [0.76, 0.74],
            "curtail_rate": [0.04, 0.03],
            "export_rate": [0.20, 0.10],
        }
    )
    policy_fig, missing = _build_compact_policy_comparison_figure(comparison)

    assert missing == []
    assert policy_fig is not None
    assert [trace.name for trace in policy_fig.data] == ["绿电占比", "自发自用率", "低弃电", "低上网"]

    hourly = pd.DataFrame(
        {
            "timestamp": pd.date_range("2020-07-01", periods=48, freq="h"),
            "load_power": [20.0] * 48,
            "pv_generation_power": [0.0] * 6 + [12.0] * 10 + [0.0] * 32,
            "wind_generation_power": [6.0] * 48,
            "bess_charge_power": [0.0] * 48,
            "bess_discharge_power": [1.0] * 48,
            "grid_import_power": [8.0] * 48,
            "grid_export_power": [0.5] * 48,
            "curtail_power": [0.1] * 48,
            "soc_end": [0.5] * 48,
        }
    )
    typical_fig, label, method = _build_compact_typical_day_figure(hourly, "夏季")

    assert typical_fig is not None
    assert "/" in label
    assert "季节中心日法" in method


def test_chart_html_zip_contains_html_and_meta_files():
    from green_direct.ui.app import _build_chart_html_zip, _comparison_summary_from_portfolio

    hours = 72
    hourly = pd.DataFrame(
        {
            "scenario_id": ["S0001"] * hours,
            "timestamp": pd.date_range("2020-03-01", periods=hours, freq="h"),
            "load_power": [10.0] * hours,
            "direct_self_use_power": [4.0] * hours,
            "bess_discharge_power": [1.0] * hours,
            "grid_import_power": [5.0] * hours,
            "bess_charge_power": [0.5] * hours,
            "grid_export_power": [0.2] * hours,
            "curtail_power": [0.1] * hours,
            "renewable_power": [5.0] * hours,
            "station_use_power": [0.0] * hours,
            "soc_end": [0.5] * hours,
        }
    )
    summary = pd.DataFrame(
        {
            "scenario_id": ["S0001", "S0002", "S0003"],
            "pv_capacity": [10.0, 20.0, 30.0],
            "wind_capacity": [5.0, 10.0, 15.0],
            "bess_power": [2.0, 3.0, 4.0],
            "bess_energy": [4.0, 6.0, 8.0],
            "self_use_rate": [0.7, 0.8, 0.82],
            "green_load_rate": [0.35, 0.4, 0.42],
            "export_rate": [0.1, 0.12, 0.13],
            "curtail_rate": [0.05, 0.03, 0.02],
            "self_use_energy": [100.0, 120.0, 130.0],
            "grid_export_energy": [10.0, 12.0, 13.0],
            "curtail_energy": [5.0, 4.0, 3.0],
            "bess_loss_energy": [1.0, 1.5, 1.8],
        }
    )
    portfolio = pd.DataFrame({"scenario_id": ["S0002"]})
    comparison = _comparison_summary_from_portfolio(summary, "S0001", portfolio)

    content = _build_chart_html_zip(summary, "S0001", hourly, comparison_summary=comparison)
    names = ZipFile(BytesIO(content)).namelist()
    readme = ZipFile(BytesIO(content)).read("README.md").decode("utf-8-sig")

    assert "README.md" in names
    assert any(name.endswith(".html") for name in names)
    assert any("typical" in name and name.endswith("_meta.md") for name in names)
    typical_html = [name for name in names if name.startswith("typical_") and name.endswith(".html")]
    assert len(typical_html) == 4
    assert any("spring" in name for name in typical_html)
    assert any("winter" in name for name in typical_html)
    assert comparison["scenario_id"].tolist() == ["S0002", "S0001"]
    assert "多方案对比范围：2 个方案" in readme


def test_single_entity_annual_workbook_has_context_and_field_explanations():
    from green_direct.ui.app import _build_single_entity_annual_workbook_bytes

    scenario_id = "S0165"
    annual = pd.DataFrame(
        [
            {
                "scenario_id": scenario_id,
                "year": 0,
                "operation_year": 0,
                "period_type": "construction",
                "self_use_energy": 0.0,
                "grid_export_energy": 0.0,
                "net_avoided_grid_cost_price": 0.5,
                "avoided_grid_purchase_cash_price": 0.5,
                "self_use_saving": 0.0,
                "avoided_grid_purchase_cash_saving": 0.0,
                "environmental_value": 0.0,
                "grid_export_revenue_without_vat": 0.0,
                "other_external_revenue_without_vat": 0.0,
                "operating_cost_basis": 0.0,
                "bess_replacement_basis": 0.0,
                "bess_replacement_cash_outflow_with_vat": 0.0,
                "initial_investment_basis": 100.0,
                "construction_cash_outflow_with_vat": 110.0,
                "pre_tax_net_cash_flow": -100.0,
                "cumulative_net_cash_flow": -100.0,
                "discount_factor": 1.0,
                "discounted_net_cash_flow": -100.0,
                "cumulative_discounted_net_cash_flow": -100.0,
            }
        ]
    )
    technical_summary = pd.DataFrame(
        [
            {
                "scenario_id": scenario_id,
                "方案类型": "风光储方案",
                "pv_capacity": 10.0,
                "wind_capacity": 5.0,
                "bess_power": 2.0,
                "bess_energy": 4.0,
                "pass_policy": True,
                "green_load_rate": 0.4,
                "self_use_rate": 0.7,
                "export_rate": 0.1,
                "curtail_rate": 0.05,
            }
        ]
    )
    economic_summary = pd.DataFrame(
        [
            {
                "scenario_id": scenario_id,
                "single_entity_firr_pre_tax": 0.12,
                "single_entity_firr_status": "ok",
                "single_entity_fnpv_pre_tax": 20.0,
                "initial_investment_basis": 100.0,
                "construction_cash_outflow_with_vat": 110.0,
                "net_avoided_grid_cost_price": 0.5,
            }
        ]
    )

    content = _build_single_entity_annual_workbook_bytes(
        scenario_id=scenario_id,
        annual=annual,
        technical_summary=technical_summary,
        economic_summary=economic_summary,
    )
    workbook = pd.ExcelFile(BytesIO(content))

    assert workbook.sheet_names == ["方案说明", "年度现金流", "字段说明"]
    annual_sheet = pd.read_excel(workbook, sheet_name="年度现金流")
    field_sheet = pd.read_excel(workbook, sheet_name="字段说明")
    scenario_sheet = pd.read_excel(workbook, sheet_name="方案说明")

    assert any(str(column).startswith("1. ") for column in annual_sheet.columns)
    assert "储能容量(万kWh)" in scenario_sheet["项目"].tolist()
    assert any("=5×7" in str(value) for value in field_sheet["计算/含义说明"])
