# 图表模块数据契约与开发边界

> **状态：讨论稿**
>
> 本文档用于约束“绿电直连风光储配置方案典型图表制作模块”与现有方案计算模块之间的数据边界、职责边界和开发边界。  
> 后续进入正式开发前，应结合现有项目代码字段、文件结构和实际输出结果进一步校核。

---

## 1. 契约目的

本文件用于约束图表模块与现有方案计算模块之间的关系。

核心原则：

> 计算模块负责算清楚每小时发生了什么，图表模块负责把发生的事情解释清楚。

图表模块不得重新实现或修改核心能量平衡逻辑。

---

## 2. 模块边界

### 2.1 图表模块可以做的事

图表模块可以：

1. 读取项目参数；
2. 读取方案参数；
3. 读取方案汇总结果；
4. 读取逐小时明细结果；
5. 做日度、月度、年度展示性聚合；
6. 做热力图透视；
7. 做多方案对比；
8. 生成交互图；
9. 生成静态图；
10. 导出图表数据；
11. 输出图表口径说明；
12. 输出异常时段表。

### 2.2 图表模块禁止做的事

图表模块禁止：

1. 重新计算新能源出力分配；
2. 重新计算储能充放电；
3. 重新滚动 SOC；
4. 重新判断上网或弃电；
5. 重新判断下网缺口；
6. 重新处理站用电抵扣逻辑；
7. 重新定义政策指标口径；
8. 改变已有计算结果字段含义；
9. 在图表层修正或覆盖计算模块输出；
10. 为了画图而修改核心仿真逻辑。

---

## 3. 允许的展示性聚合

图表模块允许基于已有字段做以下聚合：

```text
hourly_detail → daily_summary
hourly_detail → monthly_summary
hourly_detail → annual_summary_for_chart
hourly_detail → heatmap_matrix
summary → multi_scenario_comparison
```

但这些聚合只能使用已有字段求和、均值、最大值、最小值、分位数、排序、透视，不得重算核心调度过程。

---

## 4. 标准输入对象

图表模块应优先消费以下对象或等效数据结构：

```text
ProjectConfig
ScenarioConfig
ScenarioSummary
HourlyDetail
MonthlySummary，可选
PolicyThresholds
ChartSettings
```

如果现有项目尚未定义这些对象，图表模块应通过适配层读取现有 DataFrame 或 CSV，不得强行大改原有计算模块。

---

## 5. ScenarioSummary 推荐字段

图表模块需要以下方案汇总字段。

如果现有 summary 中缺少字段，应先在适配层兼容；确需补充时，只允许在计算模块输出端追加字段，不得改变原字段含义。

```text
scenario_id
scenario_name

pv_capacity
wind_capacity
battery_power
battery_duration
battery_energy_capacity

total_load_energy
renewable_available_energy

pv_station_use_energy
wind_station_use_energy

renewable_direct_to_load_energy
battery_charge_from_renewable_energy
battery_discharge_to_load_energy
battery_loss_energy

renewable_self_consumed_energy
renewable_self_consumption_rate

grid_export_energy
grid_export_rate

curtailment_energy
curtailment_rate

grid_import_energy
grid_import_rate
grid_import_shortage_energy

green_power_share

battery_equivalent_cycles
battery_charge_energy
battery_discharge_energy
battery_loss_rate
soc_end

max_grid_import_power
max_grid_export_power
max_grid_exchange_power

is_feasible
failure_reasons
```

---

## 6. HourlyDetail 推荐字段

图表模块需要以下逐小时字段。

```text
scenario_id
timestamp
hour_index
date
month
day_of_year
hour

load_power

pv_raw_power
wind_raw_power

pv_positive_power
wind_positive_power

pv_station_use_power
wind_station_use_power

renewable_positive_power
renewable_net_power

renewable_to_load_power
surplus_renewable_power

battery_charge_power
battery_discharge_power
battery_discharge_to_load_power
battery_soc
battery_energy

grid_import_power
grid_export_power
grid_exchange_power

curtailment_power
grid_import_shortage_power

is_battery_charging
is_battery_discharging
is_soc_min_hit
is_soc_max_hit
is_grid_import_limit_hit
is_grid_export_limit_hit
is_export_ratio_limit_hit

curtailment_reason
```

其中 `curtailment_reason` 第一阶段可以为空或缺省，但代码结构应预留。

---

## 7. 口径统一要求

### 7.1 功率与电量

逐小时数据中，功率单位为万千瓦。

