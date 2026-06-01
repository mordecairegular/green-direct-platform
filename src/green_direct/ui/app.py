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
from green_direct.economy import (
    AvoidedGridPurchaseParams,
    EconomicParams,
    OtherOperatingRevenueItem,
    calc_avoided_grid_purchase_cash_price,
)
from green_direct.export.csv_exporter import export_hourly_details_zip
from green_direct.export.excel_exporter import export_summary_excel
from green_direct.io.read_curves import read_csv_auto_encoding, read_curve_set
from green_direct.io.validators import DataValidationError
from green_direct.models.params import BessParams, DataCleaningParams, PerformanceParams, PolicyParams
from green_direct.recommendation import (
    ENGINEERING_VIEW_LABELS,
    SINGLE_ENTITY_VIEW_LABELS,
)
from green_direct.services import RecommendationInputSnapshot, build_recommendation_study, run_economic_study
from green_direct.ui.field_labels import FIELD_LABELS, format_display_frame, localize_columns, mapping_frame
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
WORKFLOW_PAGES = ["欢迎页", "技术仿真", "经济性评价", "推荐方案与详细分析"]


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


def _trim_number(value: float) -> str:
    return f"{value:g}"


def _float_text_input(
    st,
    label: str,
    value: float,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
    help: str | None = None,
) -> float:
    raw = st.text_input(label, value=_trim_number(value), help=help)
    try:
        parsed = float(str(raw).replace(",", "").strip())
    except ValueError:
        st.error(f"{label} 必须填写数字。")
        st.stop()
    if min_value is not None and parsed < min_value:
        st.error(f"{label} 不能小于 {_trim_number(min_value)}。")
        st.stop()
    if max_value is not None and parsed > max_value:
        st.error(f"{label} 不能大于 {_trim_number(max_value)}。")
        st.stop()
    return parsed


def _percent_text_input(
    st,
    label: str,
    value_percent: float,
    *,
    min_value: float = 0.0,
    max_value: float = 100.0,
    help: str | None = None,
) -> float:
    return _float_text_input(
        st,
        label,
        value_percent,
        min_value=min_value,
        max_value=max_value,
        help=help,
    ) / 100


def _optional_percent_text_input(
    st,
    label: str,
    value_percent: float,
    *,
    min_value: float = 0.0,
    max_value: float = 100.0,
    help: str | None = None,
) -> float | None:
    raw = st.text_input(label, value=_trim_number(value_percent), help=help)
    if str(raw).strip() == "":
        return None
    try:
        parsed = float(str(raw).replace(",", "").strip())
    except ValueError:
        st.error(f"{label} 必须填写数字，或留空表示不对相关席位排序。")
        st.stop()
    if parsed < min_value:
        st.error(f"{label} 不能小于 {_trim_number(min_value)}。")
        st.stop()
    if parsed > max_value:
        st.error(f"{label} 不能大于 {_trim_number(max_value)}。")
        st.stop()
    return parsed / 100


