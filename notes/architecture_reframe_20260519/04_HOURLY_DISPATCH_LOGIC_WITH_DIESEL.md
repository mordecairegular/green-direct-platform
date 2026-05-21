# 每小时调度与能量平衡核心逻辑草案

日期：2026-05-19  
状态：目标计算口径草案，供专家审查和后续开发使用  
适用范围：风、光、储能、电网、柴油发电机共同参与的并网 / 离网 / 备用供电场景

## 1. 文档目的

本文专门描述“每一个小时内部，负荷、光伏、风电、储能、电网、柴发之间如何计算和判断”。

它不讨论 UI，不讨论图表样式，也不讨论完整经济评价。它的目标是把未来程序最核心的逐小时算账逻辑写清楚，便于：

- 专家审查计算口径；
- 后续 Codex / Claude Code 实现调度策略；
- 新增柴发时避免把电网、柴油、绿电、储能混在一起；
- 保证每小时明细可人工复核。

## 2. 总体原则

### 2.1 每小时必须先形成能源事实表

每个小时都应形成一行 `HourlyEnergyLedger`。后续年度汇总、政策判断、经济性排序、图表和报告都从该逐小时台账读取。

不建议图表、经济性或报告模块重新推导核心调度逻辑。

### 2.2 能源来源必须清楚

至少区分：

- 新能源电量：光伏、风电；
- 电网电量：下网购电；
- 柴油电量：柴油发电机输出；
- 储能电量：由此前充入的电量释放。

当前基线中，储能只能由富余新能源充电，因此储能放电可以计入新能源自发自用。

未来若允许电网或柴发给储能充电，必须做储能电量来源追踪，否则不能把所有储能放电都计入绿电。

### 2.3 调度策略必须显式命名

不同项目模式下，调度顺序不同。程序不应把所有逻辑写死在一个函数里。

建议至少定义：

```text
GRID_CONNECTED_RENEWABLE_FIRST
GRID_CONNECTED_DIESEL_BACKUP
OFF_GRID_DIESEL_BACKUP
CUSTOM
```

未来如果做分时电价或经济最优调度，应新增策略，而不是悄悄修改基线策略。

### 2.4 柴发不能混入电网字段

柴发应独立记录：

```text
diesel_power
diesel_generation_energy
diesel_fuel_consumption
diesel_cost
diesel_emission
```

不能把柴发输出记入 `grid_import_power`。

### 2.5 缺供必须显式记录

离网或弱网场景中，如果风、光、储、柴、电网都不能满足负荷，应记录：

```text
unserved_load_power
unserved_load_energy
```

不能让负荷平衡公式“看起来平衡”，却隐藏缺供。

## 3. 每小时输入变量

### 3.1 时间变量

```text
t                当前小时索引
dt_hours         时间步长，当前通常为 1 小时
timestamp[t]     当前小时时间戳
```

### 3.2 负荷

```text
P_load[t]        用户负荷功率，万千瓦
```

可选扩展：

```text
P_critical_load[t]   关键负荷
P_sheddable_load[t]  可切负荷
```

初期可不区分关键负荷和可切负荷，全部视为必须满足负荷。

### 3.3 风光资源

```text
pv_pu[t]         光伏标幺值，可为负
wind_pu[t]       风电标幺值，可为负
C_pv             光伏装机容量，万千瓦
C_wind           风电装机容量，万千瓦
```

### 3.4 储能参数

```text
P_bess           储能额定功率，万千瓦
E_bess           储能额定容量，万千瓦时
SOC_min          最小 SOC
SOC_max          最大 SOC
eta_charge       充电效率
eta_discharge    放电效率
E_bess_start[t]  当前小时初储能电量
SOC_start[t]     当前小时初 SOC
```

### 3.5 电网参数

```text
allow_grid_import        是否允许下网
allow_grid_export        是否允许上网
grid_import_power_limit  最大下网功率，可为空
grid_export_power_limit  最大上网功率，可为空
grid_exchange_limit      双向交换功率限制，可为空
annual_export_cap        年度允许上网电量，可为空
cumulative_export[t]     当前小时开始前累计上网电量
```

说明：

- 如果只设置 `grid_exchange_limit`，可同时约束上网和下网；
- 如果分别设置 import/export limit，则应分别约束；
- 当前 V0.1 使用过 `grid_exchange_power_limit` 同时约束上网和下网。

### 3.6 柴发参数

