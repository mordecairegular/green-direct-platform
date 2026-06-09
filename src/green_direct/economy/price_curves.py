"""Hourly price-curve input, validation, alignment, and economy aggregation."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO, Mapping

import pandas as pd

from green_direct.economy.economic_inputs import AvoidedGridPurchaseParams, EconomicParams
from green_direct.economy.electricity_saving import (
    calc_avoided_grid_purchase_cash_price,
    calc_net_avoided_grid_cost_price,
)
from green_direct.io.read_curves import read_csv_auto_encoding
from green_direct.models.diagnostics import DiagnosticSeverity, InputDiagnostics

PRICE_CURVE_SUPPORTED_HOURS = (8760, 8784)

TIMESTAMP_ALIASES = (
    "timestamp",
    "time",
    "datetime",
    "时间",
    "时间戳",
    "日期时间",
)
HOUR_INDEX_ALIASES = (
    "hour_index",
    "hour index",
    "hour",
    "小时索引",
    "小时序号",
)

PRICE_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "energy_market_price_with_vat": (
        "energy_market_price_with_vat",
        "电能量/市场购电价格",
        "电能量/市场购电价格(元/kWh，含税)",
        "电能量/市场购电价格（元/kWh，含税）",
        "电度电价",
        "电度电价(元/kWh)",
        "电度电价（元/kWh）",
    ),
    "line_loss_price_with_vat": (
        "line_loss_price_with_vat",
        "上网环节线损费用",
        "线损费",
        "线损费(元/kWh)",
        "线损费（元/kWh）",
    ),
    "system_operation_fee_with_vat": (
        "system_operation_fee_with_vat",
        "系统运行费用",
        "系统运行费",
        "系统运行费(元/kWh)",
        "系统运行费（元/kWh）",
    ),
    "transmission_distribution_tariff_with_vat": (
        "transmission_distribution_tariff_with_vat",
        "输配电价",
        "输配电价(元/kWh)",
        "输配电价（元/kWh）",
    ),
    "gov_fund_surcharge": (
        "gov_fund_surcharge",
        "政府性基金及附加",
        "政府性基金及附加(元/kWh)",
        "政府性基金及附加（元/kWh）",
        "政府基金及附加",
        "政府基金附加费",
    ),
}

PRICE_VALUE_COLUMNS = tuple(PRICE_COLUMN_ALIASES.keys())
NON_NEGATIVE_COLUMNS = PRICE_VALUE_COLUMNS
RATE_COLUMNS: tuple[str, ...] = ()
BILL_COMPONENT_COLUMNS = (
    "energy_market_price_with_vat",
    "line_loss_price_with_vat",
    "system_operation_fee_with_vat",
    "transmission_distribution_tariff_with_vat",
    "gov_fund_surcharge",
)


class PriceCurveValidationError(ValueError):
    """Raised when a price curve cannot be safely used for economy evaluation."""


@dataclass(frozen=True)
class PriceCurveData:
    """Normalized price curve ready to align with hourly technical ledgers."""

    data: pd.DataFrame
    diagnostics: InputDiagnostics = field(default_factory=InputDiagnostics)
    encoding: str | None = None
    source_name: str | None = None
    matched_columns: dict[str, str] = field(default_factory=dict)
    has_explicit_hour_index: bool = False

    @property
    def warnings(self) -> list[str]:
        return self.diagnostics.warnings_as_messages()


@dataclass(frozen=True)
class PriceCurveApplicationResult:
    """Technical summary enriched with price-curve annual amounts."""

    summary: pd.DataFrame
    price_summary: pd.DataFrame
    diagnostics: InputDiagnostics


def _source_name(source: str | Path | BinaryIO | bytes) -> str | None:
    if isinstance(source, (str, Path)):
        return str(source)
    name = getattr(source, "name", None)
    return str(name) if name else None


def _read_bytes(source: str | Path | BinaryIO | bytes) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    if hasattr(source, "seek"):
        source.seek(0)
    content = source.read()
    if isinstance(content, str):
        return content.encode("utf-8")
    return content


def _looks_like_excel(raw: bytes, source_name: str | None) -> bool:
    suffix = Path(source_name).suffix.lower() if source_name else ""
    return suffix in {".xlsx", ".xlsm", ".xls"} or raw.startswith(b"PK\x03\x04")


def _read_price_source(
    source: str | Path | BinaryIO | bytes,
    *,
    sheet_name: str | int = 0,
) -> tuple[pd.DataFrame, str | None]:
    raw = _read_bytes(source)
    source_name = _source_name(source)
    if _looks_like_excel(raw, source_name):
        try:
            return pd.read_excel(BytesIO(raw), sheet_name=sheet_name), None
        except Exception as exc:  # noqa: BLE001 - reword as user-facing validation
            raise PriceCurveValidationError(f"价格曲线 Excel 读取失败：{exc}") from exc
    try:
        return read_csv_auto_encoding(raw)
    except Exception as exc:  # noqa: BLE001 - reword as user-facing validation
        raise PriceCurveValidationError(f"价格曲线 CSV 读取失败：{exc}") from exc


def _normalize_label(value: object) -> str:
    text = str(value).strip().lower()
    for old, new in {
        "（": "(",
        "）": ")",
        "／": "/",
        "，": ",",
        " ": "",
        "\u3000": "",
    }.items():
        text = text.replace(old, new)
    return text


def _alias_lookup(aliases: tuple[str, ...]) -> set[str]:
    return {_normalize_label(alias) for alias in aliases}


TIMESTAMP_ALIAS_LOOKUP = _alias_lookup(TIMESTAMP_ALIASES)
HOUR_INDEX_ALIAS_LOOKUP = _alias_lookup(HOUR_INDEX_ALIASES)
PRICE_ALIAS_LOOKUP = {
    canonical: _alias_lookup((canonical, *aliases))
    for canonical, aliases in PRICE_COLUMN_ALIASES.items()
}


def _find_matching_column(columns: pd.Index, aliases: set[str]) -> str | None:
    for column in columns:
        if _normalize_label(column) in aliases:
            return str(column)
    return None


def _numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype(float)


def _rate_series(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    percent_mask = text.str.endswith("%", na=False)
    values = pd.to_numeric(text.str.rstrip("%"), errors="coerce").astype(float)
    values.loc[percent_mask] = values.loc[percent_mask] / 100.0
    return values


def _raise_if_diagnostics_have_errors(diagnostics: InputDiagnostics) -> None:
    if not diagnostics.has_errors():
        return
    messages = [item.message for item in diagnostics.items if item.severity is DiagnosticSeverity.ERROR]
    raise PriceCurveValidationError("；".join(messages))


def read_price_curve(
    source: str | Path | BinaryIO | bytes,
    *,
    sheet_name: str | int = 0,
) -> PriceCurveData:
    """Read and validate a CSV/XLSX hourly price curve.

    The normalized output keeps only alignment columns plus recognized price
    fields. Missing price values are allowed and will fall back to fixed UI
    prices during economy aggregation.
    """

    raw, encoding = _read_price_source(source, sheet_name=sheet_name)
    diagnostics = InputDiagnostics()
    if raw.empty:
        diagnostics.add(
            DiagnosticSeverity.ERROR,
            "price_curve",
            "EMPTY_PRICE_CURVE",
            "价格曲线文件为空，请上传包含 8760 或 8784 行价格数据的 CSV/Excel。",
        )
        _raise_if_diagnostics_have_errors(diagnostics)

    matched_columns: dict[str, str] = {}
    timestamp_col = _find_matching_column(raw.columns, TIMESTAMP_ALIAS_LOOKUP)
    hour_index_col = _find_matching_column(raw.columns, HOUR_INDEX_ALIAS_LOOKUP)
    if timestamp_col is None and hour_index_col is None:
        diagnostics.add(
            DiagnosticSeverity.ERROR,
            "price_curve",
            "MISSING_ALIGNMENT_COLUMN",
            "价格曲线缺少对齐字段：请至少提供 timestamp/时间戳 或 hour_index/小时索引。",
            suggestion="建议使用 docs/templates/price_curves/price_curve_template_down_grid.csv 的表头。",
        )

    normalized = pd.DataFrame(index=raw.index)
    if timestamp_col is not None:
        matched_columns["timestamp"] = timestamp_col
        normalized["timestamp"] = pd.to_datetime(raw[timestamp_col], errors="coerce")
    else:
        normalized["timestamp"] = pd.NaT

    has_explicit_hour_index = hour_index_col is not None
    if hour_index_col is not None:
        matched_columns["hour_index"] = hour_index_col
        normalized["hour_index"] = _numeric_series(raw[hour_index_col])
    else:
        normalized["hour_index"] = range(len(raw))

    recognized_price_columns: list[str] = []
    for canonical, aliases in PRICE_ALIAS_LOOKUP.items():
        source_col = _find_matching_column(raw.columns, aliases)
        if source_col is None:
            continue
        matched_columns[canonical] = source_col
        recognized_price_columns.append(canonical)
        if canonical in RATE_COLUMNS:
            normalized[canonical] = _rate_series(raw[source_col])
        else:
            normalized[canonical] = _numeric_series(raw[source_col])

    if not recognized_price_columns:
        diagnostics.add(
            DiagnosticSeverity.ERROR,
            "price_curve",
            "MISSING_PRICE_COLUMNS",
            "价格曲线未识别到任何价格字段，请检查表头或使用模板字段。",
        )

    price_numeric = (
        normalized[recognized_price_columns]
        if recognized_price_columns
        else pd.DataFrame(index=normalized.index)
    )
    has_any_price = price_numeric.notna().any(axis=1) if not price_numeric.empty else pd.Series(False, index=normalized.index)
    has_alignment = normalized["timestamp"].notna() | normalized["hour_index"].notna()
    data_like = has_any_price | has_alignment
    dropped_rows = int((~data_like).sum())
    if dropped_rows:
        diagnostics.add(
            DiagnosticSeverity.WARNING,
            "price_curve",
            "IGNORED_NON_DATA_ROWS",
            f"价格曲线已忽略 {dropped_rows} 行空白或说明行。",
        )
    normalized = normalized.loc[data_like].reset_index(drop=True)

    row_count = len(normalized)
    if row_count not in PRICE_CURVE_SUPPORTED_HOURS:
        diagnostics.add(
            DiagnosticSeverity.ERROR,
            "price_curve",
            "INVALID_PRICE_CURVE_LENGTH",
            f"价格曲线行数为 {row_count}，当前仅支持 8760 或 8784 行。",
            suggestion="请确认是否包含表头说明行、空行，或普通年/闰年小时数是否完整。",
        )

    if normalized["timestamp"].isna().all() and normalized["hour_index"].isna().any():
        diagnostics.add(
            DiagnosticSeverity.ERROR,
            "price_curve",
            "INVALID_HOUR_INDEX",
            "价格曲线 hour_index 存在无法识别的值，且没有可用 timestamp 作为备选。",
        )

    for column in NON_NEGATIVE_COLUMNS:
        if column not in normalized.columns:
            continue
        negative = normalized[column].dropna() < 0
        if negative.any():
            first = int(negative[negative].index[0]) + 2
            diagnostics.add(
                DiagnosticSeverity.ERROR,
                "price_curve",
                "NEGATIVE_PRICE",
                f"价格字段 {column} 存在负值，首个问题约在第 {first} 行。",
                location=column,
            )

    for column in RATE_COLUMNS:
        if column not in normalized.columns:
            continue
        invalid = normalized[column].dropna().map(lambda value: not 0 <= float(value) <= 1)
        if invalid.any():
            first = int(invalid[invalid].index[0]) + 2
            diagnostics.add(
                DiagnosticSeverity.ERROR,
                "price_curve",
                "INVALID_RATE",
                f"税率字段 {column} 应为 0 到 1 之间的小数或百分比，首个问题约在第 {first} 行。",
                location=column,
            )

    _raise_if_diagnostics_have_errors(diagnostics)
    return PriceCurveData(
        data=normalized,
        diagnostics=diagnostics,
        encoding=encoding,
        source_name=_source_name(source),
        matched_columns=matched_columns,
        has_explicit_hour_index=has_explicit_hour_index,
    )


def _add_warning(diagnostics: InputDiagnostics, code: str, message: str) -> None:
    diagnostics.add(DiagnosticSeverity.WARNING, "price_curve", code, message)


def align_price_curve_to_hourly(
    price_curve: PriceCurveData,
    hourly_detail: pd.DataFrame,
    *,
    diagnostics: InputDiagnostics | None = None,
) -> tuple[pd.DataFrame, str]:
    """Return price rows ordered exactly like a scenario hourly ledger."""

    diag = diagnostics or InputDiagnostics()
    prices = price_curve.data.reset_index(drop=True)
    hourly = hourly_detail.reset_index(drop=True)
    if len(prices) != len(hourly):
        raise PriceCurveValidationError(
            f"价格曲线行数 {len(prices)} 与逐小时明细行数 {len(hourly)} 不一致，无法对齐。"
        )
    if len(prices) not in PRICE_CURVE_SUPPORTED_HOURS:
        raise PriceCurveValidationError(
            f"价格曲线/逐小时明细行数为 {len(prices)}，当前曲线模式仅支持 8760 或 8784 行。"
        )

    if "timestamp" in hourly.columns and prices["timestamp"].notna().all():
        hourly_timestamp = pd.to_datetime(hourly["timestamp"], errors="coerce")
        price_timestamp = pd.to_datetime(prices["timestamp"], errors="coerce")
        if hourly_timestamp.notna().all() and price_timestamp.is_unique and hourly_timestamp.is_unique:
            hourly_set = set(hourly_timestamp.astype("datetime64[ns]"))
            price_set = set(price_timestamp.astype("datetime64[ns]"))
            if hourly_set == price_set:
                ordered = prices.assign(_timestamp=price_timestamp).set_index("_timestamp")
                aligned = ordered.loc[hourly_timestamp.astype("datetime64[ns]")].reset_index(drop=True)
                return aligned.drop(columns=[column for column in ["_timestamp"] if column in aligned.columns]), "timestamp"
            _add_warning(
                diag,
                "PRICE_TIMESTAMP_FALLBACK",
                "价格曲线时间戳与技术逐小时明细不完全一致，已按 hour_index/行序对齐。",
            )

    if price_curve.has_explicit_hour_index:
        price_hour_index = pd.to_numeric(prices["hour_index"], errors="coerce")
        if price_hour_index.notna().all() and price_hour_index.is_unique:
            if "hour_index" in hourly.columns:
                hourly_hour_index = pd.to_numeric(hourly["hour_index"], errors="coerce")
                if hourly_hour_index.notna().all() and set(price_hour_index.astype(int)) == set(hourly_hour_index.astype(int)):
                    ordered = prices.assign(_hour_index=price_hour_index.astype(int)).set_index("_hour_index")
                    aligned = ordered.loc[hourly_hour_index.astype(int)].reset_index(drop=True)
                    return aligned.drop(columns=[column for column in ["_hour_index"] if column in aligned.columns]), "hour_index"
            expected = set(range(len(prices)))
            if set(price_hour_index.astype(int)) == expected:
                return prices.assign(_hour_index=price_hour_index.astype(int)).sort_values("_hour_index").drop(columns="_hour_index").reset_index(drop=True), "hour_index"
        _add_warning(
            diag,
            "PRICE_HOUR_INDEX_FALLBACK",
            "价格曲线 hour_index 缺失、重复或无法覆盖完整小时序号，已按文件行序对齐。",
        )

    return prices.reset_index(drop=True), "row_order"


def _series_with_default(frame: pd.DataFrame, column: str, default: float) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(float(default), index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").astype(float).fillna(float(default))


def _row_has_bill_curve(frame: pd.DataFrame) -> pd.Series:
    columns = [column for column in BILL_COMPONENT_COLUMNS if column in frame.columns]
    if not columns:
        return pd.Series(False, index=frame.index)
    return frame[columns].notna().any(axis=1)


def build_effective_hourly_prices(
    price_frame: pd.DataFrame,
    *,
    economic_params: EconomicParams,
    avoided_grid_params: AvoidedGridPurchaseParams,
    load_side_avoided_charge_price: float,
    green_power_settlement_price_with_vat: float,
    environmental_value_per_kwh: float,
) -> pd.DataFrame:
    """Fill missing hourly price cells and derive bill-build-up prices."""

    result = pd.DataFrame(index=price_frame.index)
    result["green_power_settlement_price_with_vat"] = pd.Series(
        float(green_power_settlement_price_with_vat),
        index=price_frame.index,
        dtype=float,
    )
    result["grid_export_price_with_vat"] = pd.Series(
        float(economic_params.grid_export_price_with_vat),
        index=price_frame.index,
        dtype=float,
    )
    result["environmental_value_per_kwh"] = pd.Series(
        float(environmental_value_per_kwh),
        index=price_frame.index,
        dtype=float,
    )

    energy_market = _series_with_default(
        price_frame,
        "energy_market_price_with_vat",
        avoided_grid_params.energy_market_price_with_vat,
    )
    line_loss = _series_with_default(
        price_frame,
        "line_loss_price_with_vat",
        avoided_grid_params.line_loss_price_with_vat,
    )
    system_operation = _series_with_default(
        price_frame,
        "system_operation_fee_with_vat",
        avoided_grid_params.system_operation_fee_with_vat,
    )
    transmission_distribution = _series_with_default(
        price_frame,
        "transmission_distribution_tariff_with_vat",
        avoided_grid_params.transmission_distribution_tariff_with_vat,
    )
    gov_fund = _series_with_default(
        price_frame,
        "gov_fund_surcharge",
        avoided_grid_params.gov_fund_surcharge,
    )
    vat_rate = pd.Series(
        float(avoided_grid_params.grid_purchase_vat_rate),
        index=price_frame.index,
        dtype=float,
    )
    retained_td = transmission_distribution.copy()
    retained_gov = gov_fund.copy()

    taxable_price_with_vat = energy_market + line_loss + system_operation + transmission_distribution
    bill_net_price = ((taxable_price_with_vat - retained_td) / (1 + vat_rate)) + gov_fund - retained_gov
    bill_cash_price = taxable_price_with_vat + gov_fund - retained_td - retained_gov
    down_grid_landed_price = taxable_price_with_vat + gov_fund
    green_self_use_landed_price = (
        result["green_power_settlement_price_with_vat"]
        + transmission_distribution
        + gov_fund
    )
    has_bill_curve = _row_has_bill_curve(price_frame)

    fixed_net = calc_net_avoided_grid_cost_price(avoided_grid_params)
    fixed_load = float(load_side_avoided_charge_price)
    result["net_avoided_grid_cost_price"] = pd.Series(fixed_net, index=price_frame.index, dtype=float)
    result.loc[has_bill_curve, "net_avoided_grid_cost_price"] = bill_net_price.loc[has_bill_curve]

    result["load_side_avoided_charge_price"] = pd.Series(fixed_load, index=price_frame.index, dtype=float)
    result.loc[has_bill_curve, "load_side_avoided_charge_price"] = bill_cash_price.loc[has_bill_curve]
    result["down_grid_landed_price_with_vat"] = down_grid_landed_price
    result["green_self_use_landed_price_with_vat"] = green_self_use_landed_price

    for column in [
        "green_power_settlement_price_with_vat",
        "grid_export_price_with_vat",
        "environmental_value_per_kwh",
        "net_avoided_grid_cost_price",
        "load_side_avoided_charge_price",
        "down_grid_landed_price_with_vat",
        "green_self_use_landed_price_with_vat",
    ]:
        if (result[column].dropna() < 0).any():
            raise PriceCurveValidationError(f"价格曲线推导后的 {column} 存在负值，请检查账单组价和仍缴费用。")

    return result


def _weighted_average(total_amount: float, total_energy: float, fallback: float) -> float:
    return float(total_amount) / float(total_energy) if total_energy > 0 else float(fallback)


def _hourly_power_series(hourly: pd.DataFrame, column: str) -> pd.Series:
    if column not in hourly.columns:
        return pd.Series(0.0, index=hourly.index, dtype=float)
    return pd.to_numeric(hourly[column], errors="coerce").fillna(0.0).astype(float)


def _scenario_price_summary(
    *,
    scenario_id: str,
    hourly: pd.DataFrame,
    aligned_prices: pd.DataFrame,
    alignment_mode: str,
    economic_params: EconomicParams,
    avoided_grid_params: AvoidedGridPurchaseParams,
    load_side_avoided_charge_price: float,
    green_power_settlement_price_with_vat: float,
    environmental_value_per_kwh: float,
    dt_hours: float,
) -> dict[str, Any]:
    prices = build_effective_hourly_prices(
        aligned_prices,
        economic_params=economic_params,
        avoided_grid_params=avoided_grid_params,
        load_side_avoided_charge_price=load_side_avoided_charge_price,
        green_power_settlement_price_with_vat=green_power_settlement_price_with_vat,
        environmental_value_per_kwh=environmental_value_per_kwh,
    )
    load_power = _hourly_power_series(hourly, "load_power")
    direct = _hourly_power_series(hourly, "direct_self_use_power")
    bess_discharge = _hourly_power_series(hourly, "bess_discharge_power")
    grid_import_power = _hourly_power_series(hourly, "grid_import_power")
    export_power = _hourly_power_series(hourly, "grid_export_power")
    load_energy = load_power * float(dt_hours)
    self_use_energy = (direct + bess_discharge) * float(dt_hours)
    grid_import_energy = grid_import_power * float(dt_hours)
    export_energy = export_power * float(dt_hours)

    load_total = float(load_energy.sum())
    self_use_total = float(self_use_energy.sum())
    grid_import_total = float(grid_import_energy.sum())
    export_total = float(export_energy.sum())
    before_green_landed_cost = float(
        (load_energy * prices["down_grid_landed_price_with_vat"]).sum()
    )
    after_green_down_grid_cost = float(
        (grid_import_energy * prices["down_grid_landed_price_with_vat"]).sum()
    )
    after_green_self_use_cost = float(
        (self_use_energy * prices["green_self_use_landed_price_with_vat"]).sum()
    )
    after_green_landed_cost = after_green_down_grid_cost + after_green_self_use_cost
    green_revenue_with_vat = float(
        (self_use_energy * prices["green_power_settlement_price_with_vat"]).sum()
    )
    export_revenue_with_vat = float((export_energy * prices["grid_export_price_with_vat"]).sum())
    export_revenue_without_vat = export_revenue_with_vat / (1 + economic_params.output_vat_rate)
    self_use_saving = float((self_use_energy * prices["net_avoided_grid_cost_price"]).sum())
    avoided_cash_saving = float(
        (self_use_energy * prices["load_side_avoided_charge_price"]).sum()
    )
    environmental_value = float((self_use_energy * prices["environmental_value_per_kwh"]).sum())
    load_side_green_power_cost = green_revenue_with_vat
    load_side_cash_saving_without_environment = avoided_cash_saving - load_side_green_power_cost
    load_side_annual_benefit = load_side_cash_saving_without_environment + environmental_value

    fixed_net = calc_net_avoided_grid_cost_price(avoided_grid_params)
    fixed_cash = calc_avoided_grid_purchase_cash_price(avoided_grid_params)
    green_self_use_landed_fallback = (
        float(green_power_settlement_price_with_vat)
        + float(avoided_grid_params.transmission_distribution_tariff_with_vat)
        + float(avoided_grid_params.gov_fund_surcharge)
    )
    before_green_price = _weighted_average(
        before_green_landed_cost,
        load_total,
        fixed_cash,
    )
    after_green_price = _weighted_average(
        after_green_landed_cost,
        load_total,
        before_green_price,
    )
    return {
        "scenario_id": scenario_id,
        "price_mode": "hourly_curve",
        "price_curve_alignment": alignment_mode,
        "self_use_revenue_with_vat_override": green_revenue_with_vat,
        "grid_export_revenue_with_vat_override": export_revenue_with_vat,
        "grid_export_revenue_without_vat_override": export_revenue_without_vat,
        "self_use_saving_override": self_use_saving,
        "avoided_grid_purchase_cash_saving_override": avoided_cash_saving,
        "environmental_value_override": environmental_value,
        "load_side_green_power_purchase_cost": load_side_green_power_cost,
        "load_side_cash_saving_without_environment_override": load_side_cash_saving_without_environment,
        "load_side_environmental_value_override": environmental_value,
        "load_side_annual_benefit_override": load_side_annual_benefit,
        "green_power_settlement_price_with_vat_effective": _weighted_average(
            green_revenue_with_vat,
            self_use_total,
            green_power_settlement_price_with_vat,
        ),
        "grid_export_price_with_vat_effective": _weighted_average(
            export_revenue_with_vat,
            export_total,
            economic_params.grid_export_price_with_vat,
        ),
        "net_avoided_grid_cost_price_effective": _weighted_average(
            self_use_saving,
            self_use_total,
            fixed_net,
        ),
        "avoided_grid_purchase_cash_price_effective": _weighted_average(
            avoided_cash_saving,
            self_use_total,
            fixed_cash,
        ),
        "load_side_avoided_charge_price_effective": _weighted_average(
            avoided_cash_saving,
            self_use_total,
            load_side_avoided_charge_price,
        ),
        "environmental_value_per_kwh_effective": _weighted_average(
            environmental_value,
            self_use_total,
            environmental_value_per_kwh,
        ),
        "load_landed_price_before_green_with_vat": before_green_price,
        "load_landed_price_after_green_with_vat": after_green_price,
        "load_landed_price_delta_with_vat": after_green_price - before_green_price,
        "load_landed_cost_before_green_with_vat": before_green_landed_cost,
        "load_landed_cost_after_green_with_vat": after_green_landed_cost,
        "weighted_down_grid_landed_price_with_vat": _weighted_average(
            after_green_down_grid_cost,
            grid_import_total,
            before_green_price,
        ),
        "green_self_use_landed_price_with_vat_effective": _weighted_average(
            after_green_self_use_cost,
            self_use_total,
            green_self_use_landed_fallback,
        ),
        "down_grid_energy_for_landed_price": grid_import_total,
        "self_use_energy_for_landed_price": self_use_total,
        "total_load_energy_for_landed_price": load_total,
    }


def apply_price_curve_to_summary(
    summary: pd.DataFrame,
    hourly_details: Mapping[str, pd.DataFrame],
    price_curve: PriceCurveData,
    *,
    economic_params: EconomicParams,
    avoided_grid_params: AvoidedGridPurchaseParams,
    load_side_avoided_charge_price: float,
    green_power_settlement_price_with_vat: float,
    environmental_value_per_kwh: float = 0.0,
    dt_hours: float = 1.0,
) -> PriceCurveApplicationResult:
    """Aggregate hourly price curves into per-scenario annual economy inputs."""

    diagnostics = InputDiagnostics()
    diagnostics.extend(price_curve.diagnostics)
    rows: list[dict[str, Any]] = []
    for _, summary_row in summary.iterrows():
        scenario_id = str(summary_row.get("scenario_id", ""))
        if scenario_id not in hourly_details:
            raise PriceCurveValidationError(f"缺少方案 {scenario_id} 的逐小时明细，无法应用价格曲线。")
        hourly = hourly_details[scenario_id]
        aligned, alignment_mode = align_price_curve_to_hourly(
            price_curve,
            hourly,
            diagnostics=diagnostics,
        )
        rows.append(
            _scenario_price_summary(
                scenario_id=scenario_id,
                hourly=hourly.reset_index(drop=True),
                aligned_prices=aligned,
                alignment_mode=alignment_mode,
                economic_params=economic_params,
                avoided_grid_params=avoided_grid_params,
                load_side_avoided_charge_price=load_side_avoided_charge_price,
                green_power_settlement_price_with_vat=green_power_settlement_price_with_vat,
                environmental_value_per_kwh=environmental_value_per_kwh,
                dt_hours=dt_hours,
            )
        )

    price_summary = pd.DataFrame(rows)
    enriched = summary.copy()
    if not price_summary.empty:
        enriched["scenario_id"] = enriched["scenario_id"].astype(str)
        enriched = enriched.merge(price_summary, on="scenario_id", how="left")
    return PriceCurveApplicationResult(
        summary=enriched,
        price_summary=price_summary,
        diagnostics=diagnostics,
    )
