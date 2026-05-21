"""Streamlit app for V0.1 technical batch simulation."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

import pandas as pd

SRC_ROOT = str(Path(__file__).resolve().parents[2])
if sys.path[0] != SRC_ROOT:  # pragma: no cover - import path guard for Streamlit and installed packages
    sys.path.insert(0, SRC_ROOT)
PROJECT_ROOT = Path(__file__).resolve().parents[3]

from green_direct.batch.batch_runner import estimate_scenario_count, run_batch
from green_direct.economy import EconomicParams, OtherOperatingRevenueItem, evaluate_batch_economy
from green_direct.export.csv_exporter import export_hourly_details_zip
from green_direct.export.excel_exporter import export_summary_excel
from green_direct.io.read_curves import read_csv_auto_encoding, read_curve_set
from green_direct.io.validators import DataValidationError
from green_direct.models.params import BessParams, DataCleaningParams, PerformanceParams, PolicyParams
from green_direct.ui.field_labels import localize_columns, mapping_frame
from green_direct.visualization.chart_ui import render_chart_analysis


TIME_COLUMN_CANDIDATES = ["时间", "timestamp", "time", "日期时间", "日期", "datetime"]
VALUE_COLUMN_CANDIDATES = {
    "负荷": ["负荷", "数值(万千瓦)", "load", "load_power", "负荷功率"],
    "光伏": ["光伏", "光伏（标幺）", "pv", "pv_pu"],
    "风电": ["风电", "风电（标幺）", "wind", "wind_pu"],
}
FILE_KEYWORDS = {
    "负荷": ["负荷", "load", "用电"],
    "光伏": ["光伏", "pv", "solar"],
    "风电": ["风电", "wind"],
}


class _LocalSampleFile:
    def __init__(self, path: Path):
        self.path = path
        self.name = path.name

    def getvalue(self) -> bytes:
        return self.path.read_bytes()


def _load_sample_curve_files() -> tuple[dict[str, _LocalSampleFile], list[str]]:
    sample_dir = PROJECT_ROOT / "samples"
    assigned: dict[str, _LocalSampleFile] = {}
    messages: list[str] = []
    if not sample_dir.exists():
        return assigned, ["未找到 samples 示例数据目录。"]
    for path in sample_dir.glob("*.csv"):
        curve_name = _match_curve_from_filename(path.name)
        if curve_name is None:
            messages.append(f"示例文件 `{path.name}` 未能识别曲线类型。")
            continue
        assigned[curve_name] = _LocalSampleFile(path)
    missing = {"负荷", "光伏", "风电"} - set(assigned)
    if missing:
        messages.append(f"示例数据缺少：{', '.join(sorted(missing))}。")
    return assigned, messages


def _load_preview(uploaded_file):
    if uploaded_file is None:
        return None, None
    raw = uploaded_file.getvalue()
    df, encoding = read_csv_auto_encoding(raw)
    return df, encoding


def _match_curve_from_filename(filename: str) -> str | None:
    normalized = filename.lower()
    for curve_name, keywords in FILE_KEYWORDS.items():
        if any(keyword.lower() in normalized for keyword in keywords):
            return curve_name
    return None


def _auto_assign_curve_files(files) -> tuple[dict[str, object], list[str]]:
    assigned: dict[str, object] = {}
    messages: list[str] = []
    for uploaded_file in files or []:
        curve_name = _match_curve_from_filename(uploaded_file.name)
        if curve_name is None:
            messages.append(f"未能识别文件 `{uploaded_file.name}`，请使用单独上传入口。")
            continue
        if curve_name in assigned:
            messages.append(f"`{curve_name}`匹配到多个文件，已使用 `{assigned[curve_name].name}`，忽略 `{uploaded_file.name}`。")
            continue
        assigned[curve_name] = uploaded_file
    return assigned, messages


def _guess_time_column(df: pd.DataFrame | None) -> str | None:
    if df is None:
        return None
    lower_map = {str(column).lower(): column for column in df.columns}
    for candidate in TIME_COLUMN_CANDIDATES:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    for column in df.columns:
        parsed = pd.to_datetime(df[column], errors="coerce")
        if parsed.notna().mean() > 0.95:
            return column
    return None


def _guess_value_column(df: pd.DataFrame | None, time_col: str | None, curve_name: str) -> str | None:
    if df is None:
        return None
    lower_map = {str(column).lower(): column for column in df.columns}
    for candidate in VALUE_COLUMN_CANDIDATES[curve_name]:
        if candidate.lower() in lower_map and lower_map[candidate.lower()] != time_col:
            return lower_map[candidate.lower()]
    candidates = []
    for column in df.columns:
        if column == time_col:
            continue
        numeric = pd.to_numeric(df[column], errors="coerce")
        if numeric.notna().mean() > 0.95:
            candidates.append(column)
    if len(candidates) == 1:
        return candidates[0]
    return None


def _column_selector(st, label: str, df: pd.DataFrame | None, guessed: str | None):
    if df is None:
        return None
    columns = list(df.columns)
    if guessed in columns:
        st.caption(f"{label}：已自动识别为 `{guessed}`")
        return guessed
    return st.selectbox(label, columns, index=0)


def _range_inputs(st, label: str, defaults: tuple[float, float, float]) -> dict:
    c1, c2, c3 = st.columns(3)
    start = c1.number_input(f"{label}起始", value=float(defaults[0]), min_value=0.0, step=1.0)
    end = c2.number_input(f"{label}结束", value=float(defaults[1]), min_value=0.0, step=1.0)
    step = c3.number_input(f"{label}步长", value=float(defaults[2]), min_value=0.000001, step=1.0)
    return {"start": start, "end": end, "step": step}


def _build_download_payloads(batch_result, config_snapshot: dict):
    with TemporaryDirectory() as tmp:
        excel_path = export_summary_excel(
            batch_result.summary,
            tmp,
            config_snapshot=config_snapshot,
            warnings=batch_result.warnings,
        )
        zip_path = export_hourly_details_zip(batch_result.hourly_details, tmp)
        return {
            "excel_name": excel_path.name,
            "excel_bytes": excel_path.read_bytes(),
            "zip_name": zip_path.name,
            "zip_bytes": zip_path.read_bytes(),
        }


def _curve_status(label: str, df: pd.DataFrame | None, encoding: str | None, time_col: str | None, value_col: str | None):
    if df is None or time_col is None or value_col is None:
        return None
    parsed = pd.to_datetime(df[time_col], errors="coerce")
    numeric = pd.to_numeric(df[value_col], errors="coerce")
    status = {
        "曲线": label,
        "编码": encoding,
        "小时数": len(df),
        "开始时间": parsed.min(),
        "结束时间": parsed.max(),
        "空值/非数字点": int(numeric.isna().sum()),
        "负值点": int((numeric < 0).sum()),
        "大于1点": int((numeric > 1).sum()) if label in {"光伏", "风电"} else 0,
    }
    return status


def _scenario_type(row: pd.Series) -> str:
    has_pv = row["pv_capacity"] > 0
    has_wind = row["wind_capacity"] > 0
    has_bess = row["bess_energy"] > 0
    if not has_bess:
        if has_pv and not has_wind:
            return "纯光伏方案"
        if has_wind and not has_pv:
            return "纯风电方案"
        if has_pv and has_wind:
            return "风光无储方案"
        return "无新能源无储能方案"
    if has_pv and not has_wind:
        return "光储方案"
    if has_wind and not has_pv:
        return "风储方案"
    if has_pv and has_wind:
        return "风光储方案"
    return "仅储能方案"


def _add_scenario_type(summary: pd.DataFrame) -> pd.DataFrame:
    if "方案类型" in summary.columns:
        return summary
    result = summary.copy()
    has_pv = result["pv_capacity"] > 0
    has_wind = result["wind_capacity"] > 0
    has_bess = result["bess_energy"] > 0
    result["方案类型"] = "仅储能方案"
    result.loc[~has_bess & ~has_pv & ~has_wind, "方案类型"] = "无新能源无储能方案"
    result.loc[~has_bess & has_pv & ~has_wind, "方案类型"] = "纯光伏方案"
    result.loc[~has_bess & has_wind & ~has_pv, "方案类型"] = "纯风电方案"
    result.loc[~has_bess & has_pv & has_wind, "方案类型"] = "风光无储方案"
    result.loc[has_bess & has_pv & ~has_wind, "方案类型"] = "光储方案"
    result.loc[has_bess & has_wind & ~has_pv, "方案类型"] = "风储方案"
    result.loc[has_bess & has_pv & has_wind, "方案类型"] = "风光储方案"
    return result


def _apply_filters(summary: pd.DataFrame, only_passed: bool, scheme_types: list[str], sort_label: str) -> pd.DataFrame:
    display = summary.copy()
    if only_passed:
        display = display[display["pass_policy"] == True]  # noqa: E712
    if scheme_types:
        display = display[display["方案类型"].isin(scheme_types)]
    sort_options = {
        "绿电占比从高到低": ("green_load_rate", False),
        "弃电率从低到高": ("curtail_rate", True),
        "自发自用率从高到低": ("self_use_rate", False),
        "上网比例从低到高": ("export_rate", True),
        "储能容量从小到大": ("bess_energy", True),
    }
    column, ascending = sort_options[sort_label]
    return display.sort_values(column, ascending=ascending).reset_index(drop=True)


def _format_summary_for_display(summary: pd.DataFrame) -> pd.DataFrame:
    display = summary.copy()
    energy_columns = [
        "total_load_energy",
        "grid_import_energy",
        "total_renewable_generation",
        "pv_station_use_energy",
        "wind_station_use_energy",
        "station_use_energy",
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
    ]
    percent_columns = ["grid_import_rate", "self_use_rate", "green_load_rate", "export_rate", "curtail_rate"]
    for column in energy_columns:
        if column in display.columns:
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.0f}")
    for column in percent_columns:
        if column in display.columns:
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.2%}")
    return localize_columns(display)


def _display_mapping_expander(st, columns: list[str], label: str = "字段对应关系") -> None:
    with st.expander(label, expanded=False):
        st.dataframe(mapping_frame(columns), use_container_width=True, hide_index=True)


def _get_download_payloads(st, batch_result, config_snapshot: dict):
    signature = (id(batch_result), len(batch_result.summary), len(batch_result.hourly_details))
    cached = st.session_state.get("download_payloads")
    if cached and cached.get("signature") == signature:
        return cached["payloads"]
    with st.spinner("正在准备下载文件..."):
        payloads = _build_download_payloads(batch_result, config_snapshot)
        st.session_state["download_payloads"] = {"signature": signature, "payloads": payloads}
    return payloads


def _parse_specific_years(raw: object) -> tuple[int, ...]:
    text = "" if raw is None else str(raw).strip()
    if not text:
        return ()
    years: list[int] = []
    for part in re.split(r"[,，;；|\s]+", text):
        if not part:
            continue
        years.append(int(float(part)))
    return tuple(year for year in years if year > 0)


def _build_other_revenue_items(raw: pd.DataFrame) -> tuple[OtherOperatingRevenueItem, ...]:
    items: list[OtherOperatingRevenueItem] = []
    if raw.empty:
        return ()
    for _, row in raw.iterrows():
        amount = pd.to_numeric(row.get("金额(万元/年)", 0.0), errors="coerce")
        if pd.isna(amount) or abs(float(amount)) < 1e-12:
            continue
        name = str(row.get("名称", "")).strip() or "其他经营收入"
        active_rule = str(row.get("发生规则", "every_year")).strip() or "every_year"
        vat_rate = pd.to_numeric(row.get("销项税率", 0.13), errors="coerce")
        if pd.isna(vat_rate):
            vat_rate = 0.13
        items.append(
            OtherOperatingRevenueItem(
                name=name,
                amount_with_vat=float(amount),
                vat_rate=float(vat_rate),
                active_rule=active_rule,
                specific_years=_parse_specific_years(row.get("指定年份")),
            )
        )
    return tuple(items)


def _build_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        for sheet_name, data in sheets.items():
            data.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return output.getvalue()


def _render_data_status(st, statuses: list[dict]) -> None:
    status_df = pd.DataFrame(statuses)
    if status_df.empty:
        return

    has_incomplete = len(statuses) < 3
    has_invalid_length = any(item["小时数"] not in {8760, 8784} for item in statuses)
    has_high_pu = any(item["大于1点"] for item in statuses)
    has_negative = any(item["负值点"] for item in statuses)

    if has_incomplete or has_invalid_length:
        st.error("数据状态：需要复核。存在缺失曲线或小时数不符合 8760/8784。")
    elif has_high_pu:
        st.warning("数据状态：可计算，但标幺曲线存在大于 1 的点，请确认容量基准。")
    elif has_negative:
        st.info("数据状态：可计算。发现负标幺值，将按站用电口径参与计算。")
    else:
        st.success("数据状态：三条曲线已识别，小时数和基础格式正常。")

    with st.expander("查看数据状态详情", expanded=False):
        st.dataframe(status_df, use_container_width=True, hide_index=True)
        for item in statuses:
            st.caption(
                f"{item['曲线']}：{item['小时数']} 小时，"
                f"{item['开始时间']} 至 {item['结束时间']}。"
            )
            if item["大于1点"]:
                st.warning(f"{item['曲线']}标幺值曲线存在数值大于 1 的情况，共 {item['大于1点']} 个点。")
            if item["负值点"]:
                st.info(f"{item['曲线']}曲线存在负值，共 {item['负值点']} 个点，将按站用电参与计算。")


def _render_economy_v1(st, summary: pd.DataFrame) -> None:
    st.markdown("---")
    st.header("经济性评价 V1")
    st.caption("经济性评价仅读取方案汇总结果，不重新计算逐小时调度。")

    with st.expander("经济性参数", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        operation_years = int(c1.number_input("运营期（年）", value=25, min_value=1, max_value=40, step=1))
        discount_rate = c2.number_input("折现率", value=0.06, min_value=-0.99, max_value=1.0, step=0.005, format="%.3f")
        income_tax_rate = c3.number_input("企业所得税率", value=0.25, min_value=0.0, max_value=1.0, step=0.01)
        urban_area = c4.selectbox("城建税地区", ["县城、镇 5%", "市区 7%", "其他 1%"])
        urban_tax_rate = {"市区 7%": 0.07, "县城、镇 5%": 0.05, "其他 1%": 0.01}[urban_area]

        c1, c2, c3, c4 = st.columns(4)
        wind_capex = c1.number_input("风电单位造价（元/kW，含税）", value=4500.0, min_value=0.0, step=100.0)
        pv_capex = c2.number_input(
            "光伏单位造价（元/kW，含税）",
            value=2500.0,
            min_value=0.0,
            step=100.0,
            help="需与光伏标幺曲线容量基准匹配；直流侧曲线填直流侧造价，交流侧曲线填交流侧造价。",
        )
        bess_capex = c3.number_input("储能单位造价（元/kWh，含税）", value=900.0, min_value=0.0, step=50.0)
        other_fixed_asset = c4.number_input("其他固定资产投资（万元，含税）", value=0.0, min_value=0.0, step=100.0)

        c1, c2, c3, c4 = st.columns(4)
        construction_vat_rate = c1.number_input("建设投资进项税率", value=0.10, min_value=0.0, max_value=1.0, step=0.01)
        wind_om = c2.number_input("风电运维成本（元/kW/年）", value=50.0, min_value=0.0, step=1.0)
        pv_om = c3.number_input("光伏运维成本（元/kW/年）", value=25.0, min_value=0.0, step=1.0)
        bess_om = c4.number_input("储能运维成本（元/kW/年）", value=18.0, min_value=0.0, step=1.0)

        c1, c2, c3, c4 = st.columns(4)
        grid_export_price = c1.number_input("上网电价（元/kWh，含税）", value=0.25, min_value=0.0, step=0.01)
        self_use_price = c2.number_input(
            "自发自用电价（元/kWh，含税）",
            value=0.40,
            min_value=0.0,
            step=0.01,
            help="输入不含过网费的自发自用电价。",
        )
        output_vat_rate = c3.number_input("销项税率", value=0.13, min_value=0.0, max_value=1.0, step=0.01)
        other_operating_cost = c4.number_input("其他运行成本（万元/年）", value=0.0, min_value=0.0, step=10.0)

        c1, c2 = st.columns(2)
        replacement_ratio = c1.number_input("储能更换投资比例", value=0.50, min_value=0.0, max_value=1.0, step=0.05)
        replacement_vat_rate = c2.number_input("储能更换进项税率", value=0.13, min_value=0.0, max_value=1.0, step=0.01)

        st.caption("其他经营收入可输入负值；负值在 V1 中不产生进项税，按收入抵减或额外经营性支出处理。")
        default_other = pd.DataFrame(
            [
                {
                    "名称": "",
                    "金额(万元/年)": 0.0,
                    "销项税率": 0.13,
                    "发生规则": "every_year",
                    "指定年份": "",
                }
            ]
        )
        other_revenue_df = st.data_editor(
            st.session_state.get("economy_other_revenue_df", default_other),
            num_rows="dynamic",
            use_container_width=True,
            key="economy_other_revenue_editor",
        )
        st.session_state["economy_other_revenue_df"] = other_revenue_df

    try:
        other_revenues = _build_other_revenue_items(other_revenue_df)
    except ValueError as exc:
        st.error(f"其他经营收入年份格式有误：{exc}")
        return

    params = EconomicParams(
        operation_years=operation_years,
        wind_capex_per_kw_with_vat=wind_capex,
        pv_capex_per_kw_with_vat=pv_capex,
        bess_capex_per_kwh_with_vat=bess_capex,
        other_fixed_asset_investment_with_vat=other_fixed_asset,
        construction_input_vat_rate=construction_vat_rate,
        wind_om_cost_per_kw_year=wind_om,
        pv_om_cost_per_kw_year=pv_om,
        bess_om_cost_per_kw_year=bess_om,
        other_operating_cost_with_vat=other_operating_cost,
        grid_export_price_with_vat=grid_export_price,
        self_use_price_with_vat=self_use_price,
        output_vat_rate=output_vat_rate,
        other_operating_revenues=other_revenues,
        bess_replacement_cost_ratio=replacement_ratio,
        bess_replacement_input_vat_rate=replacement_vat_rate,
        urban_maintenance_tax_rate=urban_tax_rate,
        income_tax_rate=income_tax_rate,
        discount_rate=discount_rate,
    )

    if st.button("计算经济性 V1", key="run_economy_v1"):
        with st.spinner("正在计算经济性年度现金流..."):
            economic_summary, annual_cashflows = evaluate_batch_economy(summary, params)
        st.session_state["economy_v1_result"] = {
            "summary": economic_summary,
            "annual_cashflows": annual_cashflows,
        }

    economy_result = st.session_state.get("economy_v1_result")
    if not economy_result:
        return

    economic_summary = economy_result["summary"]
    annual_cashflows = economy_result["annual_cashflows"]
    if economic_summary.empty:
        st.info("当前没有可展示的经济性结果。")
        return

    display_columns = [
        "scenario_id",
        "fnpv",
        "firr",
        "firr_status",
        "static_payback_year",
        "dynamic_payback_year",
        "construction_cash_outflow",
        "annual_operating_revenue_with_vat",
        "annual_operating_cost_with_vat",
        "bess_replacement_operation_year",
    ]
    st.subheader("经济性汇总")
    st.dataframe(localize_columns(economic_summary[display_columns]), use_container_width=True, hide_index=True)
    _display_mapping_expander(st, display_columns, "经济性汇总字段对应关系")

    selected_id = st.selectbox("选择方案下载经济性年度明细", economic_summary["scenario_id"].astype(str).tolist())
    annual = annual_cashflows[selected_id]

    st.download_button(
        "下载经济性结果 Excel",
        data=_build_excel_bytes(
            {
                "经济性汇总": localize_columns(economic_summary),
                f"年度现金流_{selected_id}": localize_columns(annual),
            }
        ),
        file_name="economic_evaluation_v1.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_economy_v1",
    )


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="绿电直连风光储方案策划平台", layout="wide")
    st.title("绿电直连风光储方案策划与测算平台")

    with st.sidebar:
        with st.expander("数据上传", expanded=True):
            use_sample_data = st.checkbox(
                "使用内置示例数据（Demo）",
                value=False,
                help="使用 samples 目录中的负荷、光伏、风电示例曲线，适合快速体验测算和图表分析。",
            )
            sample_files: dict[str, object] = {}
            if use_sample_data:
                sample_files, sample_messages = _load_sample_curve_files()
                for message in sample_messages:
                    st.warning(message)
                for curve_name, sample_file in sample_files.items():
                    st.caption(f"{curve_name}示例：`{sample_file.name}`")

            batch_files = st.file_uploader(
                "批量上传曲线 CSV",
                type=["csv"],
                accept_multiple_files=True,
                help="可一次选择负荷、光伏、风电三个文件。文件名包含负荷/load、光伏/pv/solar、风电/wind 时会自动识别。",
            )
            assigned_files, assign_messages = _auto_assign_curve_files(batch_files)
            for message in assign_messages:
                st.warning(message)
            for curve_name, uploaded_file in assigned_files.items():
                st.caption(f"{curve_name}文件：已自动识别 `{uploaded_file.name}`")

            st.caption("如果批量识别不准确，可在下面单独上传覆盖。")
            load_file_manual = st.file_uploader("负荷 CSV", type=["csv"], key="load_csv_manual")
            pv_file_manual = st.file_uploader("光伏 CSV", type=["csv"], key="pv_csv_manual")
            wind_file_manual = st.file_uploader("风电 CSV", type=["csv"], key="wind_csv_manual")
            load_file = load_file_manual or assigned_files.get("负荷") or sample_files.get("负荷")
            pv_file = pv_file_manual or assigned_files.get("光伏") or sample_files.get("光伏")
            wind_file = wind_file_manual or assigned_files.get("风电") or sample_files.get("风电")

            try:
                load_df, load_encoding = _load_preview(load_file)
                pv_df, pv_encoding = _load_preview(pv_file)
                wind_df, wind_encoding = _load_preview(wind_file)
                if load_encoding:
                    st.caption(f"负荷编码: {load_encoding}")
                if pv_encoding:
                    st.caption(f"光伏编码: {pv_encoding}")
                if wind_encoding:
                    st.caption(f"风电编码: {wind_encoding}")
            except DataValidationError as exc:
                st.error(str(exc))
                load_df = pv_df = wind_df = None
                load_encoding = pv_encoding = wind_encoding = None

            load_time_guess = _guess_time_column(load_df)
            pv_time_guess = _guess_time_column(pv_df)
            wind_time_guess = _guess_time_column(wind_df)
            load_value_guess = _guess_value_column(load_df, load_time_guess, "负荷")
            pv_value_guess = _guess_value_column(pv_df, pv_time_guess, "光伏")
            wind_value_guess = _guess_value_column(wind_df, wind_time_guess, "风电")

            load_time_col = _column_selector(st, "负荷时间列", load_df, load_time_guess)
            load_value_col = _column_selector(st, "负荷数值列", load_df, load_value_guess)
            pv_time_col = _column_selector(st, "光伏时间列", pv_df, pv_time_guess)
            pv_value_col = _column_selector(st, "光伏数值列", pv_df, pv_value_guess)
            wind_time_col = _column_selector(st, "风电时间列", wind_df, wind_time_guess)
            wind_value_col = _column_selector(st, "风电数值列", wind_df, wind_value_guess)

        with st.expander("容量搜索范围", expanded=True):
            pv_range = _range_inputs(st, "光伏容量", (0, 30, 5))
            wind_range = _range_inputs(st, "风电容量", (0, 30, 5))
            bess_power_range = _range_inputs(st, "储能功率", (0, 10, 2))
            include_no_bess = st.checkbox("包含无储能方案", value=True)
            duration_text = st.text_input("储能时长选项（小时）", value="2,4")

        with st.expander("储能参数", expanded=False):
            soc_initial = st.number_input("初始 SOC", value=0.5, min_value=0.0, max_value=1.0, step=0.05)
            soc_min = st.number_input("最小 SOC", value=0.1, min_value=0.0, max_value=1.0, step=0.05)
            soc_max = st.number_input("最大 SOC", value=0.9, min_value=0.0, max_value=1.0, step=0.05)
            eta_charge = st.number_input("充电效率", value=0.95, min_value=0.000001, max_value=1.0, step=0.01)
            eta_discharge = st.number_input("放电效率", value=0.95, min_value=0.000001, max_value=1.0, step=0.01)
            cycle_life = st.number_input("循环寿命", value=6000.0, min_value=0.0, step=100.0)

        with st.expander("上网与政策约束", expanded=False):
            allow_export = st.checkbox("允许上网", value=True)
            enforce_export_cap = st.checkbox("启用年度上网比例硬约束（超过额度后弃电）", value=True)
            self_use_rate_min = st.number_input("自发自用率下限", value=0.60, min_value=0.0, max_value=1.0, step=0.01)
            green_load_rate_min = st.number_input("绿电占用电比例下限", value=0.30, min_value=0.0, max_value=1.0, step=0.01)
            export_rate_max = st.number_input("上网比例上限", value=0.20, min_value=0.0, max_value=1.0, step=0.01)
            limit_exchange_power = st.checkbox("设置与电网交换功率限制", value=False)
            grid_exchange_power_limit = None
            if limit_exchange_power:
                grid_exchange_power_limit = st.number_input(
                    "与电网交换功率限制（万千瓦）",
                    value=10.0,
                    min_value=0.0,
                    step=1.0,
                )

        with st.expander("高级参数", expanded=False):
            warn_threshold = st.number_input("方案数提醒阈值", value=5000, min_value=1, step=100)

    try:
        durations = [float(item.strip()) for item in duration_text.split(",") if item.strip()]
        if include_no_bess and 0.0 not in durations:
            durations = [0.0, *durations]
        scenario_grid = {
            "pv_capacity": pv_range,
            "wind_capacity": wind_range,
            "bess_power": bess_power_range,
            "bess_duration_hours": durations,
        }
        scenario_count = estimate_scenario_count(scenario_grid)
        st.metric("方案数量预估", scenario_count)
        if scenario_count > warn_threshold:
            st.warning(f"本次配置将生成 {scenario_count} 个方案，可能计算较慢，建议增大步长或缩小范围。")
    except Exception as exc:  # noqa: BLE001 - UI should show friendly text
        st.error(f"方案范围设置有误：{exc}")
        scenario_grid = None

    ready = all(
        [
            load_file,
            pv_file,
            wind_file,
            load_time_col,
            load_value_col,
            pv_time_col,
            pv_value_col,
            wind_time_col,
            wind_value_col,
            scenario_grid,
        ]
    )

    if not ready:
        st.info("请上传三条 CSV 曲线并确认列名后开始测算。")

    if st.button("一键生成 Demo 结果", help="使用 samples 示例曲线和 20 个小规模方案快速生成图表演示。"):
        try:
            demo_files, demo_messages = _load_sample_curve_files()
            missing_demo = {"负荷", "光伏", "风电"} - set(demo_files)
            if missing_demo:
                raise DataValidationError(f"内置示例数据不完整，缺少：{', '.join(sorted(missing_demo))}。")
            for message in demo_messages:
                st.warning(message)

            demo_load_df, _ = _load_preview(demo_files["负荷"])
            demo_pv_df, _ = _load_preview(demo_files["光伏"])
            demo_wind_df, _ = _load_preview(demo_files["风电"])
            demo_load_time_col = _guess_time_column(demo_load_df)
            demo_pv_time_col = _guess_time_column(demo_pv_df)
            demo_wind_time_col = _guess_time_column(demo_wind_df)
            demo_load_value_col = _guess_value_column(demo_load_df, demo_load_time_col, "负荷")
            demo_pv_value_col = _guess_value_column(demo_pv_df, demo_pv_time_col, "光伏")
            demo_wind_value_col = _guess_value_column(demo_wind_df, demo_wind_time_col, "风电")
            if not all(
                [
                    demo_load_time_col,
                    demo_pv_time_col,
                    demo_wind_time_col,
                    demo_load_value_col,
                    demo_pv_value_col,
                    demo_wind_value_col,
                ]
            ):
                raise DataValidationError("未能自动识别示例数据列名，请检查 samples 目录中的 CSV。")

            demo_curves = read_curve_set(
                BytesIO(demo_files["负荷"].getvalue()),
                BytesIO(demo_files["光伏"].getvalue()),
                BytesIO(demo_files["风电"].getvalue()),
                load_time_col=demo_load_time_col,
                load_value_col=demo_load_value_col,
                pv_time_col=demo_pv_time_col,
                pv_value_col=demo_pv_value_col,
                wind_time_col=demo_wind_time_col,
                wind_value_col=demo_wind_value_col,
                cleaning=DataCleaningParams(),
            )
            demo_grid = {
                "pv_capacity": {"start": 10, "end": 20, "step": 10},
                "wind_capacity": {"start": 5, "end": 15, "step": 10},
                "bess_power": {"start": 0, "end": 4, "step": 2},
                "bess_duration_hours": [0, 2, 4],
            }
            with st.spinner("正在生成 Demo 测算结果..."):
                batch_result = run_batch(
                    demo_curves.data,
                    demo_grid,
                    bess_params=BessParams(),
                    policy_params=PolicyParams(export_control_mode="annual_cap_runtime"),
                    performance_params=PerformanceParams(warn_if_scenarios_exceed=int(warn_threshold)),
                )
            st.session_state["batch_result"] = batch_result
            st.session_state["config_snapshot"] = {
                "scenario_grid": demo_grid,
                "bess": BessParams().__dict__,
                "policy": PolicyParams(export_control_mode="annual_cap_runtime").__dict__,
                "warnings": demo_curves.warnings,
                "demo": True,
            }
            st.session_state.pop("download_payloads", None)
            st.success("Demo 结果已生成，可直接查看下方图表分析。")
        except DataValidationError as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001 - UI should show friendly text
            st.error(f"Demo 生成失败：{exc}")

    statuses = [
        _curve_status("负荷", load_df, load_encoding, load_time_col, load_value_col),
        _curve_status("光伏", pv_df, pv_encoding, pv_time_col, pv_value_col),
        _curve_status("风电", wind_df, wind_encoding, wind_time_col, wind_value_col),
    ]
    statuses = [item for item in statuses if item is not None]
    if statuses:
        _render_data_status(st, statuses)

    if st.button("开始测算", type="primary", disabled=not ready):
        try:
            curves = read_curve_set(
                BytesIO(load_file.getvalue()),
                BytesIO(pv_file.getvalue()),
                BytesIO(wind_file.getvalue()),
                load_time_col=load_time_col,
                load_value_col=load_value_col,
                pv_time_col=pv_time_col,
                pv_value_col=pv_value_col,
                wind_time_col=wind_time_col,
                wind_value_col=wind_value_col,
                cleaning=DataCleaningParams(),
            )
            bess_params = BessParams(
                soc_initial=soc_initial,
                soc_min=soc_min,
                soc_max=soc_max,
                eta_charge=eta_charge,
                eta_discharge=eta_discharge,
                cycle_life=cycle_life,
            )
            policy_params = PolicyParams(
                self_use_rate_min=self_use_rate_min,
                green_load_rate_min=green_load_rate_min,
                export_rate_max=export_rate_max,
                allow_export=allow_export,
                export_power_max=None,
                grid_exchange_power_limit=grid_exchange_power_limit,
                export_control_mode="annual_cap_runtime" if enforce_export_cap else "post_check",
            )
            progress = st.progress(0)
            progress_text = st.empty()

            def update_progress(done, total, scenario):
                progress.progress(done / total if total else 1.0)
                progress_text.caption(f"正在计算 {done}/{total}：{scenario.scenario_id}")

            batch_result = run_batch(
                curves.data,
                scenario_grid,
                bess_params=bess_params,
                policy_params=policy_params,
                performance_params=PerformanceParams(warn_if_scenarios_exceed=int(warn_threshold)),
                progress_callback=update_progress,
            )
            progress_text.caption(f"计算完成：{batch_result.scenario_count}/{batch_result.scenario_count}")

            st.session_state["batch_result"] = batch_result
            st.session_state["config_snapshot"] = {
                "scenario_grid": scenario_grid,
                "bess": bess_params.__dict__,
                "policy": policy_params.__dict__,
                "warnings": curves.warnings,
            }
            st.session_state.pop("download_payloads", None)
            st.success("测算完成。")
        except DataValidationError as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001 - UI should show friendly text
            st.error(f"测算失败：{exc}")

    batch_result = st.session_state.get("batch_result")
    if not batch_result:
        return

    for warning in batch_result.warnings[:10]:
        st.warning(warning)
    if not batch_result.errors.empty:
        st.error(f"{len(batch_result.errors)} 个方案计算失败，已在错误表中记录。")
        st.dataframe(batch_result.errors, use_container_width=True)

    summary = batch_result.summary
    if summary.empty:
        st.warning("没有成功生成方案结果。")
        return

    summary = _add_scenario_type(summary)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("总方案数", batch_result.scenario_count)
    c2.metric("达标方案数", int(summary["pass_policy"].sum()))
    c3.metric("最高绿电占比", f"{summary['green_load_rate'].max():.2%}")
    c4.metric("最低弃电率", f"{summary['curtail_rate'].min():.2%}")
    c5.metric("最低下网比例", f"{summary['grid_import_rate'].min():.2%}")

    with st.expander("高级：结果表、筛选与下载", expanded=False):
        if st.checkbox("准备下载文件", value=False, help="生成 Excel/ZIP 可能需要等待，默认不占用主界面。"):
            payloads = _get_download_payloads(st, batch_result, st.session_state.get("config_snapshot", {}))
            d1, d2 = st.columns(2)
            d1.download_button(
                "下载方案汇总 Excel",
                data=payloads["excel_bytes"],
                file_name=payloads["excel_name"],
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_summary_excel",
            )
            d2.download_button(
                "下载全部逐小时明细 ZIP",
                data=payloads["zip_bytes"],
                file_name=payloads["zip_name"],
                mime="application/zip",
                key="download_hourly_zip",
            )

        only_passed = st.checkbox("只看达标方案", value=False)
        scheme_types = st.multiselect(
            "方案类型筛选（与达标筛选为 AND 关系）",
            sorted(summary["方案类型"].dropna().unique()),
            default=[],
        )
        sort_label = st.selectbox(
            "排序方式",
            ["绿电占比从高到低", "弃电率从低到高", "自发自用率从高到低", "上网比例从低到高", "储能容量从小到大"],
        )
        display = _apply_filters(summary, only_passed, scheme_types, sort_label)
        max_display_rows = st.number_input("结果表最多显示行数", min_value=50, max_value=5000, value=200, step=50)
        st.caption(f"当前筛选结果 {len(display)} 条，表格显示前 {min(len(display), int(max_display_rows))} 条。")
        st.dataframe(_format_summary_for_display(display.head(int(max_display_rows))), use_container_width=True)
        _display_mapping_expander(st, list(display.columns), "方案汇总字段对应关系")

        scenario_ids = list(batch_result.hourly_details.keys())
        selected = st.selectbox("选择方案下载逐小时 CSV", scenario_ids)
        if selected:
            csv_bytes = localize_columns(batch_result.hourly_details[selected]).to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "下载当前方案逐小时 CSV",
                data=csv_bytes,
                file_name=f"hourly_detail_{selected}.csv",
                mime="text/csv",
            )
            _display_mapping_expander(
                st,
                list(batch_result.hourly_details[selected].columns),
                "逐小时明细字段对应关系",
            )

    _render_economy_v1(st, summary)

    render_chart_analysis(
        st,
        batch_result,
        summary,
        economy_result=st.session_state.get("economy_v1_result"),
    )


if __name__ == "__main__":
    main()