```text
diesel_enabled              是否启用柴发
P_diesel_rated              柴发额定功率，万千瓦
P_diesel_min                最小出力，万千瓦，初期可为 0
fuel_liter_per_mwh          单位发电油耗，升/万千瓦时或换算后单位
diesel_fuel_price           柴油价格
diesel_variable_om_cost     柴发可变运维成本
diesel_emission_factor      排放因子
```

后续可扩展：

```text
min_stable_load
startup_cost
min_runtime
ramp_limit
fuel_curve_a
fuel_curve_b
```

初期建议先不做启停、最小运行时间、爬坡和复杂油耗曲线，避免过早复杂化。

## 4. 每小时第一步：计算风光原始出力和站用电

### 4.1 原始出力

```text
P_pv_raw = pv_pu[t] * C_pv
P_wind_raw = wind_pu[t] * C_wind
```

`P_pv_raw` 和 `P_wind_raw` 可以为负。

### 4.2 正发电与站用电拆分

```text
P_pv_generation = max(P_pv_raw, 0)
P_wind_generation = max(P_wind_raw, 0)

P_pv_station_use = max(-P_pv_raw, 0)
P_wind_station_use = max(-P_wind_raw, 0)
```

合计：

```text
P_renewable_generation = P_pv_generation + P_wind_generation
P_station_use = P_pv_station_use + P_wind_station_use
```

### 4.3 站用电抵扣

风光正发电先抵扣风光站用电：

```text
P_net_renewable = P_renewable_generation - P_station_use
P_renewable_available = max(P_net_renewable, 0)
P_station_use_deficit = max(-P_net_renewable, 0)
```

参与调度的负荷：

```text
P_dispatch_load = P_load[t] + P_station_use_deficit
```

解释：

- `P_load[t]` 是用户负荷；
- `P_station_use_deficit` 是风光站用电无法由当小时风光正发电覆盖的缺口；
- 这个缺口需要由储能、电网或柴发承担。

## 5. 当前基线：并网风光储、无柴发

策略名：

```text
GRID_CONNECTED_RENEWABLE_FIRST
```

适用：

- 并网；
- 无柴发；
- 储能只允许富余新能源充电；
- 储能只允许放电供负荷，不允许放电上网。

### 5.1 判断新能源是否足够

```text
if P_renewable_available >= P_dispatch_load:
    进入新能源富余或平衡分支
else:
    进入新能源不足分支
```

### 5.2 分支 A：新能源富余或平衡

触发条件：

```text
P_renewable_available >= P_dispatch_load
```

新能源直接供负荷：

```text
P_renewable_to_load = P_dispatch_load
P_remaining_load = 0
```

富余新能源：

```text
P_surplus = P_renewable_available - P_dispatch_load
```

储能可充功率受三类约束：

```text
P_bess_charge_limit_power = P_bess
P_bess_charge_limit_energy = (SOC_max * E_bess - E_bess_start) / eta_charge / dt_hours
P_bess_charge_limit_surplus = P_surplus
```

实际充电：

```text
P_bess_charge = min(
    P_bess_charge_limit_surplus,
    P_bess_charge_limit_power,
    P_bess_charge_limit_energy
)
```

储能电量更新：

```text
E_bess_end = E_bess_start + P_bess_charge * dt_hours * eta_charge
```

充储后的富余：

```text
P_surplus_after_bess = P_surplus - P_bess_charge
```

尝试上网：

```text
P_grid_export_possible = P_surplus_after_bess
```

如果不允许上网：

```text
P_grid_export = 0
P_curtail = P_surplus_after_bess
```

如果允许上网，则计算上网上限：

```text
P_export_limit = min(
    grid_export_power_limit or infinity,
    grid_exchange_limit or infinity
)
```

若有年度上网额度：

```text
E_export_remaining = annual_export_cap - cumulative_export
P_export_annual_limit = max(E_export_remaining / dt_hours, 0)
P_export_limit = min(P_export_limit, P_export_annual_limit)
```

实际上网：

```text
P_grid_export = min(P_grid_export_possible, P_export_limit)
P_curtail = P_surplus_after_bess - P_grid_export
```

本分支中：

```text
P_bess_discharge = 0
P_grid_import = 0
P_diesel = 0
P_unserved_load = 0
```

### 5.3 分支 B：新能源不足

触发条件：

```text
P_renewable_available < P_dispatch_load
```

新能源全部直接供负荷：

```text
P_renewable_to_load = P_renewable_available
P_remaining_load = P_dispatch_load - P_renewable_available
```