def _build_download_payloads(batch_result, config_snapshot: dict):
    with TemporaryDirectory() as tmp:
        excel_path = export_summary_excel(
            batch_result.summary,
            tmp,
            config_snapshot=config_snapshot,
            warnings=batch_result.warnings,
            filename_prefix="scenario_summary",
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
    return localize_columns(format_display_frame(summary))


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


SINGLE_ENTITY_ANNUAL_COLUMNS = [
    "scenario_id",
    "year",
    "operation_year",
    "period_type",
    "self_use_energy",
    "grid_export_energy",
    "net_avoided_grid_cost_price",
    "avoided_grid_purchase_cash_price",
    "self_use_saving",
    "avoided_grid_purchase_cash_saving",
    "environmental_value",
    "grid_export_revenue_without_vat",
    "other_external_revenue_without_vat",
    "operating_cost_basis",
    "bess_replacement_basis",
    "bess_replacement_cash_outflow_with_vat",
    "initial_investment_basis",
    "construction_cash_outflow_with_vat",
    "pre_tax_net_cash_flow",
    "cumulative_net_cash_flow",
    "discount_factor",
    "discounted_net_cash_flow",
    "cumulative_discounted_net_cash_flow",
]


def _label_for_column(column: str) -> str:
    return FIELD_LABELS.get(column, column)


def _value_from_frame(frame: pd.DataFrame, scenario_id: str, column: str):
    if frame.empty or column not in frame.columns or "scenario_id" not in frame.columns:
        return ""
    matched = frame[frame["scenario_id"].astype(str) == str(scenario_id)]
    if matched.empty:
        return ""
    value = matched.iloc[0][column]
    if pd.isna(value):
        return ""
    return value


def _build_scenario_info_frame(
    scenario_id: str,
    technical_summary: pd.DataFrame,
    economic_summary: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    def add(category: str, column: str, note: str = "") -> None:
        rows.append(
            {
                "类别": category,
                "项目": _label_for_column(column),
                "英文字段": column,
                "值": _value_from_frame(technical_summary, scenario_id, column)
                if column in technical_summary.columns
                else _value_from_frame(economic_summary, scenario_id, column),
                "说明": note,
            }
        )

    rows.append({"类别": "方案", "项目": "方案编号", "英文字段": "scenario_id", "值": scenario_id, "说明": ""})
    add("方案", "方案类型")
    add("容量", "pv_capacity")
    add("容量", "wind_capacity")
    add("容量", "bess_power")
    add("容量", "bess_energy")
    add("政策/技术指标", "pass_policy")
    add("政策/技术指标", "fail_reasons")
    add("政策/技术指标", "green_load_rate")
    add("政策/技术指标", "self_use_rate")
    add("政策/技术指标", "export_rate")
    add("政策/技术指标", "curtail_rate")
    add("电量", "self_use_energy")
    add("电量", "grid_export_energy")
    add("电量", "curtail_energy")
    add("储能更换", "annual_equivalent_cycles")
    add("储能更换", "replacement_year", "按循环寿命估算的更换年；经济性还会与电池日历寿命取早。")
    add("同一主体经济性", "single_entity_firr_pre_tax")
    add("同一主体经济性", "single_entity_firr_status")
    add("同一主体经济性", "single_entity_fnpv_pre_tax")
    add("同一主体经济性", "initial_investment_basis")
    add("同一主体经济性", "construction_cash_outflow_with_vat")
    add("同一主体经济性", "net_avoided_grid_cost_price")
    add("同一主体经济性", "annual_self_use_saving")
    add("同一主体经济性", "bess_replacement_operation_years")
    return pd.DataFrame(rows)


def _single_entity_field_descriptions(columns: list[str]) -> pd.DataFrame:
    index_by_column = {column: idx for idx, column in enumerate(columns, start=1)}

    def n(column: str) -> str:
        return str(index_by_column[column])

    descriptions = {
        "scenario_id": "方案编号，用于与方案汇总表、逐小时明细表关联。",
        "year": "项目年份。0 为建设期，1 至 N 为运营期。",
        "operation_year": "运营年。建设期为 0。",
        "period_type": "期间类型：construction 为建设期，operation 为运营期。",
        "self_use_energy": "来自技术仿真的自发自用电量，运营期各年按代表年结果重复。",
        "grid_export_energy": "来自技术仿真的上网电量，运营期各年按代表年结果重复。",
        "net_avoided_grid_cost_price": "外部购电净成本单价。表示同一主体口径下每 1 kWh 自发自用绿电替代外部购电带来的税前净节费；简化模式为用户直接输入。组价模式公式：外部购电净成本单价=原外部购网电电量类成本单价-绿电直连自发自用仍需缴纳费用单价。",
        "avoided_grid_purchase_cash_price": "少付电网电费现金单价。同一主体简化模式下与净成本单价相同；组价模式下为含税/附加现金口径，仅辅助展示，不作为负荷侧可成交收益的固定价输入。",
        "self_use_saving": f"{n('self_use_saving')}={n('self_use_energy')}×{n('net_avoided_grid_cost_price')}。进入税前 FIRR 的自发自用购电节费。",
        "avoided_grid_purchase_cash_saving": f"{n('avoided_grid_purchase_cash_saving')}={n('self_use_energy')}×{n('avoided_grid_purchase_cash_price')}。少付电网电量电费现金额，仅辅助展示，不进入税前 FIRR。",
        "environmental_value": f"{n('environmental_value')}={n('self_use_energy')}×环境价值单价。默认环境价值单价为 0。",
        "grid_export_revenue_without_vat": f"{n('grid_export_revenue_without_vat')}={n('grid_export_energy')}×上网含税电价÷(1+销项税率)。",
        "other_external_revenue_without_vat": "其他外部收益，不含税口径。来自其他经营收入设置。",
        "operating_cost_basis": "运行成本评价基础。当前 V1 运行成本不拆进项税。",
        "bess_replacement_basis": f"储能更换评价基础。可抵扣时，约等于 {n('bess_replacement_cash_outflow_with_vat')}÷(1+储能更换进项税率)；用于税前 FIRR。",
        "bess_replacement_cash_outflow_with_vat": "储能更换现金流出，含税展示口径。约等于储能容量×储能单位造价×储能更换投资比例，仅在触发更换年份发生。",
        "initial_investment_basis": "Year 0 初始投资评价基础。可抵扣时为含税建设投资扣除进项税后的金额，进入税前 FIRR。",
        "construction_cash_outflow_with_vat": "Year 0 含税建设投资现金流出，辅助展示，不直接作为税前 FIRR 的评价基础。",
        "pre_tax_net_cash_flow": f"Year 0：{n('pre_tax_net_cash_flow')}=-{n('initial_investment_basis')}；运营期：{n('pre_tax_net_cash_flow')}={n('self_use_saving')}+{n('environmental_value')}+{n('grid_export_revenue_without_vat')}+{n('other_external_revenue_without_vat')}-{n('operating_cost_basis')}-{n('bess_replacement_basis')}。",
        "cumulative_net_cash_flow": f"截至当年的 {n('pre_tax_net_cash_flow')} 累计值。",
        "discount_factor": "折现系数 = 1÷(1+折现率)^年份。",
        "discounted_net_cash_flow": f"{n('discounted_net_cash_flow')}={n('pre_tax_net_cash_flow')}×{n('discount_factor')}。",
        "cumulative_discounted_net_cash_flow": f"截至当年的 {n('discounted_net_cash_flow')} 累计值。",
    }
    return pd.DataFrame(
        [
            {
                "序号": index_by_column[column],
                "英文字段": column,
                "中文表头": _label_for_column(column),
                "计算/含义说明": descriptions.get(column, ""),
            }
            for column in columns
        ]
    )


def _build_single_entity_annual_workbook_bytes(
    *,
    scenario_id: str,
    annual: pd.DataFrame,
    technical_summary: pd.DataFrame,
    economic_summary: pd.DataFrame,
) -> bytes:
    columns = [column for column in SINGLE_ENTITY_ANNUAL_COLUMNS if column in annual.columns]
    numbered_names = {column: f"{idx}. {_label_for_column(column)}" for idx, column in enumerate(columns, start=1)}
    annual_numbered = annual[columns].rename(columns=numbered_names)
    scenario_info = _build_scenario_info_frame(scenario_id, technical_summary, economic_summary)
    field_descriptions = _single_entity_field_descriptions(columns)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        scenario_info.to_excel(writer, sheet_name="方案说明", index=False)
        annual_numbered.to_excel(writer, sheet_name="年度现金流", index=False)
        field_descriptions.to_excel(writer, sheet_name="字段说明", index=False)

        workbook = writer.book
        wrap = workbook.add_format({"text_wrap": True, "valign": "top"})
        for sheet_name in ["方案说明", "年度现金流", "字段说明"]:
            worksheet = writer.sheets[sheet_name]
            worksheet.freeze_panes(1, 0)
            worksheet.set_column(0, 0, 12)
            worksheet.set_column(1, 1, 24)
            worksheet.set_column(2, 2, 28)
            worksheet.set_column(3, 3, 18)
            worksheet.set_column(4, 4, 48, wrap)
        writer.sheets["年度现金流"].freeze_panes(1, 4)
        writer.sheets["字段说明"].set_column(3, 3, 90, wrap)
    return output.getvalue()


def _merge_result_context(result_summary: pd.DataFrame, technical_summary: pd.DataFrame) -> pd.DataFrame:
    context_columns = [
        column
        for column in ["scenario_id", "方案类型", "pv_capacity", "wind_capacity", "bess_energy"]
        if column in technical_summary.columns
    ]
    display_summary = result_summary.copy()
    if len(context_columns) > 1:
        display_summary = display_summary.merge(
            technical_summary[context_columns].drop_duplicates("scenario_id"),
            on="scenario_id",
            how="left",
        )
    return display_summary


def _render_recommendation_v1(
    st,
    summary: pd.DataFrame,
    power_economy_summary: pd.DataFrame,
    single_entity_summary: pd.DataFrame | None,
    economic_params: EconomicParams,
    load_side_avoided_charge_price: float,
    green_power_settlement_price_with_vat: float,
    environmental_value_per_kwh: float,
    min_power_side_acceptable_firr: float | None,
) -> None:
    st.markdown("---")
    st.header("推荐方案 V1（试用）")
    st.caption(
        "默认构造同一主体、电源侧 FIRR、负荷侧可成交收益、工程代表四个席位；"
        "推荐只读取技术汇总和经济性结果，不改变逐小时调度。重复命中多个席位的方案会合并标签。"
    )

    single_entity_label_to_key = {label: key for key, label in SINGLE_ENTITY_VIEW_LABELS.items()}
    single_entity_view_label = st.selectbox(
        "同一主体推荐视角",
        list(single_entity_label_to_key.keys()),
        index=0,
        help="默认按 FIRR 最高；也可切换为动态回收期最短，用于查看更偏快速回收的方案。",
    )
    single_entity_view = single_entity_label_to_key[single_entity_view_label]

    view_label_to_key = {label: key for key, label in ENGINEERING_VIEW_LABELS.items()}
    engineering_view_label = st.selectbox(
        "工程代表方案视角",
        list(view_label_to_key.keys()),
        index=0,
        help="第四个推荐席位的工程视角。默认政策达标最小投资，可切换低弃电、高绿电占比、高自发自用。",
    )
    engineering_view = view_label_to_key[engineering_view_label]

    recommendation_inputs = RecommendationInputSnapshot(
        economic_params=economic_params,
        load_side_avoided_charge_price=load_side_avoided_charge_price,
        green_power_settlement_price_with_vat=green_power_settlement_price_with_vat,
        environmental_value_per_kwh=environmental_value_per_kwh,
        min_power_side_acceptable_firr=min_power_side_acceptable_firr,
    )
    recommendation_result = build_recommendation_study(
        summary,
        power_economy_summary,
        recommendation_inputs,
        single_entity_summary=single_entity_summary,
        single_entity_view=single_entity_view,
        engineering_view=engineering_view,
    )
    portfolio = recommendation_result.portfolio
    load_side_detail = recommendation_result.load_side_detail

    if portfolio.empty:
        st.info("当前没有可展示的推荐结果。")
        return
    if min_power_side_acceptable_firr is None:
        st.warning("电源侧最低可接受 FIRR 已留空，负荷侧可成交收益席位不参与默认排序。")

    display_columns = [
        "recommendation_rank",
        "recommendation_labels",
        "recommendation_status",
        "scenario_id",
        "方案类型",
        "pv_capacity",
        "wind_capacity",
        "bess_energy",
        "load_side_annual_benefit",
        "load_side_saving_price",
        "single_entity_firr_pre_tax",
        "single_entity_static_payback_year",
        "firr",
        "power_side_firr_threshold",
        "construction_cash_outflow",
        "green_load_rate",
        "self_use_rate",
        "curtail_rate",
        "recommendation_reason",
        "risk_note",
    ]
    display_columns = [column for column in display_columns if column in portfolio.columns]
    st.dataframe(
        localize_columns(format_display_frame(portfolio[display_columns])),
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("高级：推荐明细和下载", expanded=False):
        st.download_button(
            "下载推荐组合 Excel",
            data=_build_excel_bytes(
                {
                    "推荐组合": localize_columns(portfolio),
                    "电源侧经济性汇总": localize_columns(power_economy_summary),
                    "同一主体经济性汇总": localize_columns(
                        single_entity_summary if single_entity_summary is not None else pd.DataFrame()
                    ),
                    "负荷侧可成交收益明细": localize_columns(load_side_detail),
                }
            ),
            file_name="recommendation_portfolio_v1.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_recommendation_portfolio_v1",
        )
        st.caption("负荷侧明细用于复核可成交性筛选、节约电费单价和电源侧 FIRR 门槛。")
        detail_columns = [
            "scenario_id",
            "pass_policy",
            "load_side_tradable",
            "load_side_tradable_status",
            "self_use_energy",
            "load_side_avoided_charge_price",
            "green_power_settlement_price_with_vat",
            "load_side_saving_price",
            "load_side_environmental_value",
            "load_side_annual_benefit",
            "firr",
            "firr_status",
            "power_side_firr_threshold",
            "green_load_rate",
            "curtail_rate",
            "construction_cash_outflow",
        ]
        detail_columns = [column for column in detail_columns if column in load_side_detail.columns]
        st.dataframe(
            localize_columns(format_display_frame(load_side_detail[detail_columns])),
            use_container_width=True,
            hide_index=True,
        )
        _display_mapping_expander(st, display_columns, "推荐组合字段对应关系")


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


def _render_economy_v1(
    st,
    summary: pd.DataFrame,
    bess_calendar_life_years: float = 15.0,
    *,
    render_recommendation: bool = True,
) -> None:
    st.markdown("---")
    st.header("经济性评价 V1")
    st.caption("经济性评价仅读取方案汇总结果，不重新计算逐小时调度。")

    with st.expander("经济性参数", expanded=False):
        st.markdown("#### 基本参数")
        c1, c2, c3 = st.columns(3)
        operation_years = int(c1.number_input("运营期（年）", value=25, min_value=1, max_value=40, step=1))
        discount_rate = _percent_text_input(c2, "折现率（%）", 6, min_value=-99, max_value=100)
        min_power_side_acceptable_firr = _optional_percent_text_input(
            c3,
            "电源侧最低可接受 FIRR（%）",
            7,
            min_value=0,
            max_value=100,
            help="用于负荷侧可成交收益席位筛选。留空时，该席位不参与默认排序。",
        )

        st.markdown("##### Year 0 建设投资")
        c1, c2, c3, c4 = st.columns(4)
        wind_capex = _float_text_input(c1, "风电单位造价（元/kW，含税）", 4500, min_value=0.0)
        pv_capex = _float_text_input(
            c2,
            "光伏单位造价（元/kW，含税）",
            2500,
            min_value=0.0,
            help="需与光伏标幺曲线容量基准匹配；直流侧曲线填直流侧造价，交流侧曲线填交流侧造价。",
        )
        bess_capex = _float_text_input(c3, "储能单位造价（元/kWh，含税）", 900, min_value=0.0)
        dedicated_connection_line = _float_text_input(c4, "送出线路工程投资（万元，含税）", 0, min_value=0.0)

        c1, c2 = st.columns(2)
        other_fixed_asset = _float_text_input(c1, "其他固定资产投资（万元，含税）", 0, min_value=0.0)
        construction_vat_rate = _percent_text_input(c2, "建设投资进项税率（%）", 10)

        st.markdown("#### 成本费用")
        c1, c2, c3, c4 = st.columns(4)
        wind_om = _float_text_input(c1, "风电运维成本（元/kW/年）", 50, min_value=0.0)
        pv_om = _float_text_input(c2, "光伏运维成本（元/kW/年）", 25, min_value=0.0)
        bess_om = _float_text_input(c3, "储能运维成本（元/kW/年）", 18, min_value=0.0)
        other_operating_cost = _float_text_input(c4, "其他运行成本（万元/年）", 0, min_value=0.0)

        st.markdown("##### 储能更换")
        st.caption("储能更换发生年份以日历寿命和循环寿命哪个先到为准；更换后重新开始计算下一次更换。")
        c1, c2 = st.columns(2)
        replacement_ratio = _percent_text_input(c1, "储能更换投资比例（%）", 50)
        replacement_vat_rate = _percent_text_input(c2, "储能更换进项税率（%）", 13)
        replacement_calendar_life = float(bess_calendar_life_years)

        st.markdown("#### 收入和税金")
        c1, c2, c3, c4 = st.columns(4)
        grid_export_price = _float_text_input(c1, "上网电价（元/kWh，含税）", 0.25, min_value=0.0)
        self_use_price = _float_text_input(
            c2,
            "绿电结算价（元/kWh，含税）",
            0.40,
            min_value=0.0,
            help="原“自发自用电价”。电源侧视角中作为绿电售电收入，负荷侧视角中作为绿电购电成本。非用户到户电价，不含输配电价、政府基金及附加、系统运行费和容需量电费等。",
        )
        net_avoided_grid_cost_price = _float_text_input(
            c3,
            "外部购电净成本单价（元/kWh）",
            0.50,
            min_value=0.0,
            help=(
                "用于同一主体口径估算每 1 kWh 自发自用绿电替代外部购电带来的税前净节费。"
                "简化模式下直接使用本输入值；组价模式公式：外部购电净成本单价="
                "原外部购网电电量类成本单价-绿电直连自发自用仍需缴纳费用单价。"
                "不等同于负荷侧比较绿电结算价时使用的到户电能量全价。"
            ),
        )
        environmental_value = _float_text_input(c4, "环境价值单价（元/kWh）", 0, min_value=0.0)

        c1, c2, c3 = st.columns(3)
        output_vat_rate = _percent_text_input(c1, "销项税率（%）", 13)
        income_tax_rate = _percent_text_input(c2, "企业所得税率（%）", 25)
        urban_area = c3.selectbox("城建税地区", ["县城、镇 5%", "市区 7%", "其他 1%"])
        urban_tax_rate = {"市区 7%": 0.07, "县城、镇 5%": 0.05, "其他 1%": 0.01}[urban_area]

        with st.expander("高级：其他经营收入", expanded=False):
            st.caption("一般项目可不填。可输入负值；负值在 V1 中不产生进项税，按收入抵减或额外经营性支出处理。")
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

        st.markdown("#### 电费构成参数")
        with st.expander("高级：电费清单组价和价格曲线", expanded=False):
            use_grid_price_build_up = st.checkbox(
                "按电费清单组价覆盖外部购电净成本和负荷侧可减少费用",
                value=False,
                help="默认使用上方固定值；勾选后按电费清单中的电量电费项目分别推导同一主体净成本口径和负荷侧现金口径。",
            )
            if use_grid_price_build_up:
                c1, c2, c3 = st.columns(3)
                energy_market_price = _float_text_input(c1, "电能量/市场购电价格（元/kWh，含税）", 0.40, min_value=0.0)
                line_loss_price = _float_text_input(c2, "上网环节线损费用（元/kWh，含税）", 0, min_value=0.0)
                system_operation_fee = _float_text_input(c3, "系统运行费用（元/kWh，含税）", 0, min_value=0.0)
                c1, c2, c3 = st.columns(3)
                transmission_distribution_tariff = _float_text_input(c1, "输配电价（元/kWh，含税）", 0.15, min_value=0.0)
                gov_fund_surcharge = _float_text_input(c2, "政府性基金及附加（元/kWh）", 0.03, min_value=0.0, help="按无增值税电量附加处理。")
                grid_purchase_vat_rate = _percent_text_input(c3, "电网购电增值税率（%）", 13)
                st.caption("以下为绿电直连自发自用电量仍需缴纳的费用。1192 号文系统运行费暂按下网电量缴纳，自发自用绿电不在这里设置系统运行费扣减。")
                c1, c2 = st.columns(2)
                retained_transmission_distribution_tariff = _float_text_input(
                    c1,
                    "绿电仍缴输配电价（元/kWh，含税）",
                    transmission_distribution_tariff,
                    min_value=0.0,
                )
                retained_gov_fund_surcharge = _float_text_input(
                    c2,
                    "绿电仍缴政府性基金及附加（元/kWh）",
                    gov_fund_surcharge,
                    min_value=0.0,
                )
                net_avoided_grid_cost_price_for_calc = None
            else:
                energy_market_price = 0.0
                line_loss_price = 0.0
                system_operation_fee = 0.0
                transmission_distribution_tariff = 0.0
                gov_fund_surcharge = 0.0
                retained_transmission_distribution_tariff = 0.0
                retained_gov_fund_surcharge = 0.0
                grid_purchase_vat_rate = 0.13
                net_avoided_grid_cost_price_for_calc = net_avoided_grid_cost_price
            override_load_side_avoided_charge = st.checkbox(
                "单独覆盖负荷侧可减少购网费用单价",
                value=False,
                help=(
                    "默认由上方固定价或电费清单组价内部推导；只有负荷侧账单口径与同一主体净节费口径明显不同时才需要覆盖。"
                ),
            )
            if override_load_side_avoided_charge:
                load_side_avoided_charge_price_override = _float_text_input(
                    st,
                    "负荷侧可减少购网费用单价（元/kWh）",
                    net_avoided_grid_cost_price,
                    min_value=0.0,
                    help=(
                        "用于负荷侧可成交收益席位，表示绿电替代购网电后，负荷侧每 1 kWh "
                        "自发自用绿电可减少的电量类购网费用现金口径。"
                    ),
                )
            else:
                load_side_avoided_charge_price_override = None
            st.caption("容需量电费和力调电费 V1 默认不参与节费测算：它们通常不随自发自用电量按 kWh 线性变化，后续作为高级模型单独研究。")
            st.caption("绿电结算价曲线、外部购电净成本曲线和上网电价曲线后续按 CSV/Excel 上传处理，不做网页逐项录入。当前页面先使用固定价。")

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
        dedicated_connection_line_investment_with_vat=dedicated_connection_line,
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
        bess_calendar_life_years=replacement_calendar_life,
        urban_maintenance_tax_rate=urban_tax_rate,
        income_tax_rate=income_tax_rate,
        discount_rate=discount_rate,
    )
    avoided_grid_params = AvoidedGridPurchaseParams(
        net_avoided_grid_cost_price=net_avoided_grid_cost_price_for_calc,
        energy_market_price_with_vat=energy_market_price,
        line_loss_price_with_vat=line_loss_price,
        system_operation_fee_with_vat=system_operation_fee,
        transmission_distribution_tariff_with_vat=transmission_distribution_tariff,
        gov_fund_surcharge=gov_fund_surcharge,
        green_direct_retained_transmission_distribution_tariff_with_vat=retained_transmission_distribution_tariff,
        green_direct_retained_gov_fund_surcharge=retained_gov_fund_surcharge,
        grid_purchase_vat_rate=grid_purchase_vat_rate,
        environmental_value_per_kwh=environmental_value,
    )
    derived_load_side_avoided_charge_price = calc_avoided_grid_purchase_cash_price(
        avoided_grid_params
    )
    load_side_avoided_charge_price_for_calc = (
        load_side_avoided_charge_price_override
        if load_side_avoided_charge_price_override is not None
        else derived_load_side_avoided_charge_price
    )

    if st.button("计算经济性 V1（当前已实现视角）", key="run_economy_v1_all"):
        try:
            with st.spinner("正在计算电源侧和同一主体经济性年度现金流..."):
                economic_study_result = run_economic_study(
                    summary,
                    economic_params=params,
                    avoided_grid_params=avoided_grid_params,
                    load_side_avoided_charge_price=load_side_avoided_charge_price_for_calc,
                    green_power_settlement_price_with_vat=self_use_price,
                    environmental_value_per_kwh=environmental_value,
                    min_power_side_acceptable_firr=min_power_side_acceptable_firr,
                )
            st.session_state["economy_v1_result"] = {
                "summary": economic_study_result.power_summary,
                "annual_cashflows": economic_study_result.power_annual_cashflows,
            }
            st.session_state["single_entity_economy_result"] = {
                "summary": economic_study_result.single_entity_summary,
                "annual_cashflows": economic_study_result.single_entity_annual_cashflows,
            }
            st.session_state["recommendation_v1_inputs"] = economic_study_result.recommendation_inputs.to_session_dict()
            st.session_state.pop("download_payloads", None)
        except ValueError as exc:
            st.error(f"经济性参数有误：{exc}")

    economy_result = st.session_state.get("economy_v1_result")
    single_entity_result = st.session_state.get("single_entity_economy_result")
    if not economy_result and not single_entity_result:
        return

    if economy_result:
        economic_summary = economy_result["summary"]
        annual_cashflows = economy_result["annual_cashflows"]
        if not economic_summary.empty:
            display_economic_summary = _merge_result_context(economic_summary, summary)
            display_columns = [
                "scenario_id",
                "方案类型",
                "pv_capacity",
                "wind_capacity",
                "bess_energy",
                "fnpv",
                "firr",
                "firr_status",
                "static_payback_year",
                "dynamic_payback_year",
                "construction_cash_outflow",
                "dedicated_connection_line_investment_with_vat",
                "annual_operating_revenue_with_vat",
                "annual_operating_cost_with_vat",
                "bess_replacement_operation_year",
                "bess_replacement_operation_years",
                "bess_replacement_count",
            ]
            display_columns = [column for column in display_columns if column in display_economic_summary.columns]
            st.success("电源侧经济性 V1 已计算。技术方案汇总表仍保持纯技术指标，经济性结果请在本区单独下载。")

            with st.expander("高级：电源侧经济性汇总表和年度现金流下载", expanded=False):
                st.dataframe(
                    localize_columns(format_display_frame(display_economic_summary[display_columns])),
                    use_container_width=True,
                    hide_index=True,
                )
                _display_mapping_expander(st, display_columns, "电源侧经济性汇总字段对应关系")

                st.download_button(
                    "下载电源侧经济性汇总 Excel",
                    data=_build_excel_bytes(
                        {
                            "电源侧经济性汇总": localize_columns(display_economic_summary[display_columns]),
                        }
                    ),
                    file_name="power_side_economic_summary.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_power_side_economy_summary",
                )

                selected_id = st.selectbox(
                    "选择方案下载电源侧年度明细",
                    economic_summary["scenario_id"].astype(str).tolist(),
                    key="power_side_annual_select",
                )
                annual = annual_cashflows[selected_id]

                st.download_button(
                    "下载所选方案电源侧年度现金流 Excel",
                    data=_build_excel_bytes(
                        {
                            f"电源侧年度现金流_{selected_id}": localize_columns(annual),
                        }
                    ),
                    file_name=f"power_side_annual_cashflow_{selected_id}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_economy_v1",
                )

    if single_entity_result:
        single_entity_summary = single_entity_result["summary"]
        single_entity_annual_cashflows = single_entity_result["annual_cashflows"]
        if not single_entity_summary.empty:
            display_single_entity_summary = _merge_result_context(single_entity_summary, summary)
            single_entity_columns = [
                "scenario_id",
                "方案类型",
                "pv_capacity",
                "wind_capacity",
                "bess_energy",
                "single_entity_fnpv_pre_tax",
                "single_entity_firr_pre_tax",
                "single_entity_firr_status",
                "single_entity_static_payback_year",
                "single_entity_dynamic_payback_year",
                "initial_investment_basis",
                "construction_cash_outflow_with_vat",
                "annual_self_use_saving",
                "annual_avoided_grid_purchase_cash_saving",
                "annual_environmental_value",
                "annual_grid_export_revenue_without_vat",
                "annual_operating_cost_basis",
                "net_avoided_grid_cost_price",
                "avoided_grid_purchase_cash_price",
                "energy_market_price_with_vat",
                "line_loss_price_with_vat",
                "system_operation_fee_with_vat",
                "transmission_distribution_tariff_with_vat",
                "gov_fund_surcharge",
                "green_direct_retained_transmission_distribution_tariff_with_vat",
                "green_direct_retained_gov_fund_surcharge",
                "bess_replacement_operation_year",
                "bess_replacement_operation_years",
                "bess_replacement_count",
            ]
            single_entity_columns = [
                column for column in single_entity_columns if column in display_single_entity_summary.columns
            ]
            st.success("同一主体税前经济性已计算。该结果不并入技术方案概览表，也不覆盖电源侧经济性。")

            with st.expander("高级：同一主体税前经济性汇总表和年度现金流下载", expanded=False):
                st.dataframe(
                    localize_columns(format_display_frame(display_single_entity_summary[single_entity_columns])),
                    use_container_width=True,
                    hide_index=True,
                )
                _display_mapping_expander(st, single_entity_columns, "同一主体经济性汇总字段对应关系")

                st.download_button(
                    "下载同一主体税前经济性汇总 Excel",
                    data=_build_excel_bytes(
                        {
                            "同一主体经济性汇总": localize_columns(
                                display_single_entity_summary[single_entity_columns]
                            ),
                        }
                    ),
                    file_name="single_entity_pre_tax_economic_summary.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_single_entity_summary",
                )

                selected_id = st.selectbox(
                    "选择方案下载同一主体年度明细",
                    single_entity_summary["scenario_id"].astype(str).tolist(),
                    key="single_entity_annual_select",
                )
                annual = single_entity_annual_cashflows[selected_id]

                st.download_button(
                    "下载所选方案同一主体年度现金流 Excel",
                    data=_build_single_entity_annual_workbook_bytes(
                        scenario_id=selected_id,
                        annual=annual,
                        technical_summary=summary,
                        economic_summary=single_entity_summary,
                    ),
                    file_name=f"single_entity_pre_tax_annual_cashflow_{selected_id}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_single_entity_annual_cashflow",
                )

    if render_recommendation and economy_result and not economy_result["summary"].empty:
        recommendation_single_entity_summary = (
            single_entity_result["summary"]
            if single_entity_result and not single_entity_result["summary"].empty
            else None
        )
        _render_recommendation_v1(
            st,
            summary,
            economy_result["summary"],
            recommendation_single_entity_summary,
            economic_params=params,
            load_side_avoided_charge_price=load_side_avoided_charge_price_for_calc,
            green_power_settlement_price_with_vat=self_use_price,
            environmental_value_per_kwh=environmental_value,
            min_power_side_acceptable_firr=min_power_side_acceptable_firr,
        )


def _render_workflow_navigation(st) -> str:
    with st.sidebar:
        st.markdown("### 工作流")
        page = st.radio(
            "工作流阶段",
            WORKFLOW_PAGES,
            key="workflow_page",
            label_visibility="collapsed",
        )
        batch_result = st.session_state.get("batch_result")
        economy_result = st.session_state.get("economy_v1_result")
        st.caption(f"技术仿真：{'已完成' if batch_result else '未完成'}")
        st.caption(
            "经济性评价："
            f"{'已完成' if economy_result and not economy_result.get('summary', pd.DataFrame()).empty else '未完成'}"
        )
    return page


def _go_to_workflow_page(st, page: str) -> None:
    st.session_state["workflow_page"] = page
    if hasattr(st, "rerun"):
        st.rerun()


def _get_bess_calendar_life_years(st) -> float:
    snapshot = st.session_state.get("config_snapshot", {})
    try:
        return float(snapshot.get("bess_calendar_life_years", 15.0))
    except (TypeError, ValueError):
        return 15.0


def _summary_from_batch_result(batch_result) -> pd.DataFrame:
    summary = batch_result.summary
    if summary.empty:
        return summary
    return _add_scenario_type(summary)


def _render_missing_step(st, target_page: str, message: str) -> None:
    st.info(message)
    if st.button(f"进入{target_page}", key=f"go_{target_page}"):
        _go_to_workflow_page(st, target_page)


def _render_welcome_page(st) -> None:
    st.header("绿电直连 / 微电网方案策划与推荐平台")
    st.caption("当前版本优先打通技术仿真、经济性评价、推荐组合和代表方案分析，不把全量枚举表作为主入口。")

    batch_result = st.session_state.get("batch_result")
    economy_result = st.session_state.get("economy_v1_result")
    summary = _summary_from_batch_result(batch_result) if batch_result else pd.DataFrame()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("技术仿真", "已完成" if batch_result else "待开始")
    c2.metric("经济性评价", "已完成" if economy_result and not economy_result.get("summary", pd.DataFrame()).empty else "待开始")
    c3.metric("方案数量", int(batch_result.scenario_count) if batch_result else 0)
    c4.metric("达标方案", int(summary["pass_policy"].sum()) if not summary.empty and "pass_policy" in summary.columns else 0)

    st.markdown(
        """
        **推荐使用路径**

        1. 技术仿真：上传负荷、光伏、风电曲线，设置风光储遍历范围和政策约束。
        2. 经济性评价：输入少量核心经济参数，默认用一个外部购电净成本口径派生负荷侧节费口径。
        3. 推荐方案与详细分析：查看四个推荐席位、用户指定方案、能量流向和运行曲线。
        """
    )
    if st.button("开始技术仿真", type="primary", key="welcome_start_technical"):
        _go_to_workflow_page(st, "技术仿真")


def _render_recommendation_analysis_page(st, batch_result, summary: pd.DataFrame) -> None:
    st.header("推荐方案与详细分析")
    st.caption("这里集中展示推荐组合、用户指定方案和逐小时图表分析。全量枚举表仍保留在技术仿真页的高级区域。")

    economy_result = st.session_state.get("economy_v1_result")
    single_entity_result = st.session_state.get("single_entity_economy_result")
    recommendation_inputs = st.session_state.get("recommendation_v1_inputs")
    if not economy_result or economy_result.get("summary", pd.DataFrame()).empty:
        _render_missing_step(st, "经济性评价", "请先完成经济性评价，再生成推荐席位和经济性图表。")
        return
    if not recommendation_inputs:
        _render_missing_step(st, "经济性评价", "请重新运行一次经济性评价，以保存推荐席位所需的价格和门槛参数。")
        return

    recommendation_single_entity_summary = (
        single_entity_result["summary"]
        if single_entity_result and not single_entity_result["summary"].empty
        else None
    )
    _render_recommendation_v1(
        st,
        summary,
        economy_result["summary"],
        recommendation_single_entity_summary,
        economic_params=recommendation_inputs["economic_params"],
        load_side_avoided_charge_price=recommendation_inputs["load_side_avoided_charge_price"],
        green_power_settlement_price_with_vat=recommendation_inputs["green_power_settlement_price_with_vat"],
        environmental_value_per_kwh=recommendation_inputs["environmental_value_per_kwh"],
        min_power_side_acceptable_firr=recommendation_inputs["min_power_side_acceptable_firr"],
    )
    render_chart_analysis(
        st,
        batch_result,
        summary,
        economy_result=economy_result,
    )


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="绿电直连风光储方案策划平台", layout="wide")
    st.title("绿电直连风光储方案策划与测算平台")
    workflow_page = _render_workflow_navigation(st)

    if workflow_page == "欢迎页":
        _render_welcome_page(st)
        return

    if workflow_page in {"经济性评价", "推荐方案与详细分析"}:
        batch_result = st.session_state.get("batch_result")
        if not batch_result:
            _render_missing_step(st, "技术仿真", "请先完成技术仿真，经济性评价和推荐分析会读取技术仿真的方案汇总。")
            return
        summary = _summary_from_batch_result(batch_result)
        if summary.empty:
            st.warning("没有成功生成方案结果，请回到技术仿真页检查输入数据和方案范围。")
            return
        if workflow_page == "经济性评价":
            _render_economy_v1(
                st,
                summary,
                bess_calendar_life_years=_get_bess_calendar_life_years(st),
                render_recommendation=False,
            )
        else:
            _render_recommendation_analysis_page(st, batch_result, summary)
        return

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
            bess_calendar_life = st.number_input(
                "电池日历寿命（年）",
                value=15.0,
                min_value=1.0,
                max_value=40.0,
                step=1.0,
                help="当前不参与小时调度，只在经济性评价中与循环寿命共同决定储能更换年份。",
            )

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
        if scenario_count == 0:
            st.error("当前容量范围没有可用候选方案：至少需要配置光伏或风电容量，纯储能/无绿电来源组合不会进入候选池。")
            scenario_grid = None
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
                "bess_calendar_life_years": 15.0,
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
                "bess_calendar_life_years": bess_calendar_life,
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
    c3.metric("最高绿电占比", f"{summary['green_load_rate'].max():.1%}")
    c4.metric("最低弃电率", f"{summary['curtail_rate'].min():.1%}")
    c5.metric("最低下网比例", f"{summary['grid_import_rate'].min():.1%}")

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

    st.info("技术仿真已完成。下一步请进入“经济性评价”设置经济参数并生成推荐所需的经济结果。")
    if st.button("进入经济性评价", key="technical_go_economy"):
        _go_to_workflow_page(st, "经济性评价")


if __name__ == "__main__":
    main()