当时间步长为 1 小时时：

```text
小时电量 = 小时平均功率 × 1h
```

图表标题必须区分：

- 功率图：万千瓦；
- 电量图：万千瓦时。

### 7.2 新能源自身消纳

建议使用计算模块输出字段，不在图表层重算。

推荐口径：

```text
新能源自身消纳电量 = 新能源直供负荷电量 + 储能放电供负荷电量
```

储能充电量不能直接等同于最终消纳电量，因为存在储能损耗。

### 7.3 上网比例

```text
上网比例 = 上网电量 / 新能源总可用发电量
```

该指标为年度累计电量指标，不是逐小时功率比例。

### 7.4 绿电占用电比例

```text
绿电占用电比例 = 新能源自身消纳电量 / 用户总用电量
```

### 7.5 站用电

光伏、风电标幺值允许为负。

负值代表站用电，不代表新能源反向发电。

图表模块不得自行修改站用电口径，应读取计算模块输出的：

```text
pv_station_use_power
wind_station_use_power
pv_station_use_energy
wind_station_use_energy
```

---

## 8. 图表函数返回契约

所有图表函数必须返回统一结构。

建议使用 dataclass 或等效 dict。

```python
@dataclass
class ChartResult:
    chart_id: str
    chart_name: str
    figure: Any
    data: pd.DataFrame
    meta: dict
    warnings: list[str]
```

其中：

```text
chart_id：图表唯一标识
chart_name：图表名称
figure：plotly 或 matplotlib 图对象
data：生成图表所用的数据表
meta：图表口径元信息
warnings：图表生成过程中的提示或风险
```

---

## 9. ChartMeta 推荐字段

```text
unit
x_axis
y_axis
series_fields
fields_used
aggregation_method
calculation_basis
policy_thresholds
scenario_ids
time_range
notes
warnings
export_ready
```

---

## 10. 图表函数命名建议

### 10.1 单方案图表

```python
build_indicator_cards(...)
build_policy_bar_chart(...)
build_daily_balance_chart(...)
build_heatmap_chart(...)
build_monthly_load_source_chart(...)
build_monthly_renewable_flow_chart(...)
build_soc_chart(...)
build_battery_power_chart(...)
build_grid_exchange_chart(...)
build_duration_curve_chart(...)
build_abnormal_day_table(...)
build_station_use_chart(...)
```

### 10.2 多方案图表

```python
build_multi_policy_comparison(...)
build_multi_capacity_comparison(...)
build_multi_renewable_flow_comparison(...)
build_multi_load_source_comparison(...)
build_curtailment_vs_self_consumption_scatter(...)
build_multi_battery_cycles_comparison(...)
```

---

## 11. 导出契约

每张图应同时支持：

1. Streamlit 页面展示；
2. 静态图片导出；
3. 图表数据导出；
4. 口径说明导出。

推荐导出结构：

```text
output/
  charts/
    scenario_S001/
      S01_indicator_cards.png
      S03_daily_balance.html
      S03_daily_balance.png
      S03_daily_balance_data.xlsx
      S03_daily_balance_meta.md
    comparison/
      M01_multi_policy_comparison.png
      M05_curtailment_scatter.html
  data/
    selected_scenario_summary.xlsx
    selected_hourly_detail.xlsx
  report_assets/
    chart_index.md
```

---

## 12. 缺字段处理规则

如果图表所需字段缺失，图表模块应：

1. 显示友好提示；
2. 列出缺失字段；
3. 不崩溃；
4. 不自行重算核心逻辑；
5. 在 warnings 中记录；
6. 建议用户重新运行方案计算或升级计算模块输出字段。

示例：

```text
无法生成“弃电原因分解图”，缺少字段 curtailment_reason。
请升级计算模块，在逐小时仿真过程中记录弃电原因。
```

---

## 13. 测试要求

至少应提供以下测试：

1. ChartResult 结构测试；
2. 缺字段时不崩溃测试；
3. 8760 小时热力图测试；
4. 8784 小时热力图测试；
5. 单方案图表 smoke test；
6. 多方案图表 smoke test；
7. 导出 PNG / HTML / Excel 测试；
8. 原有方案计算模块回归测试。

---

## 14. 第一阶段不做事项

第一阶段不做：

1. 经济性评价；
2. 自动最优方案推荐；
3. 复杂 Word/PDF 报告生成；
4. 完整桑基图；
5. 复杂弃电原因分解；
6. 调度优化算法；
7. 修改核心仿真口径。