储能可放功率受三类约束：

```text
P_bess_discharge_limit_load = P_remaining_load
P_bess_discharge_limit_power = P_bess
P_bess_discharge_limit_energy = (E_bess_start - SOC_min * E_bess) * eta_discharge / dt_hours
```

实际放电：

```text
P_bess_discharge = min(
    P_bess_discharge_limit_load,
    P_bess_discharge_limit_power,
    P_bess_discharge_limit_energy
)
```

储能电量更新：

```text
E_bess_end = E_bess_start - P_bess_discharge * dt_hours / eta_discharge
```

储能放电后的剩余负荷：

```text
P_remaining_load_after_bess = P_remaining_load - P_bess_discharge
```

电网下网：

```text
if allow_grid_import:
    P_grid_import_possible = P_remaining_load_after_bess
else:
    P_grid_import_possible = 0
```

下网功率上限：

```text
P_import_limit = min(
    grid_import_power_limit or infinity,
    grid_exchange_limit or infinity
)
```

实际下网：

```text
P_grid_import = min(P_grid_import_possible, P_import_limit)
P_unserved_load = P_remaining_load_after_bess - P_grid_import
```

本分支中：

```text
P_bess_charge = 0
P_grid_export = 0
P_curtail = 0
P_diesel = 0
```

若 `P_unserved_load > 0`，并网基线方案应判为不可行或不达标。

## 6. 并网加柴发备用策略

策略名：

```text
GRID_CONNECTED_DIESEL_BACKUP
```

适用：

- 项目并网；
- 柴发存在，但主要作为备用；
- 正常情况下优先使用电网而不是柴发；
- 当电网不可用、下网受限或用户指定柴发兜底时，柴发补足剩余缺口。

### 6.1 富余分支

新能源富余时，与并网风光储基线一致：

```text
新能源供负荷
-> 富余新能源充储能
-> 剩余富余上网或弃电
```

柴发不运行：

```text
P_diesel = 0
```

初期不建议让柴发在新能源富余时运行，也不建议让柴发给储能充电。

### 6.2 不足分支

当新能源不足：

```text
新能源供负荷
-> 储能放电
-> 电网下网
-> 柴发补足电网无法满足的剩余缺口
-> 仍不足则缺供
```

具体计算：

```text
P_renewable_to_load = P_renewable_available
P_remaining_load = P_dispatch_load - P_renewable_available
```

储能放电同基线：

```text
P_bess_discharge = min(
    P_remaining_load,
    P_bess,
    (E_bess_start - SOC_min * E_bess) * eta_discharge / dt_hours
)
```

```text
P_remaining_after_bess = P_remaining_load - P_bess_discharge
```

电网下网：

```text
P_grid_import_possible = P_remaining_after_bess if allow_grid_import else 0
P_grid_import = min(P_grid_import_possible, P_import_limit)
```

电网后仍未满足的负荷：

```text
P_remaining_after_grid = P_remaining_after_bess - P_grid_import
```

柴发补足：

```text
if diesel_enabled:
    P_diesel = min(P_remaining_after_grid, P_diesel_rated)
else:
    P_diesel = 0
```

缺供：

```text
P_unserved_load = P_remaining_after_grid - P_diesel
```

柴发油耗和成本：

```text
E_diesel = P_diesel * dt_hours
diesel_fuel_consumption = E_diesel * fuel_liter_per_energy
diesel_fuel_cost = diesel_fuel_consumption * diesel_fuel_price
diesel_variable_om_cost_total = E_diesel * diesel_variable_om_cost
diesel_emission = E_diesel * diesel_emission_factor
```

注意：

- `P_diesel` 不计入 `P_grid_import`；
- `E_diesel` 不计入新能源发电；
- 柴发供负荷不计入绿电占比；
- 若 `P_unserved_load > 0`，方案应记录可靠性不达标。

## 7. 离网风光储柴策略

策略名：

```text
OFF_GRID_DIESEL_BACKUP
```

适用：

- 无电网；
- 不允许下网；
- 不允许上网；
- 柴发作为储能之后的兜底电源；
- 重点关注缺供和柴发消耗。

### 7.1 离网模式的基本设置

```text
allow_grid_import = false
allow_grid_export = false
```

因此：

```text
P_grid_import = 0
P_grid_export = 0
```

### 7.2 分支 A：新能源富余或平衡

