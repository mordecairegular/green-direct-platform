"""Centralized UI field labels.

The technical data model keeps stable English field names. The Streamlit UI
uses these Chinese labels for display and user-facing ad-hoc downloads.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


FIELD_LABELS = {
    "scenario_id": "方案编号",
    "pv_capacity": "光伏容量(万kW)",
    "wind_capacity": "风电容量(万kW)",
    "bess_power": "储能功率(万kW)",
    "bess_energy": "储能容量(万kWh)",
    "bess_duration": "储能时长(h)",
    "bess_c_rate": "储能倍率",
    "total_load_energy": "年用电量(万kWh)",
    "total_renewable_generation": "新能源可发电量(万kWh)",
    "pv_station_use_energy": "光伏站用电量(万kWh)",
    "wind_station_use_energy": "风电站用电量(万kWh)",
    "station_use_energy": "站用电量(万kWh)",
    "direct_self_use_energy": "直接自发自用电量(万kWh)",
    "bess_discharge_to_load": "储能供负荷电量(万kWh)",
    "self_use_energy": "自发自用电量(万kWh)",
    "grid_import_energy": "下网电量(万kWh)",
    "grid_import_rate": "下网比例",
    "grid_export_energy": "上网电量(万kWh)",
    "export_cap_energy": "允许上网额度(万kWh)",
    "curtail_energy": "弃电量(万kWh)",
    "curtail_due_to_export_cap_energy": "因上网比例限额弃电(万kWh)",
    "curtail_due_to_exchange_limit_energy": "因交换功率限制弃电(万kWh)",
    "exchange_import_shortfall_energy": "下网受限缺口电量(万kWh)",
    "bess_charge_energy": "储能充电量(万kWh)",
    "bess_loss_energy": "储能损耗(万kWh)",
    "self_use_rate": "新能源消纳率",
    "green_load_rate": "绿电占用电比例",
    "export_rate": "上网比例",
    "curtail_rate": "弃电率",
    "annual_equivalent_cycles": "储能年等效循环次数",
    "replacement_year": "储能估算更换年",
    "max_grid_import_power": "最大下网功率(万kW)",
    "max_grid_export_power": "最大上网功率(万kW)",
    "grid_exchange_power_limit": "电网交换功率限制(万kW)",
    "final_soc": "期末SOC",
    "export_control_mode": "上网控制模式",
    "pass_policy": "政策达标",
    "fail_reasons": "未达标原因",
    "dispatch_strategy": "调度策略",
    "方案类型": "方案类型",
    "timestamp": "时间",
    "hour_index": "小时序号",
    "load_power": "负荷功率(万kW)",
    "pv_power": "光伏净功率(万kW)",
    "wind_power": "风电净功率(万kW)",
    "pv_generation_power": "光伏发电功率(万kW)",
    "wind_generation_power": "风电发电功率(万kW)",
    "renewable_generation_power": "新能源可发功率(万kW)",
    "pv_station_use_power": "光伏站用功率(万kW)",
    "wind_station_use_power": "风电站用功率(万kW)",
    "station_use_power": "站用功率(万kW)",
    "renewable_power": "新能源净可用功率(万kW)",
    "direct_self_use_power": "直接自用功率(万kW)",
    "bess_charge_power": "储能充电功率(万kW)",
    "bess_discharge_power": "储能放电功率(万kW)",
    "grid_import_power": "下网功率(万kW)",
    "grid_export_power": "上网功率(万kW)",
    "curtail_power": "弃电功率(万kW)",
    "curtail_due_to_export_cap_power": "因上网比例限额弃电功率(万kW)",
    "curtail_due_to_exchange_limit_power": "因交换功率限制弃电功率(万kW)",
    "exchange_import_shortfall_power": "下网受限缺口功率(万kW)",
    "soc_start": "期初SOC",
    "soc_end": "期末SOC",
    "bess_energy_start": "期初储能电量(万kWh)",
    "bess_energy_end": "期末储能电量(万kWh)",
    "hour_case": "小时状态",
    "fnpv": "财务净现值FNPV(万元)",
    "firr": "财务内部收益率FIRR",
    "firr_status": "FIRR状态",
    "static_payback_year": "静态回收期(年)",
    "dynamic_payback_year": "动态回收期(年)",
    "construction_cash_outflow": "建设投资现金流出(万元)",
    "dedicated_connection_line_investment_with_vat": "送出线路工程投资(万元,含税)",
    "bess_replacement_depreciation": "储能更换折旧(万元)",
    "dedicated_connection_line_depreciation": "送出线路折旧(万元)",
    "annual_operating_revenue_with_vat": "年营业收入(万元,含税)",
    "annual_operating_cost_with_vat": "年运行成本(万元,含税)",
    "bess_replacement_operation_year": "首次储能更换运营年",
    "bess_replacement_operation_years": "储能更换运营年列表",
    "bess_replacement_count": "储能更换次数",
}


PERCENT_COLUMNS = {
    "grid_import_rate",
    "self_use_rate",
    "green_load_rate",
    "export_rate",
    "curtail_rate",
    "final_soc",
    "min_soc",
    "max_soc",
    "soc_start",
    "soc_end",
    "firr",
}

ENERGY_COLUMNS = {
    "total_load_energy",
    "load_energy",
    "grid_import_energy",
    "total_renewable_generation",
    "pv_station_use_energy",
    "wind_station_use_energy",
    "station_use_energy",
    "direct_self_use_energy",
    "self_use_energy",
    "grid_export_energy",
    "export_cap_energy",
    "curtail_energy",
    "curtail_due_to_export_cap_energy",
    "curtail_due_to_exchange_limit_energy",
    "exchange_import_shortfall_energy",
    "bess_charge_energy",
    "bess_discharge_to_load",
    "bess_loss_energy",
    "bess_energy",
}

MONEY_COLUMNS = {
    "fnpv",
    "construction_cash_outflow",
    "annual_operating_revenue_with_vat",
    "annual_operating_cost_with_vat",
    "grid_export_revenue_with_vat",
    "self_use_revenue_with_vat",
    "other_operating_revenue_with_vat",
    "operating_revenue_with_vat",
    "operating_revenue_without_vat",
    "wind_om_cost_with_vat",
    "pv_om_cost_with_vat",
    "bess_om_cost_with_vat",
    "other_operating_cost_with_vat",
    "operating_cost_with_vat",
    "operating_cost_without_vat",
    "construction_input_vat",
    "bess_replacement_input_vat",
    "input_vat",
    "vat_credit_begin",
    "vat_payable",
    "vat_credit_end",
    "urban_maintenance_tax",
    "education_surcharge",
    "local_education_surcharge",
    "taxes_and_surcharges",
    "wind_depreciation",
    "pv_depreciation",
    "bess_depreciation",
    "bess_replacement_depreciation",
    "dedicated_connection_line_depreciation",
    "other_fixed_asset_depreciation",
    "depreciation",
    "profit_before_tax",
    "loss_offset",
    "taxable_income",
    "income_tax",
    "net_profit",
    "bess_replacement_cash_outflow",
    "net_cash_flow",
    "cumulative_net_cash_flow",
    "discounted_net_cash_flow",
    "cumulative_discounted_net_cash_flow",
}

TWO_DECIMAL_COLUMNS = {
    "pv_capacity",
    "wind_capacity",
    "bess_power",
    "bess_duration",
    "bess_c_rate",
    "max_grid_import_power",
    "max_grid_export_power",
    "grid_exchange_power_limit",
}

ONE_DECIMAL_COLUMNS = {
    "static_payback_year",
    "dynamic_payback_year",
    "replacement_year",
}

INTEGER_COLUMNS = {
    "hour_index",
    "bess_replacement_operation_year",
    "bess_replacement_count",
    "annual_equivalent_cycles",
}


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _format_number(value: Any, digits: int, *, trim_trailing_zeros: bool = False) -> str:
    if _is_blank(value):
        return ""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if pd.isna(numeric):
        return ""
    if numeric == float("inf") or numeric == float("-inf"):
        return ""
    formatted = f"{numeric:,.{digits}f}"
    if trim_trailing_zeros and "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted


def format_display_value(column: str, value: Any) -> Any:
    if column in PERCENT_COLUMNS:
        if _is_blank(value):
            return ""
        try:
            return f"{float(value):.1%}"
        except (TypeError, ValueError):
            return str(value)
    if column in ENERGY_COLUMNS or column in INTEGER_COLUMNS:
        return _format_number(value, 0)
    if column in MONEY_COLUMNS:
        return _format_number(value, 0)
    if column in ONE_DECIMAL_COLUMNS:
        return _format_number(value, 1)
    if column in TWO_DECIMAL_COLUMNS:
        return _format_number(value, 2, trim_trailing_zeros=True)
    if isinstance(value, (int, float)) and not _is_blank(value):
        return _format_number(value, 2, trim_trailing_zeros=True)
    return value


def format_display_frame(df: pd.DataFrame) -> pd.DataFrame:
    display = df.copy()
    for column in display.columns:
        if column in PERCENT_COLUMNS | ENERGY_COLUMNS | MONEY_COLUMNS | TWO_DECIMAL_COLUMNS | ONE_DECIMAL_COLUMNS | INTEGER_COLUMNS:
            display[column] = display[column].map(lambda value, col=column: format_display_value(col, value))
    return display


def localize_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={column: FIELD_LABELS.get(column, column) for column in df.columns})


def mapping_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "中文名": [FIELD_LABELS.get(column, column) for column in columns],
            "英文原名": columns,
        }
    )
