from io import BytesIO

import pandas as pd


def test_streamlit_app_imports():
    import green_direct.ui.app as app

    assert callable(app.main)


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