```text
P_renewable_to_load = P_dispatch_load
P_surplus = P_renewable_available - P_dispatch_load
```

富余新能源优先充储能：

```text
P_bess_charge = min(
    P_surplus,
    P_bess,
    (SOC_max * E_bess - E_bess_start) / eta_charge / dt_hours
)
```

更新储能：

```text
E_bess_end = E_bess_start + P_bess_charge * dt_hours * eta_charge
```

离网不能上网，剩余富余弃电：

```text
P_curtail = P_surplus - P_bess_charge
```

柴发不运行：

```text
P_diesel = 0
P_unserved_load = 0
```

### 7.3 分支 B：新能源不足

新能源全部供负荷：

```text
P_renewable_to_load = P_renewable_available
P_remaining_load = P_dispatch_load - P_renewable_available
```

储能优先放电：

```text
P_bess_discharge = min(
    P_remaining_load,
    P_bess,
    (E_bess_start - SOC_min * E_bess) * eta_discharge / dt_hours
)
```

更新储能：

```text
E_bess_end = E_bess_start - P_bess_discharge * dt_hours / eta_discharge
```

储能后剩余负荷：

```text
P_remaining_after_bess = P_remaining_load - P_bess_discharge
```

柴发补足：

```text
P_diesel = min(P_remaining_after_bess, P_diesel_rated) if diesel_enabled else 0
```

缺供：

```text
P_unserved_load = P_remaining_after_bess - P_diesel
```

离网不足分支中：

```text
P_grid_import = 0
P_grid_export = 0
P_curtail = 0
P_bess_charge = 0
```

### 7.4 离网可靠性指标

年度汇总时应计算：

```text
unserved_load_energy = sum(P_unserved_load * dt_hours)
unserved_load_rate = unserved_load_energy / total_load_energy
loss_of_load_hours = count(P_unserved_load > 0)
max_unserved_load_power = max(P_unserved_load)
diesel_generation_energy = sum(P_diesel * dt_hours)
diesel_share_of_load = diesel_generation_energy / total_load_energy
```

可行性判断可配置：

```text
unserved_load_energy <= allowed_unserved_energy
loss_of_load_hours <= allowed_loss_of_load_hours
```

初期建议默认：

```text
unserved_load_energy == 0
```

即离网方案不允许缺供，除非用户明确设置允许缺供。

## 8. 是否允许柴发给储能充电

这是未来必须慎重确认的口径。

### 8.1 初期建议：不允许

初期建议：

```text
diesel_to_bess_power = 0
grid_to_bess_power = 0
```

理由：

- 简化调度；
- 避免绿电口径污染；
- 保持“储能放电可视为此前富余新能源”的逻辑；
- 与当前 V0.1 基线一致。

### 8.2 如果未来允许柴发充储

必须增加储能来源分账：

```text
E_bess_green_start
E_bess_non_green_start
E_bess_green_end
E_bess_non_green_end
```

充电来源：

```text
P_bess_charge_from_renewable
P_bess_charge_from_diesel
P_bess_charge_from_grid
```

放电去向与来源：

```text
P_bess_discharge_green_to_load
P_bess_discharge_non_green_to_load
```

绿电自发自用只能计入：

```text
direct_renewable_to_load
+ bess_discharge_green_to_load
```

不能把柴油或电网充入储能后释放的电量计入绿电。

### 8.3 来源分账方法

可选：

1. FIFO：先充先放；
2. LIFO：后充先放；
3. 按比例混合；
4. 保守法：只要储能有非绿电混入，放电先按非绿电计。

初期如必须实现，建议采用“按比例混合”或“保守法”，并请专家确认。

## 9. 每小时台账建议字段

### 9.1 基础字段

```text
scenario_id
timestamp
hour_index
dt_hours
project_mode
dispatch_strategy
```

### 9.2 风光与负荷

```text
load_power
dispatch_load_power
pv_power
wind_power
pv_generation_power
wind_generation_power
renewable_generation_power
pv_station_use_power
wind_station_use_power
station_use_power
station_use_deficit_power
renewable_available_power
```

### 9.3 负荷供给来源

```text
renewable_to_load_power
bess_to_load_power
grid_to_load_power
diesel_to_load_power
unserved_load_power
```

### 9.4 储能

```text
bess_charge_power
bess_charge_from_renewable_power
bess_charge_from_grid_power
bess_charge_from_diesel_power
bess_discharge_power
bess_energy_start
bess_energy_end
soc_start
soc_end
bess_loss_power
```

当前基线中：

```text
bess_charge_from_grid_power = 0
bess_charge_from_diesel_power = 0
bess_charge_from_renewable_power = bess_charge_power
```

### 9.5 电网

```text
grid_import_power
grid_export_power
grid_exchange_power
grid_import_limited_shortfall_power
grid_export_limited_curtail_power
```

### 9.6 柴发

```text
diesel_power
diesel_generation_energy
diesel_fuel_consumption
diesel_fuel_cost
diesel_variable_om_cost
diesel_emission
diesel_running_flag
```

### 9.7 弃电与场景

```text
curtail_power
curtail_due_to_bess_full_power
curtail_due_to_export_limit_power
curtail_due_to_no_export_power
hour_case
constraint_flags
```

## 10. 每小时负荷平衡校验

每小时应满足：

```text
P_dispatch_load
= P_renewable_to_load
+ P_bess_discharge_to_load
+ P_grid_import
+ P_diesel
+ P_unserved_load
```

允许微小数值误差：

```text
abs(left - right) <= tolerance
```

如果未来区分用户负荷和站用电，应同时保留：

```text
P_dispatch_load = P_load + P_station_use_deficit
```

## 11. 每小时新能源去向校验

新能源正发电应满足：

```text
P_renewable_generation
= P_station_use_offset_by_renewable
+ P_renewable_to_load
+ P_bess_charge_from_renewable
+ P_grid_export_from_renewable
+ P_curtail
```

当前简化口径中，程序先用风光正发电抵扣站用电，然后只对净新能源做后续调度。因此也可校验：

```text
P_renewable_available
= P_renewable_to_load
+ P_bess_charge_from_renewable
+ P_grid_export
+ P_curtail
```

## 12. 每小时储能状态校验

当前基线：

```text
E_bess_end
= E_bess_start
+ P_bess_charge_from_renewable * dt_hours * eta_charge
- P_bess_discharge * dt_hours / eta_discharge
```

约束：

```text
SOC_min * E_bess <= E_bess_end <= SOC_max * E_bess
P_bess_charge <= P_bess
P_bess_discharge <= P_bess
not (P_bess_charge > 0 and P_bess_discharge > 0)
```

逐小时滚动：

```text
E_bess_start[t + 1] = E_bess_end[t]
SOC_start[t + 1] = SOC_end[t]
```

## 13. 每小时柴发校验

若柴发启用：

```text
0 <= P_diesel <= P_diesel_rated
```

若考虑最小稳定出力：

```text
P_diesel == 0 or P_diesel >= P_diesel_min
```

初期如果不考虑最小稳定出力，则 `P_diesel_min = 0`。

柴发电量：

```text
E_diesel = P_diesel * dt_hours
```

柴发不计入：

```text
total_renewable_generation
self_use_energy
green_load_rate numerator
self_use_rate numerator
```

除非未来定义“非绿电自发自用”指标，但必须与绿电指标分开。

## 14. 小时场景标签建议

当前已有风光储场景：

```text
GEN_BALANCED
GEN_SURPLUS_CHARGE_BESS
GEN_SURPLUS_DIRECT_EXPORT
GEN_SURPLUS_CHARGE_EXPORT
GEN_SURPLUS_CHARGE_EXPORT_CURTAIL
GEN_SURPLUS_CURTAIL
GEN_SHORT_GRID_IMPORT
GEN_SHORT_BESS_DISCHARGE
GEN_SHORT_BESS_DISCHARGE_AND_GRID_IMPORT
NO_RENEWABLE_GRID_IMPORT
```

加入柴发后建议新增：

```text
GEN_SHORT_DIESEL
GEN_SHORT_GRID_AND_DIESEL
GEN_SHORT_BESS_AND_DIESEL
GEN_SHORT_BESS_GRID_DIESEL
OFFGRID_DIESEL_SUPPLY
OFFGRID_BESS_DIESEL_SUPPLY
OFFGRID_UNSERVED_LOAD
```

小时标签只是主场景说明，详细约束原因仍应看字段：

```text
curtail_due_to_export_limit_power
grid_import_limited_shortfall_power
unserved_load_power
diesel_power
```

## 15. 年度汇总指标

### 15.1 技术指标

```text
total_load_energy = sum(load_power * dt_hours)
dispatch_load_energy = sum(dispatch_load_power * dt_hours)
total_renewable_generation = sum(renewable_generation_power * dt_hours)
renewable_to_load_energy = sum(renewable_to_load_power * dt_hours)
bess_discharge_to_load = sum(bess_to_load_power * dt_hours)
self_use_energy = renewable_to_load_energy + green_bess_discharge_to_load
grid_import_energy = sum(grid_import_power * dt_hours)
grid_export_energy = sum(grid_export_power * dt_hours)
curtail_energy = sum(curtail_power * dt_hours)
diesel_generation_energy = sum(diesel_power * dt_hours)
unserved_load_energy = sum(unserved_load_power * dt_hours)
```

在当前基线中：

```text
green_bess_discharge_to_load = bess_discharge_to_load
```

如果未来允许非绿电给储能充电，则必须改为：

```text
green_bess_discharge_to_load = sum(bess_discharge_green_to_load * dt_hours)
```

### 15.2 政策指标

```text
self_use_rate = self_use_energy / total_renewable_generation
green_load_rate = self_use_energy / total_load_energy
export_rate = grid_export_energy / total_renewable_generation
curtail_rate = curtail_energy / total_renewable_generation
grid_import_rate = grid_import_energy / total_load_energy
```

柴发相关：

```text
diesel_load_rate = diesel_generation_energy / total_load_energy
unserved_load_rate = unserved_load_energy / total_load_energy
```

### 15.3 储能指标

```text
bess_charge_energy = sum(bess_charge_power * dt_hours)
bess_discharge_energy = sum(bess_discharge_power * dt_hours)
bess_loss_energy = bess_charge_energy - bess_discharge_energy - (E_bess_end_final - E_bess_initial)
annual_equivalent_cycles = bess_discharge_energy / E_bess
final_soc = SOC_end[last_hour]
```

### 15.4 柴发经济和排放指标

```text
diesel_fuel_consumption_total = sum(diesel_fuel_consumption)
diesel_fuel_cost_total = sum(diesel_fuel_cost)
diesel_variable_om_cost_total = sum(diesel_variable_om_cost)
diesel_emission_total = sum(diesel_emission)
```

## 16. 可行性判断建议

### 16.1 并网风光储

默认要求：

```text
self_use_rate >= self_use_rate_min
green_load_rate >= green_load_rate_min
export_rate <= export_rate_max
unserved_load_energy == 0
```

如不允许上网：

```text
grid_export_energy == 0
```

### 16.2 并网加柴发

除并网风光储要求外，增加：

```text
diesel_generation_energy <= diesel_generation_limit 可选
unserved_load_energy == 0
```

柴发若只是备用，还可统计但不强制限制：

```text
diesel_running_hours
diesel_fuel_cost
```

### 16.3 离网风光储柴

默认要求：

```text
unserved_load_energy == 0
```

可选要求：

```text
renewable_share_of_load >= threshold
diesel_load_rate <= threshold
curtail_rate <= threshold
annual_equivalent_cycles <= threshold
```

离网没有上网，通常：

```text
grid_import_energy = 0
grid_export_energy = 0
```

## 17. 专家重点审查问题

请专家重点判断：

1. 当前“风光负值作为站用电”的口径是否合理；
2. 并网加柴发时，柴发是否应在电网之后兜底，还是可根据经济性提前运行；
3. 离网模式下“新能源 -> 储能 -> 柴发 -> 缺供”的初期策略是否合理；
4. 初期是否应禁止柴油给储能充电；
5. 如果允许柴发充储，采用哪种储能来源分账方法；
6. 柴发初期是否必须考虑最小稳定出力和启停约束；
7. 离网方案是否应默认不允许缺供；
8. 绿电自发自用率在柴发参与后是否仍按本文口径计算；
9. 每小时台账字段是否足以支持后续经济性、碳排和报告；
10. 哪些判断逻辑应作为硬约束，哪些应作为排序指标。

## 18. 初期实现建议

为了降低复杂度，建议第一版柴发扩展采用：

```text
1. 柴发独立资产；
2. 柴发只供负荷，不给储能充电；
3. 不考虑启停优化；
4. 不考虑最小运行时间；
5. 不考虑爬坡；
6. 油耗采用线性模型；
7. 离网优先级为新能源、储能、柴发、缺供；
8. 并网加备用优先级为新能源、储能、电网、柴发、缺供；
9. 柴发电量不计入绿电指标；
10. 所有结果进入统一逐小时台账。
```

该版本足以支撑前期方案筛选和专家复核。复杂柴发启停和经济调度可作为后续高级策略。

