# 产品打磨记录

## 记录原则

- 记录用户提出的问题和建议。
- 记录讨论后形成的产品决策。
- 标记状态：采纳、暂缓、拒绝、已完成。
- 说明原因，沉淀后续可复用的产品/工程经验。

## 当前版本的计算逻辑

本章节记录截至 2026-05-16 的当前版本计算口径，作为后续开发和复核的基准。

### 1. 输入数据口径

- 负荷曲线使用真实功率值，单位为万千瓦。
- 光伏曲线使用标幺值。
- 风电曲线使用标幺值。
- 光伏、风电标幺值允许出现负值。
- 光伏、风电负值不作为异常，也不自动截断。
- 光伏、风电大于 1 的标幺值允许参与计算，但 UI 会提示出现点数，供用户复核。
- 支持 8760 小时普通年和 8784 小时闰年。
- 三条曲线必须行数一致、时间戳一致。

### 2. 风光出力与站用电

每小时先根据容量计算风光原始出力：

```text
pv_power = pv_pu * pv_capacity
wind_power = wind_pu * wind_capacity
```

其中 `pv_power` 和 `wind_power` 可以为负。

当前版本将原始出力拆分为正发电出力和站用电：

```text
pv_generation_power = max(pv_power, 0)
wind_generation_power = max(wind_power, 0)

pv_station_use_power = max(-pv_power, 0)
wind_station_use_power = max(-wind_power, 0)

renewable_generation_power = pv_generation_power + wind_generation_power
station_use_power = pv_station_use_power + wind_station_use_power
```

每小时先用风光正发电抵扣站用电：

```text
net_renewable_power = renewable_generation_power - station_use_power
renewable_power = max(net_renewable_power, 0)
station_use_deficit_power = max(-net_renewable_power, 0)
```

解释：

- `renewable_generation_power` 是新能源总可用发电功率，用于统计新能源总可用发电量。
- `station_use_power` 是风光站用电功率。
- `renewable_power` 是抵扣站用电后的净新能源出力，用于后续供负荷、充储、上网。
- 如果站用电超过当小时风光正发电，则超出部分并入下网需求。

### 3. 负荷与下网需求

用户负荷功率为：

```text
load_power
```

实际参与电网平衡的负荷缺口口径为：

```text
dispatch_load_power = load_power + station_use_deficit_power
```

也就是说，当风光站用电无法由当小时风光正发电覆盖时，缺口会计入下网功率。

汇总中：

```text
total_load_energy = sum(load_power)
grid_import_energy = sum(grid_import_power)
grid_import_rate = grid_import_energy / total_load_energy
```

注意：

- `total_load_energy` 仍表示用户侧总用电量，不包含站用电。
- `grid_import_energy` 表示从电网下网电量，可能包含用户负荷缺口，也可能包含站用电缺口。

### 4. 储能调度逻辑

当前版本采用逐小时贪心调度策略，不做经济性优化。

当净新能源出力大于等于调度负荷时：

```text
direct_self_use = dispatch_load
surplus = renewable_power - dispatch_load
```

富余新能源优先给储能充电：

```text
bess_charge = min(
    surplus,
    bess_power * dt,
    (soc_max * bess_energy - bess_energy_start) / eta_charge
)
```

储能电量更新：

```text
bess_energy_end = bess_energy_start + bess_charge * eta_charge
```

储能充电后剩余电量进入上网或弃电判断。

当净新能源出力小于调度负荷时：

```text
direct_self_use = renewable_power
deficit = dispatch_load - renewable_power
```

储能优先放电：

```text
bess_discharge = min(
    deficit,
    bess_power * dt,
    (bess_energy_start - soc_min * bess_energy) * eta_discharge
)
```

储能电量更新：

```text
bess_energy_end = bess_energy_start - bess_discharge / eta_discharge
```

储能放电后剩余缺口由电网下网，若启用电网交换功率限制，则受该限制约束。

储能约束：

- 储能只能由富余新能源充电。
- 储能不能从电网充电。
- 储能不能同小时充电和放电。
- 储能不能放电上网。
- 储能放电只用于补足调度负荷缺口。
- SOC 逐小时滚动。
- SOC 不得低于 `soc_min`，不得高于 `soc_max`。
- 充放电受储能功率和容量约束。
- 充放电效率参与计算。

### 5. 上网比例硬约束

当前版本默认启用年度上网比例硬约束：

```text
export_control_mode = annual_cap_runtime
```

年度允许上网电量为：

```text
export_cap_energy = total_renewable_generation * export_rate_max
```

默认：

```text
export_rate_max = 20%
```

逐小时计算时累计上网电量：

```text
cumulative_export += grid_export
```

当年度累计上网电量未达到额度时，富余新能源可以上网。

当年度累计上网电量达到额度后，后续富余新能源不能再上网，只能弃电。

因此：

```text
export_rate = grid_export_energy / total_renewable_generation
```

在硬约束模式下，理论上不会超过 `export_rate_max`。

结果中单独记录：

```text
curtail_due_to_export_cap_energy
```

用于表示因年度上网比例额度用完导致的弃电量。

如果用户关闭年度硬约束，则进入后验校核模式：

```text
export_control_mode = post_check
```

该模式下逐小时先正常上网，最后检查：

```text
export_rate <= export_rate_max
```

若超过，则方案不达标。

### 6. 与电网交换功率限制

当前版本支持可选的“与电网交换功率限制”：

```text
grid_exchange_power_limit
```

默认值为 `null`，表示无限制。

用户勾选并输入限制值后，该限制同时作用于上网功率和下网功率。

#### 6.1 上网侧

上网功率不得超过交换功率限制：

```text
grid_export_power <= grid_exchange_power_limit
```

若富余新能源超过可上网功率，则超出部分弃电。

结果中记录：

```text
curtail_due_to_exchange_limit_power
curtail_due_to_exchange_limit_energy
```

#### 6.2 下网侧

下网功率也不得超过交换功率限制：

```text
grid_import_power <= grid_exchange_power_limit
```

当负荷缺口较大时，储能会优先放电降低下网功率。

如果储能能力不足，仍超过交换功率限制，则：

```text
grid_import_power = grid_exchange_power_limit
exchange_import_shortfall_power = 原始下网需求 - grid_exchange_power_limit
```

结果中记录：

```text
exchange_import_shortfall_power
exchange_import_shortfall_energy
```

出现下网缺口时，方案判定为不达标。

### 7. 自发自用与政策指标

新能源自发自用电量口径：

```text
self_use_energy = direct_self_use_energy + bess_discharge_to_load
```

其中：

- `direct_self_use_energy` 为净新能源直接供调度负荷电量。
- `bess_discharge_to_load` 为储能放电供调度负荷电量。
- 储能放电电量只来自此前富余新能源充电。

政策指标：

```text
self_use_rate = self_use_energy / total_renewable_generation
green_load_rate = self_use_energy / total_load_energy
export_rate = grid_export_energy / total_renewable_generation
curtail_rate = curtail_energy / total_renewable_generation
grid_import_rate = grid_import_energy / total_load_energy
```

默认达标条件：

```text
self_use_rate >= 60%
green_load_rate >= 30%
export_rate <= 20%
```

如果启用电网交换功率限制，还要求不能出现下网缺口。

### 8. 储能损耗与循环

储能损耗：

```text
bess_loss_energy
= bess_charge_energy
- bess_discharge_to_load
- (final_bess_energy - initial_bess_energy)
```

年等效循环次数：

```text
annual_equivalent_cycles = bess_discharge_to_load / bess_energy
```

若 `bess_energy = 0`，则循环次数为 0。

预计更换年份：

```text
replacement_year = cycle_life / annual_equivalent_cycles
```

若循环次数为 0，则为无穷大。

### 9. 当前版本不做的事项

当前版本不做经济性评价，包括：

- LCOE；
- IRR；
- NPV；
- 投资回收期；
- 电价优化；
- 储能套利；
- 现货市场收益。

当前版本也不做数学优化，只做批量枚举和逐小时技术测算。

## 当前版本计算流程图与场景说明

本章节把当前版本的计算逻辑整理成“流程图 + 场景表 + 公式说明”，用于人工复核、需求讨论和后续重构。

### 1. 总体流程图

```mermaid
flowchart TD
    A["开始：读取三条逐时曲线"] --> B["校验数据<br/>8760/8784 行<br/>时间戳一致<br/>列可识别"]
    B --> C["枚举方案组合<br/>光伏容量、风电容量、储能功率、储能时长"]
    C --> D["进入单个方案逐小时循环"]

    D --> E["计算风光原始出力<br/>pv_power = pv_pu * pv_capacity<br/>wind_power = wind_pu * wind_capacity"]
    E --> F["拆分正发电与站用电<br/>正值 = 发电<br/>负值 = 站用电"]
    F --> G["先用风光正发电抵扣站用电"]
    G --> H{"净新能源出力<br/>是否 >= 调度负荷？"}

    H -- 是 --> I["场景 A：新能源富余或平衡<br/>新能源先供负荷"]
    I --> J["富余新能源优先充储能<br/>受储能功率、容量、SOC 上限约束"]
    J --> K["剩余富余电量尝试上网"]
    K --> L{"是否受限制？<br/>年度上网额度<br/>电网交换功率<br/>是否允许上网"}
    L -- 否 --> M["上网"]
    L -- 是 --> N["超出部分弃电<br/>记录弃电原因"]
    M --> O["记录小时明细"]
    N --> O

    H -- 否 --> P["场景 B：新能源不足<br/>新能源全部直接供负荷"]
    P --> Q["储能优先放电供负荷<br/>受储能功率、容量、SOC 下限约束"]
    Q --> R["剩余缺口由电网下网"]
    R --> S{"是否启用电网交换功率限制<br/>且下网功率超限？"}
    S -- 否 --> O
    S -- 是 --> T["下网功率封顶<br/>记录下网缺口<br/>方案不达标"]
    T --> O

    O --> U{"是否还有下一小时？"}
    U -- 是 --> D
    U -- 否 --> V["汇总全年指标<br/>自发自用率、绿电占比、上网比例、弃电率、下网比例、储能循环"]
    V --> W["政策达标判断"]
    W --> X["输出方案汇总和逐小时明细"]
```

### 2. 每小时输入与中间变量

| 变量 | 含义 | 公式 / 说明 |
|---|---|---|
| `load_power` | 用户负荷功率 | 输入曲线，单位：万千瓦 |
| `pv_pu` | 光伏标幺值 | 输入曲线，可为负 |
| `wind_pu` | 风电标幺值 | 输入曲线，可为负 |
| `pv_power` | 光伏原始出力 | `pv_pu * pv_capacity`，可为负 |
| `wind_power` | 风电原始出力 | `wind_pu * wind_capacity`，可为负 |
| `pv_generation_power` | 光伏正发电功率 | `max(pv_power, 0)` |
| `wind_generation_power` | 风电正发电功率 | `max(wind_power, 0)` |
| `pv_station_use_power` | 光伏站用电功率 | `max(-pv_power, 0)` |
| `wind_station_use_power` | 风电站用电功率 | `max(-wind_power, 0)` |
| `renewable_generation_power` | 新能源总可用发电功率 | `pv_generation_power + wind_generation_power` |
| `station_use_power` | 风光站用电功率 | `pv_station_use_power + wind_station_use_power` |
| `net_renewable_power` | 抵扣站用电后的净新能源 | `renewable_generation_power - station_use_power` |
| `renewable_power` | 参与负荷平衡的净新能源功率 | `max(net_renewable_power, 0)` |
| `station_use_deficit_power` | 站用电缺口功率 | `max(-net_renewable_power, 0)` |
| `dispatch_load_power` | 调度口径负荷 | `load_power + station_use_deficit_power` |

解释：

- `renewable_generation_power` 用于统计新能源总可用发电量。
- `renewable_power` 用于逐小时能量平衡。
- 当风光负值产生站用电时，优先由当小时风光正发电抵扣。
- 如果站用电不能完全抵扣，缺口进入下网需求。

### 3. 场景 A：净新能源大于等于调度负荷

触发条件：

```text
renewable_power >= dispatch_load_power
```

处理流程：

```text
direct_self_use_power = dispatch_load_power
surplus_power = renewable_power - dispatch_load_power
```

储能充电：

```text
bess_charge_power = min(
    surplus_power,
    bess_power,
    (soc_max * bess_energy - bess_energy_start) / eta_charge / dt
)
```

储能电量更新：

```text
bess_energy_end = bess_energy_start + bess_charge_power * dt * eta_charge
```

储能充电后的富余电量：

```text
surplus_after_charge_power = surplus_power - bess_charge_power
```

之后进入上网与弃电判断。

#### 场景 A 的小时标签

| `hour_case` | 触发情况 | 处理逻辑 |
|---|---|---|
| `GEN_BALANCED` | 新能源刚好等于调度负荷 | 全部直接自用，无储能充放电，无上网弃电 |
| `GEN_SURPLUS_CHARGE_BESS` | 有富余新能源，且全部用于充储能 | 储能充电，剩余富余为 0 |
| `GEN_SURPLUS_DIRECT_EXPORT` | 有富余新能源，无储能充电，且全部上网 | 上网，不弃电 |
| `GEN_SURPLUS_CHARGE_EXPORT` | 富余新能源先充储，剩余上网 | 充储 + 上网，不弃电 |
| `GEN_SURPLUS_CHARGE_EXPORT_CURTAIL` | 富余新能源先充储，部分上网，部分弃电 | 充储 + 上网 + 弃电 |
| `GEN_SURPLUS_CURTAIL` | 富余新能源不能上网或上网受限，剩余弃电 | 弃电 |

说明：

- 当前 `hour_case` 是主场景标签。
- 具体弃电原因需要结合以下字段复核：
  - `curtail_due_to_export_cap_power`
  - `curtail_due_to_exchange_limit_power`
  - `curtail_power`

### 4. 上网与弃电判断

富余电量在充储后尝试上网。

如果不允许上网：

```text
grid_export_power = 0
curtail_power = surplus_after_charge_power
```

如果允许上网，则先考虑电网交换功率限制：

```text
exchange_export_limit_power =
    grid_exchange_power_limit if configured else infinity
```

再考虑最大上网功率限制。当前 UI 暂不暴露单独的最大上网功率限制，但底层保留 `export_power_max`：

```text
export_power_limit =
    min(exchange_export_limit_power, export_power_max or infinity)
```

年度上网比例硬约束下：

```text
annual_export_cap_energy = total_renewable_generation * export_rate_max
remaining_export_cap_energy = annual_export_cap_energy - cumulative_export_energy
```

每小时实际上网：

```text
grid_export_energy = min(
    surplus_after_charge_energy,
    export_power_limit * dt,
    remaining_export_cap_energy
)
```

弃电：

```text
curtail_energy = surplus_after_charge_energy - grid_export_energy
```

因年度上网比例额度导致的弃电：

```text
curtail_due_to_export_cap_energy =
    max(export_before_annual_cap_energy - grid_export_energy, 0)
```

因电网交换功率限制导致的弃电：

```text
curtail_due_to_exchange_limit_energy =
    max(surplus_after_charge_energy - min(surplus_after_charge_energy, exchange_limit_energy), 0)
```

解释：

- 年度上网比例硬约束决定“全年最多能上网多少电量”。
- 电网交换功率限制决定“每小时最多能上网多少功率”。
- 两者都可能导致弃电。

### 5. 场景 B：净新能源小于调度负荷

触发条件：

```text
renewable_power < dispatch_load_power
```

处理流程：

```text
direct_self_use_power = renewable_power
deficit_power = dispatch_load_power - renewable_power
```

储能放电：

```text
bess_discharge_power = min(
    deficit_power,
    bess_power,
    (bess_energy_start - soc_min * bess_energy) * eta_discharge / dt
)
```

储能电量更新：

```text
bess_energy_end = bess_energy_start - bess_discharge_power * dt / eta_discharge
```

储能放电后的原始下网需求：

```text
raw_grid_import_power = deficit_power - bess_discharge_power
```

若未启用电网交换功率限制：

```text
grid_import_power = raw_grid_import_power
exchange_import_shortfall_power = 0
```

若启用电网交换功率限制：

```text
grid_import_power = min(raw_grid_import_power, grid_exchange_power_limit)
exchange_import_shortfall_power =
    raw_grid_import_power - grid_import_power
```

如果 `exchange_import_shortfall_power > 0`，说明即使储能已放电，系统仍无法在电网交换功率限制下满足负荷，该方案不达标。

#### 场景 B 的小时标签

| `hour_case` | 触发情况 | 处理逻辑 |
|---|---|---|
| `NO_RENEWABLE_GRID_IMPORT` | 无净新能源，且储能不放电 | 负荷由电网下网 |
| `GEN_SHORT_GRID_IMPORT` | 新能源不足，储能不放电 | 新能源直接供一部分负荷，剩余下网 |
| `GEN_SHORT_BESS_DISCHARGE` | 新能源不足，储能放电后完全覆盖缺口 | 新能源 + 储能满足调度负荷 |
| `GEN_SHORT_BESS_DISCHARGE_AND_GRID_IMPORT` | 新能源不足，储能放电后仍需下网 | 新能源 + 储能 + 电网下网 |

说明：

- 若启用电网交换功率限制，仍需查看 `exchange_import_shortfall_power`。
- 出现下网缺口时，小时标签仍可能是 `GEN_SHORT_BESS_DISCHARGE_AND_GRID_IMPORT`，但方案汇总会记录缺口并判为不达标。

### 6. 储能状态滚动

每小时开始：

```text
soc_start = bess_energy_start / bess_energy
```

每小时结束：

```text
soc_end = bess_energy_end / bess_energy
```

下一小时：

```text
soc_start[t + 1] = soc_end[t]
```

无储能方案：

```text
bess_power = 0
bess_energy = 0
bess_charge_power = 0
bess_discharge_power = 0
soc_start = 0
soc_end = 0
```

### 7. 程序考虑的约束场景汇总

| 约束场景 | 触发条件 | 程序处理 | 记录字段 |
|---|---|---|---|
| 风光负值 | `pv_power < 0` 或 `wind_power < 0` | 按站用电处理 | `pv_station_use_power`、`wind_station_use_power` |
| 站用电超过正发电 | `station_use_power > renewable_generation_power` | 超出部分进入下网需求 | 体现在 `grid_import_power` |
| 储能充电功率受限 | `surplus_power > bess_power` | 充电功率不超过 `bess_power` | `bess_charge_power` |
| 储能充电容量受限 | SOC 接近上限 | 充电不超过剩余可充空间 | `soc_end`、`bess_energy_end` |
| 储能放电功率受限 | `deficit_power > bess_power` | 放电功率不超过 `bess_power` | `bess_discharge_power` |
| 储能放电容量受限 | SOC 接近下限 | 放电不低于 `soc_min` | `soc_end`、`bess_energy_end` |
| 年度上网比例额度用完 | 累计上网达到 `export_cap_energy` | 后续富余新能源弃电 | `curtail_due_to_export_cap_power` |
| 上网交换功率受限 | 富余电力超过 `grid_exchange_power_limit` | 超出部分弃电 | `curtail_due_to_exchange_limit_power` |
| 下网交换功率受限 | 缺口超过 `grid_exchange_power_limit` | 储能先放电，仍不足则记录下网缺口 | `exchange_import_shortfall_power` |
| 不允许上网 | `allow_export = false` | 富余电力弃电 | `curtail_power` |
| 无储能方案 | `bess_power = 0` 或 `bess_energy = 0` | 不充不放，SOC 为 0 | `bess_*` 字段为 0 |

### 8. 汇总指标公式

| 指标 | 公式 | 解释 |
|---|---|---|
| `total_load_energy` | `sum(load_power * dt)` | 用户总用电量，不含站用电 |
| `total_renewable_generation` | `sum(renewable_generation_power * dt)` | 风光正发电总量 |
| `pv_station_use_energy` | `sum(pv_station_use_power * dt)` | 光伏站用电 |
| `wind_station_use_energy` | `sum(wind_station_use_power * dt)` | 风电站用电 |
| `station_use_energy` | `pv_station_use_energy + wind_station_use_energy` | 风光站用电合计 |
| `direct_self_use_energy` | `sum(direct_self_use_power * dt)` | 新能源直接供调度负荷 |
| `bess_discharge_to_load` | `sum(bess_discharge_power * dt)` | 储能放电供调度负荷 |
| `self_use_energy` | `direct_self_use_energy + bess_discharge_to_load` | 新能源自发自用电量 |
| `grid_import_energy` | `sum(grid_import_power * dt)` | 下网电量 |
| `grid_import_rate` | `grid_import_energy / total_load_energy` | 下网电量占用户总用电量比例 |
| `grid_export_energy` | `sum(grid_export_power * dt)` | 上网电量 |
| `export_rate` | `grid_export_energy / total_renewable_generation` | 上网比例 |
| `export_cap_energy` | `total_renewable_generation * export_rate_max` | 年度允许上网电量 |
| `curtail_energy` | `sum(curtail_power * dt)` | 弃电量 |
| `curtail_rate` | `curtail_energy / total_renewable_generation` | 弃电率 |
| `curtail_due_to_export_cap_energy` | `sum(curtail_due_to_export_cap_power * dt)` | 因年度上网额度导致的弃电 |
| `curtail_due_to_exchange_limit_energy` | `sum(curtail_due_to_exchange_limit_power * dt)` | 因交换功率上限导致的弃电 |
| `exchange_import_shortfall_energy` | `sum(exchange_import_shortfall_power * dt)` | 因下网交换功率限制导致的供电缺口 |
| `bess_charge_energy` | `sum(bess_charge_power * dt)` | 储能充电电量 |
| `bess_loss_energy` | `bess_charge_energy - bess_discharge_to_load - (final_bess_energy - initial_bess_energy)` | 储能损耗 |
| `annual_equivalent_cycles` | `bess_discharge_to_load / bess_energy` | 年等效循环次数 |

### 9. 达标判断

方案达标需要满足：

```text
self_use_rate >= self_use_rate_min
green_load_rate >= green_load_rate_min
export_rate <= export_rate_max
```

如果不允许上网：

```text
grid_export_energy == 0
```

如果启用电网交换功率限制：

```text
exchange_import_shortfall_energy == 0
```

不达标原因可能包括：

- 自发自用率不足；
- 绿电占用电比例不足；
- 上网比例超限；
- 不允许上网但出现上网；
- 最大上网功率超限；
- 电网交换功率限制导致下网缺口。

## 2026-05-16 UI 与复核体验优化

### 1. 储能时长选项中的 0 不直观

用户反馈：

- “储能时长为什么要有个 0？我没搞懂。”

讨论结论：

- `0` 的技术含义是“无储能方案”，用于生成纯风光基准方案。
- 但业务用户不应被迫理解这个编码。
- UI 应改为“包含无储能方案”勾选框，默认选中。
- 储能时长选项只展示真实储能时长，如 `2,4`。

状态：已完成。

经验：

- UI 中的特殊数值编码要转译成业务语言，避免让用户猜系统内部约定。

### 2. 自动识别时间列和数值列

用户反馈：

- 输入文件用户通常已经处理好。
- 软件至少应自动识别时间列，另一个数值列自动作为负荷/光伏/风电数值列。
- 不应要求用户每次手动选择。

讨论结论：

- 优先识别时间列名：`时间`、`timestamp`、`time`、`日期时间` 等。
- 排除时间列后，如果只有一个候选数值列，自动使用。
- 只有存在多个候选列或无法识别时，才显示手动选择。

状态：已完成。

经验：

- 能自动识别的输入，不要强迫用户手动操作。
- 手动选择应作为兜底，而不是主流程。

### 3. 批量测算需要进度条

用户反馈：

- 已经有方案数量预估，应在测算过程中用进度条显示当前进度。

讨论结论：

- 批量运行器增加进度回调。
- UI 显示 `已完成 / 总方案数` 和当前方案编号。

状态：已完成。

经验：

- 长耗时任务必须有过程反馈，否则用户无法判断程序是否卡住。

### 4. 数据状态与数据质量提示

用户反馈：

- 除方案数量外，应显示数据加载状态，例如负荷/光伏/风电各有多少小时。
- 对光伏标幺值大于 1 的情况，应提示数量。
- 但本阶段不要自动处理输入曲线，例如小负值不应被软件自动截断。

讨论结论：

- UI 增加数据状态面板，展示行数、时间范围、编码、数值异常提示。
- 保留“大于 1”提示。
- 小负值不再自动截断为 0，本阶段直接报错，由用户在外部处理数据。

状态：已完成。

经验：

- 技术测算软件应帮助用户确认“传入的数据是什么”，但不应在未经用户明确授权时修改输入数据。

### 5. 结果筛选和排序不足

用户反馈：

- “只看达标方案”不够。
- 至少应支持按绿电占比、弃电率、自发自用率、上网比例排序。
- 应支持按方案类型筛选：无储能、纯光伏、纯风电、光储、风储等。
- 勾选和排序应是 AND 关系。

讨论结论：

- 筛选条件之间采用 AND 关系。
- 排序只改变当前筛选结果的显示顺序。
- 增加方案类型筛选。

状态：已完成。

经验：

- 结果表不是只给机器看的输出，还要支持人的复核路径。

### 6. 补充下网电量与下网电量比例

用户反馈：

- 已有负荷总用电量，但缺少下网电量和下网电量比例。
- 电量单位使用万千瓦时，不保留小数。
- CSV 暂时可继续打磨，后续希望输出阅读体验更好的格式。

讨论结论：

- 下网电量等同当前 `grid_import_energy`。
- 新增更直观字段：
  - `grid_import_rate = grid_import_energy / total_load_energy`
- UI 展示中电量按万千瓦时、不保留小数格式化。
- CSV/Excel 格式化输出体验后续继续打磨。

状态：已完成。

经验：

- 输出字段既要满足算法口径，也要贴近业务复核语言。

### 7. 持续更新产品打磨记录

用户反馈：

- 问题解决或用更好的方案解决后，应及时更新 `PRODUCT_POLISH_LOG.md`。

讨论结论：

- 本文档作为产品打磨决策记录持续维护。
- 每轮 UI/算法口径讨论后更新状态。

状态：采纳，进行中。

经验：

- 产品打磨过程本身是可复用资产，可为未来 skill 设计提供素材。

### 8. Codex 内置浏览器中无法下载方案汇总 Excel

用户反馈：

- 在 Codex 中运行程序，方案汇总 Excel 无法下载。

初步判断：

- 当前全局下载按钮位置靠后，可能被大表格和逐小时明细淹没。
- Streamlit rerun 或临时目录生命周期也可能影响下载体验。

讨论结论：

- 将方案汇总 Excel 和全部逐小时 ZIP 下载按钮提前到汇总区。
- 生成下载文件时使用稳定的内存字节，不依赖用户点击后临时文件仍存在。
- 保留单方案 CSV 下载在明细区域。

状态：已完成。

解决方案：

- 下载按钮已移动到汇总指标下方、结果表上方。
- Excel 和 ZIP 下载数据在按钮渲染前转为稳定的内存字节，避免临时目录生命周期影响点击下载。
- 单方案 CSV 下载仍保留在逐小时明细区域。

验证记录：

- `python -m pytest` 通过，44 个测试全部通过。
- 使用干净模拟数据导出 `outputs/scenario_summary_20260516_175415.xlsx`，文件大小 11440 字节。

## 2026-05-16 风光负值曲线与站用电口径修正

### 1. 风电/光伏标幺曲线负值不应视为异常

用户反馈：

- 风电、光伏曲线出现负值是正常的。
- 可理解为新能源电源在不发电时需要用电。
- 这些负值应正常参与计算，并统计到风、光的“站用电”列。

修正结论：

- 风电/光伏标幺曲线负值不再报错，也不自动截断。
- 每小时将风光出力拆分为：
  - 原始出力：`pv_power`、`wind_power`，可为负；
  - 正发电出力：`pv_generation_power`、`wind_generation_power`；
  - 站用电：`pv_station_use_power`、`wind_station_use_power`；
  - 合计站用电：`station_use_power`。
- 调度逻辑为：
  - 先用当小时风光正发电抵扣站用电；
  - 抵扣后的净新能源再供用户负荷、充储、上网；
  - 如果站用电超过当小时正发电，缺口计入下网电量。
- 汇总新增：
  - `pv_station_use_energy`
  - `wind_station_use_energy`
  - `station_use_energy`

状态：已完成。

验证记录：

- `python -m pytest` 通过，46 个测试全部通过。

经验：

- 数据“负值”不一定是错误，技术软件必须先理解业务含义。
- 对输入数据的处理策略应区分“异常数据清洗”和“业务口径计算”。

## 2026-05-16 电网交换功率限制与运行服务重启问题

### 1. Streamlit 旧进程导致新代码未生效

用户反馈：

- 页面测算时报错：`run_batch() got an unexpected keyword argument 'progress_callback'`。

判断：

- 源码中的 `run_batch` 已经包含 `progress_callback` 参数。
- 报错说明当前浏览器连接的 Streamlit 服务仍在使用旧版本代码。
- 仅刷新浏览器不一定能让旧 Python 进程加载新代码，尤其是服务启动在代码修改之前。

结论：

- 修改代码后，应先停止旧 Streamlit 进程，再重新启动。

状态：已说明，待用户按重启步骤验证。

经验：

- 本地 Web 工具调试时，浏览器刷新和服务进程重启是两个动作。

### 2. 新增“与电网交换功率限制”

用户需求：

- 上网政策约束中增加“与电网交换功率限制”。
- 默认无限制。
- 用户勾选并输入值后，系统逐时不得出现下网功率或上网功率超过该值。
- 触及上网限制时，新能源需要弃电。
- 触及下网限制时，应尽量通过储能放电降低下网功率。

实现结论：

- 新增政策参数：`grid_exchange_power_limit`。
- UI 中新增：
  - `设置与电网交换功率限制`
  - `与电网交换功率限制（万千瓦）`
- 上网侧：
  - `grid_export_power` 不超过限制；
  - 超出部分计入 `curtail_power`；
  - 同时记录 `curtail_due_to_exchange_limit_power` 和汇总 `curtail_due_to_exchange_limit_energy`。
- 下网侧：
  - 储能按原有规则优先放电降低下网；
  - 若储能能力不足，`grid_import_power` 封顶在限制值；
  - 未满足部分记录为 `exchange_import_shortfall_power` 和汇总 `exchange_import_shortfall_energy`；
  - 出现下网缺口时方案不达标，原因包含“电网交换功率限制导致下网缺口”。

状态：已完成。

验证记录：

- `python -m pytest` 通过，50 个测试全部通过。

经验：

- “强约束”既要限制结果不越界，也要记录限制造成的代价。
- 上网受限的代价是弃电；下网受限且储能不足的代价是供电缺口，应单独展示并判定方案不可行。

## 2026-05-16 批量上传与导入路径稳定性

### 1. UI 代码更新但参数模型仍是旧版本

用户反馈：

- 仍然报错：`PolicyParams.__init__() got an unexpected keyword argument 'grid_exchange_power_limit'`。

判断：

- UI 页面已经显示新版内容，但导入 `green_direct.models.params` 时可能拿到了环境中旧的已安装包，而不是当前项目 `src` 下的源码。
- 原因是 Streamlit 执行脚本时，`sys.path` 未必总是把项目 `src` 放在第一位。

解决方案：

- 在 `src/green_direct/ui/app.py` 顶部强制把项目 `src` 路径插入 `sys.path` 第一位。
- 避免 UI 文件使用当前源码，而模型/批量/算法模块却混入旧包。

状态：已完成，需重启 Streamlit 后生效。

经验：

- 本地项目若采用 `src/` 布局，Streamlit 脚本入口要显式保证源码路径优先。
- 否则容易出现“页面是新的，导入模块是旧的”的错配问题。

### 2. 批量上传并按文件名自动识别曲线类型

用户建议：

- 数据上传区域希望能一次选择多个文件。
- 软件根据文件名自动识别：
  - 含 `负荷`、`load`、`用电` 的文件作为负荷曲线；
  - 含 `光伏`、`pv`、`solar` 的文件作为光伏标幺曲线；
  - 含 `风电`、`wind` 的文件作为风电标幺曲线。

实现方案：

- 增加“批量上传曲线 CSV”入口，支持一次选择多个 CSV。
- 自动按文件名关键字分配到负荷、光伏、风电。
- 若识别失败或识别冲突，给出提示。
- 保留单独上传入口作为人工覆盖。

状态：已完成。

经验：

- 上传入口应优先支持真实用户的一次性操作习惯。
- 自动识别必须保留人工覆盖，避免文件名不规范时卡死流程。

## 2026-05-16 储能放电上网口径与性能优化

### 1. 储能默认不能放电上网

用户问题：

- 当前计算逻辑是否存在储能放电上网的场景？
- 方案汇总表是否统计储能放电量？
- 默认应为储能不能放电上网。

核查结论：

- 当前调度逻辑不存在储能放电上网。
- 储能只在 `renewable_power < dispatch_load_power` 时放电。
- 储能放电用于补足调度负荷缺口。
- 当 `renewable_power >= dispatch_load_power` 时，储能只可能充电，不会放电。
- 汇总表中的储能放电字段是 `bess_discharge_to_load`，含义为“储能放电供负荷电量”。

加固措施：

- 在“当前版本的计算逻辑”中明确写入“储能不能放电上网”。
- 新增测试：`test_bess_discharge_never_exports_to_grid`，确保储能放电时 `grid_export_energy = 0`。

状态：已完成。

### 2. 批量计算和界面筛选速度优化

用户反馈：

- 计算速度不到 120 个方案/分钟。
- 汇总表生成较慢但还能接受。
- 一旦按规则筛选，界面变灰并长时间等待。
- 未来方案数量可能达到成千上万条。

问题定位：

- 单方案逐小时计算使用 pandas `iterrows()`，每个方案 8760/8784 次逐行构造 dict，性能较低。
- UI 在每次筛选/排序时会重新生成 Excel 和全部逐小时 ZIP 下载数据。
- UI 每次筛选时会对完整结果表做字符串格式化并渲染，方案数大时卡顿明显。

已完成优化：

- 单方案计算改为 NumPy 数组预分配 + 索引循环，避免 `iterrows()` 和逐行 dict append。
- 下载文件使用 `st.session_state` 缓存，只在新测算结果产生后准备一次。
- 筛选/排序时不再重复生成 Excel/ZIP。
- 方案类型从逐行 `apply` 改为向量化赋值。
- 结果表默认只显示筛选后的前 500 行，用户可调整最多显示行数。

状态：已完成第一轮优化。

后续可选优化：

- 批量测算时先只保留汇总表，不保存所有方案逐小时明细。
- 用户点击某个方案后，再按需重算该方案逐小时明细。
- 对大批量方案使用多进程并行。
- 将核心逐小时循环进一步迁移到 `numba` 或 Cython。
- 将结果表分页，避免一次渲染上万行。

验证记录：

- `python -m pytest` 通过，51 个测试全部通过。

经验：

- 大批量技术测算要区分“批量筛选所需数据”和“单方案复核所需明细”。
- UI 卡顿不一定来自计算本身，下载文件准备、全表格式化和全表渲染也可能是主要瓶颈。

经验：

- 下载入口应靠近结果汇总，并使用稳定的数据载体，减少 UI rerun 对下载的影响。

## 2026-05-16 建立软件总览与接口文档

用户问题：

- 当前 V0.1 技术测算模块准备先告一段落。
- 后续还要开发图表制作、经济性评价、报告等下游模块。
- 虽然希望各模块保持独立，但需要一份软件介绍或接口说明，保证后续模块能接得上。

产品判断：

- 需要建立一份稳定的“系统总览 + 模块接口契约”文档。
- `PRODUCT_POLISH_LOG.md` 继续记录产品打磨和决策过程。
- 新文档应放在 `docs/` 下，作为后续模块开发的基线，而不是混在过程日志里。

已完成：

- 新增 `docs/SOFTWARE_OVERVIEW_AND_INTERFACE.md`。
- 文档内容覆盖：
  - 软件定位与当前边界；
  - 总体架构和模块依赖方向；
  - 标准输入数据契约；
  - 参数模型、方案模型、单方案仿真、批量测算、导出接口；
  - 当前计算口径；
  - 汇总结果和逐小时明细字段；
  - 图表、经济性、报告模块接入建议；
  - 接口稳定性规则；
  - 测试与运行基线。

状态：已完成。

经验：

- 当一个模块即将成为其他模块的上游时，需要把“当前口径”从讨论日志中提炼成接口契约。
- 过程日志适合记录为什么这么做，接口文档适合记录后续必须怎么接。

## 2026-05-19 架构重定向：从批量枚举工具到方案策划推荐平台

### 1. 用户对对标软件的判断

用户提供了一组“绿电直连 / 微电网项目策划平台”的对标截图。经过讨论后形成判断：

- 对标软件真正有价值的不是 UI 表象，而是背后的项目策划工作流；
- 用户不希望软件只是枚举大量风光储容量组合，然后展示一张巨大的结果表；
- 枚举仍然可以作为内部搜索手段，但前台应展示经过筛选、排序、解释的几个代表性方案；
- 图表、报告和后续分析应围绕推荐方案展开，而不是围绕全部枚举方案展开；
- AI 助手短期内不是重点。

状态：采纳。

### 2. 新的产品方向

项目方向从：

```text
绿电直连风光储多方案批量测算工具
```

调整为：

```text
绿电直连 / 微电网项目方案策划与推荐平台
```

新的主流程应为：

```text
项目输入
-> 输入审查
-> 生成候选方案池
-> 技术仿真
-> 政策合规筛选
-> 经济性排序
-> 代表方案推荐
-> 图表、报告、导出
```

状态：采纳。

### 3. 经济性排序提前进入

用户提出：在枚举方案基础上至少有两个约束或排序维度：

1. 是否满足政策要求，包括自发自用、上网、绿电占比；
2. 经济性排序。

讨论结论：

- 经济性应提前进入推荐逻辑；
- 但第一阶段不必做完整财务评价；
- 可先实现轻量经济性排序，用于方案筛选和推荐；
- 完整 NPV、IRR、多年现金流、税费、融资等可后续扩展；
- 经济性评价必须读取技术仿真结果，不应反向改变技术调度。

状态：采纳，待设计实现。

### 4. 柴油发电进入方案逻辑

用户提出：加入柴发后，方案计算模块可更好适配离网场景；并网模式下接柴发较少但也存在，不冲突。

讨论结论：

- 柴发应作为明确资产建模，而不是混入电网下网；
- 柴发需要独立出力、油耗、成本、排放和运行状态字段；
- 离网、并网、并网加备用应作为项目模式或调度策略表达；
- 柴发调度策略需要专门研究；
- 柴发是否允许给储能充电是关键口径问题，初期建议谨慎处理；
- 如果未来允许非新能源给储能充电，必须做能源来源追踪，避免污染绿电指标。

状态：采纳，待专家审查。

### 5. 约束文档更新

用户担心旧 `AGENTS.md`、`CLAUDE.md` 和 V0.1 文档会限制后续开发。

讨论结论：

- 当前项目文件夹继续使用；
- 现有 V0.1 内核和测试作为基线保留；
- 旧 V0.1 文档不删除，但不再作为最终产品边界；
- 更新 `AGENTS.md` 和 `CLAUDE.md`，允许经济性排序、柴发、离网、推荐引擎等后续方向；
- 新增专家审查材料目录：`notes/architecture_reframe_20260519/`。

状态：已完成。

新增文档：

- `notes/architecture_reframe_20260519/01_EXPERT_REVIEW_BRIEF.md`
- `notes/architecture_reframe_20260519/02_TARGET_ARCHITECTURE_AND_CALCULATION_LOGIC.md`
- `notes/architecture_reframe_20260519/03_MIGRATION_AND_POLISH_PLAN.md`

更新文档：

- `AGENTS.md`
- `CLAUDE.md`
- `ROADMAP.md`

### 6. 后续开发经验

- 旧代码和旧文档不一定是负担，关键是把它们降级为“基线资产”，而不是继续作为未来边界。
- 架构调整前先更新 agent 指令文件，否则后续 Codex / Claude Code 很容易按旧规则开发。
- 推荐引擎应先独立于 UI 做出来，避免把产品逻辑写死在 Streamlit 页面里。
- 柴发和经济性都不应直接塞入现有函数，而应通过资产模型、调度策略、经济评价层逐步进入。

## 2026-05-19 切换电脑前补充：图表模块降级为可替换原型

### 1. 用户对当前图表模块的判断

用户反馈：

- 当前已经开发出来的图表模块很不理想；
- 甚至可以丢弃；
- 现阶段不应继续围绕图表模块投入主要精力；
- 应优先把方案逐时计算、风光储规模配置逻辑、简化经济性排序逻辑等搞清楚并实现。

讨论结论：

- 现有图表模块降级为早期原型，不作为近期重点资产；
- 后续开发可以替换或重做图表模块；
- 图表和报告应等核心计算、推荐、经济性排序稳定后再重新设计；
- 近期重点转为：
  1. 逐小时能量平衡和能源台账；
  2. 风光储规模配置 / 候选方案生成；
  3. 政策合规筛选；
  4. 轻量经济性排序；
  5. 代表方案推荐。

状态：采纳。

经验：

- 图表不是底层架构，不应让不满意的展示模块牵制核心计算和推荐逻辑。
- 技术软件应先把“算得对、筛得清、推荐得有理由”做好，再打磨可视化。

## 2026-05-21 经济性评价 V1 口径确认

用户和 AI 讨论后确认：经济性模块可以进入代码实现，但必须先按 V1 简化年度现金流口径落地，不引入贷款和复杂财务模型。

### 1. 模型定位

- V1 是不考虑贷款的项目投资现金流模型，不计算还本付息、资本金 IRR 或复杂融资结构。
- 年度现金流详表是主输出，FNPV、FIRR、静态回收期、动态回收期必须能追溯到年度明细。
- Year 0 为建设期，发生初始投资现金流出；运营期默认 25 年，各年收入、成本、税费和储能更换默认在年末发生。
- FIRR 不使用用户输入折现率；折现率只用于 FNPV、折现净现金流和动态回收期。
- 经济性评价只读取技术 `summary` / `hourly_detail`，不改变逐小时调度、SOC、上网、下网、弃电或储能充放电结果。

### 2. 已确认默认输入

| 输入项 | 默认值 | 口径 |
|---|---:|---|
| 运营期 | 25 年 | 风电、光伏整体按同一运营期处理 |
| 风电单位造价 | 4500 元/kW，含税 | 乘 `wind_capacity` |
| 光伏单位造价 | 2500 元/kW，含税 | 需提示与光伏曲线容量基准匹配 |
| 储能单位造价 | 900 元/kWh，含税 | 乘 `bess_energy` |
| 其他固定资产投资 | 0 万元，含税 | 可选 |
| 建设投资进项税率 | 10% | 可改 |
| 风电运维成本 | 50 元/kW/年 | 无进项税 |
| 光伏运维成本 | 25 元/kW/年 | 无进项税 |
| 储能运维成本 | 18 元/kW/年 | 按 `bess_power`，无进项税 |
| 上网电价 | 0.25 元/kWh，含税 | 产生销项税 |
| 自发自用电价 | 0.40 元/kWh，含税 | 产生销项税；提示不含过网费 |
| 储能更换投资比例 | 50% | 按初始储能投资比例 |
| 储能更换进项税率 | 13% | 外购设备材料 |
| 销项税率 | 13% | 电费收入拆税 |
| 城建税地区 | 县城、镇 5% | 可选市区 7%、其他 1% |
| 企业所得税率 | 25% | 可选 15% 或自定义 |
| 折现率 | 6% | 用于 FNPV、动态回收期 |

### 3. 税费和现金流口径

- 用户输入的投资、电价、收入和成本默认是含税金额。
- 利润表使用不含税收入、不含税成本、折旧、附加税费和企业所得税。
- 现金流表使用实际含税现金收付，并单独扣减实际缴纳增值税、附加税费和企业所得税。
- 建设投资进项税在 Year 0 形成留抵，进入运营期后有销项再抵扣。
- 运行成本简化为内部运维，不考虑进项税。
- 储能更换属于外购设备材料，发生当年产生进项税，可抵扣或形成留抵。
- 进项税不直接作为现金流入，只通过减少实际缴纳增值税或形成留抵体现。

### 4. 储能更换口径

- 储能更换由循环寿命达到时间触发，建议使用 `replacement_year` 或 `annual_equivalent_cycles` 推导。
- 更换现金流出 = 初始储能投资含税金额 × 更换投资比例。
- 更换当年计算可抵扣进项税。
- 后续储能更换不计算残值，不计算旧电池处置。原“储能更换不追加折旧”口径已被 2026-05-23 新口径取代：储能更换作为运营期新增可折旧投资，从更换次年至运营期最后一年线性折旧，残值 0。
- 若更换触发在运营期最后一年或之后，例如默认 25 年项目到第 25 年才触发，则默认不再更换。

### 5. 其他经营收入

- 其他经营收入支持多项输入，单位为万元/年，含税。
- 支持发生规则：每年、前 20 年、前 25 年、指定年份。
- 允许输入负值。负值默认不产生进项税，作为经营性收入抵减或额外经营性支出进入现金流。

### 6. 文档精简

用户不希望项目文档继续膨胀。本轮将 `docs/references/economic_evaluation/` 精简为：

- `00_README_使用说明.md`
- `经济性评价V1计算口径_合并版.md`
- `99_官方来源清单.md`

旧的分章节草稿已合并进权威合并版。后续经济性口径变化优先更新合并版和本日志，避免新增平行文档。

状态：V1 口径已确认。

### 7. 初版实现记录

本轮已完成经济性 V1 的第一版代码实现：

- 新增 `src/green_direct/economy/economic_inputs.py`，定义 `EconomicParams` 和 `OtherOperatingRevenueItem`；
- 新增 `src/green_direct/economy/economic_evaluator.py`，实现单方案和批量年度现金流评价；
- 输出年度现金流明细表和 FNPV、FIRR、静态投资回收期、动态投资回收期等指标；
- 实现 Year 0 建设投资留抵、运营期增值税抵扣、附加税、企业所得税、20 年直线折旧、储能更换现金流和进项税；
- 储能更换若触发在运营期最后一年或之后，默认不更换；
- 运行成本进项税为 0；
- 其他经营收入负值不产生进项税；
- 在 Streamlit 结果区加入轻量“经济性评价 V1”试用入口，可输入参数、查看经济性汇总和单方案年度明细并导出 Excel。

验证记录：

- `pytest` 通过，83 个测试全部通过。

后续建议：

- 用户先用 V1 入口试算几个典型方案，重点检查年度现金流详表、增值税留抵和储能更换年份；
- 暂不把经济性排序强行并入推荐组合，等用户确认 V1 现金流表可信后再接推荐引擎；
- 当前 UI 入口只是试用入口，后续 UI 大改时应围绕推荐方案和用户加入对比方案重做。

## 2026-05-21 浏览器批注：UI 主流程和信息层级问题

用户在 Streamlit 试用页做了一组浏览器批注。核心判断是：当前 UI 仍然像“把所有中间表摊开给用户看的技术调试页”，不符合实际方案策划工作流。主界面应该把展示位留给重点信息，表格和明细更多作为下载或高级复核入口。

### 1. 已确认的 UI 问题

- 原始枚举结果表过于繁杂，主界面不应默认展示纯大表。
- 下载方案总表、下载全部逐小时明细、方案类型筛选、排序方式、显示行数、逐小时方案详表等应默认收起，由用户勾选或展开后出现。
- 数据状态不应默认展示详细表格，应先给颜色和一句话结论，详情点击展开。
- 逐小时明细不适合在软件中直接大表查看，应只提供 CSV 下载。
- 经济性年度现金流详表不需要默认展示，应提供下载按钮，并确保与其他模块接口衔接。
- UI 表头应使用中文名，英文原名默认隐藏；点击展开后可查看中文名和英文原名对应关系。该对应关系必须全局统一。
- 图表模块现阶段效果差，后续应只围绕默认推荐方案和用户指定加入对比的方案制图，而不是围绕全量枚举表制图。
- 当前标题仍带 “V0.1 批量测算工具”，与新的方案策划平台方向不一致。

### 2. 计算速度判断

用户反馈计算速度慢，并询问多线程/并行是否能提速。当前判断：

- Python 多线程对 CPU 密集型逐小时仿真不一定有效，受 GIL 影响较大。
- 多进程并行理论上能提速，但要处理 Windows/Streamlit 下进程启动、数据复制、进度回调、错误收集和内存占用。
- 更优先的性能方向是区分“批量筛选所需汇总”和“少数方案复核所需逐小时明细”：批量阶段可先只保留汇总和推荐所需明细，用户查看或导出指定方案时再按需生成逐小时明细。
- 后续可再评估多进程、Numba 或更深的向量化。

### 3. 本轮低风险 UI 收纳

本轮先做不影响底层计算的 UI 收纳：

- 数据状态改为一句话结论 + 详情展开。
- 方案总表下载、全部逐小时 ZIP、筛选排序、行数设置、结果大表、单方案逐小时 CSV 下载收进“高级：结果表、筛选与下载”。
- 取消 UI 中直接展示逐小时明细大表，仅提供当前方案逐小时 CSV 下载。
- 当前方案逐小时 CSV 下载改用中文表头。
- 经济性年度现金流明细不再默认展示，仅提供经济性结果 Excel 下载。
- 新增统一 UI 字段中文名映射，用于表格显示和用户侧下载；英文原名通过“字段对应关系”展开查看。
- 页面标题改为“绿电直连风光储方案策划与测算平台”。

### 4. 后续 UI 重构方向

后续 UI 不应继续沿着“输入 -> 全量枚举大表 -> 用户自己找结果”的结构发展。更合理的工作流是：

```text
项目输入
-> 数据诊断一句话结论
-> 候选方案计算
-> 政策筛选和经济性评价
-> 推荐方案组合
-> 用户加入指定方案对比
-> 围绕少数方案展示图表、年度经济性、逐小时审查和导出
```

对标软件参考图可继续放在 `samples/对标软件/小红书/` 下作为视觉和工作流参考，但实现时应优先保证计算口径和推荐逻辑稳定。

## 2026-05-21 图表模块重构：对标参考图的第一版方案图谱

用户再次批注确认：旧“图表分析 / 单方案诊断”模块不适合继续修补，核心问题不是缺少几张图，而是用户不知道当前看的是哪个方案，且图表没有围绕实际方案策划流程组织。

本轮按 `samples/对标软件/小红书/` 的参考图先重做 Streamlit 图表入口，但只作为展示层读取 `BatchResult.summary`、`BatchResult.hourly_details` 和经济性 V1 结果，不修改调度、政策或经济性计算口径。

### 已调整

- 将旧“单方案诊断 / 典型日 / 热力图 / 储能与电网 / 多方案对比”结构替换为“方案图谱”结构。
- 系统先自动选取少数代表方案：推荐方案、高消纳备选、低弃电备选、低储能备选。
- 用户可手动加入指定方案参与图表对比，满足“想看心目中方案差在哪里”的需求。
- 图表区顶部明确显示“当前图表对应方案”，避免不知道当前页面对应哪个 `scenario_id`。
- 已实现四个可用页签：
  - 方案总览：代表方案卡片、当前方案关键指标、多方案雷达图；
  - 能量流向：新能源发电构成环图、年度能源流向 Sankey；
  - 运行时序：四季典型日 24h 运行策略图、折叠的 8760h 曲线；
  - 经济性分析：读取经济性 V1 汇总，展示 FNPV、FIRR、回收期和多方案经济性对比。
- 图表模块现在会读取 `st.session_state["economy_v1_result"]`，经济性图表和推荐优先级可在计算经济性后联动。

### 暂不强行实现

- 参考图中的碳排放页需要确认电网排放因子、柴油/备用电源边界和碳减排口径，当前 V1 暂不生成。
- 经济敏感性分析需要确认敏感变量、扰动幅度和是否重算年度现金流，当前先不伪造。
- 这次只重构展示层，后续推荐引擎仍应抽到独立模块，不要把推荐规则长期写死在 UI。

验证记录：

- `python -m py_compile src/green_direct/visualization/chart_ui.py src/green_direct/ui/app.py` 通过。
- `pytest` 通过，83 个测试全部通过。

## 2026-05-21 项目文件夹清理记录

用户提出项目文件夹体量过大、文档和生成物积累过多，需要做一次彻底清理和梳理。清理前已先提交 Git 检查点：

```text
535ee78 Checkpoint before repository cleanup
```

### 已清理

- 删除可再生打包产物和缓存：
  - `release/`
  - `dist/`
  - `build/`
  - `outputs/`
  - `.pytest_cache/`
  - 各级 `__pycache__/`
- 删除本地编辑器状态目录 `.obsidian/`。
- `.gitignore` 增加 `.obsidian/` 和 `outputs/`，避免本地状态和导出文件再次进入版本库。
- 删除旧图表模块讨论稿和提示词文档：
  - `docs/PRD_CHART_MODULE.md`
  - `docs/CHART_MODULE_CONTRACT.md`
  - `docs/CHART_MODULE_DEMO_GUIDE.md`
  - `docs/CODEX_START_PROMPT_CHART_MODULE.md`
  - `docs/CODEX_TASK_CHART_MODULE.md`
  - `notes/CHART_MODULE_AI_PROMPT.md`
- 删除历史导出样例文件：
  - `outputs/config_snapshot_20260516_120000.json`
  - `outputs/hourly_detail_S0001_20260516_120000.csv`
  - `outputs/hourly_details_20260516_120000.zip`
  - `outputs/scenario_summary_20260516_120000.xlsx`
  - `outputs/scenario_summary_20260516_175415.xlsx`

### 已保留

- `src/`、`tests/`、`docs/references/economic_evaluation/`、`notes/architecture_reframe_20260519/`、`samples/` 均保留。
- V0.1 基线文档继续保留，作为回归和口径参考。
- `samples/对标软件/` 保留，作为 UI / 图表 / 工作流对标参考。

### 梳理结果

- README 已更新为当前“方案策划与测算平台”定位。
- 用户快速指南已更新为当前 UI：高级结果下载、经济性 V1、方案图谱。
- 项目根目录最大体量从打包产物主导转为少量源码、样例和文档，后续清理重点不再是大文件，而是继续压缩重复文档和把权威口径集中到少数文件中。

## 2026-05-22 经济性 V1：FIRR 多次变号误判修复

用户在 Streamlit 页面检查经济性汇总时发现：部分方案 FNPV 为正、静态/动态回收期也可计算，但 FIRR 为空，状态提示“现金流存在多次变号或变号结构不稳定”。复核年度现金流后确认，这类方案通常是 Year 0 建设投资为负、运营期为正、储能更换年份短暂转负、后续再转正。多次变号会带来多重 IRR 风险，但不必然意味着 IRR 不可计算。

本次修复口径：
- FIRR 不再因现金流多次变号而直接返回空值；
- 先扫描 NPV 曲线并定位 IRR 根；
- 如果仅找到一个稳定根，正常返回 FIRR；
- 如果找到多个 IRR 解、没有有效正负现金流、或找不到稳定求解区间，才返回“IRR 无法可靠计算”状态。

已同步更新经济性 V1 计算口径文档，并新增测试覆盖“储能更换造成临时现金流转负但只有唯一 IRR 根”和“确实存在多个 IRR 根”两类情况。

验证记录：
- `python -m pytest tests\test_economy_v1.py` 通过，13 个测试全部通过。
- `python -m pytest` 通过，85 个测试全部通过。

## 2026-05-22 经济性 V1：储能更换寿命口径更新

用户补充确认：集中式储能站不应只按循环寿命判断电池更换，V1 应引入电池日历寿命，默认 15 年。储能更换时间取循环寿命与日历寿命先到者；每次更换后循环次数和日历寿命重新开始计算。

本次更新口径：
- `EconomicParams` 新增 `bess_calendar_life_years`，默认 15 年；
- 储能更换年份由 `min(循环寿命 / 年等效循环次数, 日历寿命)` 推导；
- 更换后按同一寿命间隔继续滚动触发，运营期最后一年及之后触发的更换默认不发生；
- 经济性汇总保留 `bess_replacement_operation_year` 作为首次更换年，并新增 `bess_replacement_operation_years` 和 `bess_replacement_count`；
- Streamlit 经济性参数区新增“储能电池日历寿命（年）”输入，默认 15 年。

该变化会影响 FNPV、FIRR、静态/动态回收期和年度现金流明细。尤其是原来循环寿命在 20 年以后才触发的储能方案，现在通常会在第 15 年发生更换。

## 2026-05-22 UI 数值显示格式统一

用户检查页面时提出：网站中表格、图表的小数位应统一；电量单位均为万千瓦时，显示时不需要保留小数；百分比最多保留 2 位小数。

本次调整：
- 新增统一显示格式工具，表格显示层对电量类字段保留 0 位小数、比例/FIRR/SOC 保留 2 位百分比、金额和回收期保留 2 位小数；
- 经济性汇总表增加方案类型、光伏容量、风电容量、储能容量，便于判断 FIRR 不可计算是否来自无新能源/无储能或无有效投资现金流方案；
- 方案图谱、经济性图表、能量流向图、旧图表构建器的坐标轴和部分悬浮提示同步使用统一格式；
- 下载文件仍保留原始数值，避免显示格式影响后续复核和二次分析。

## 2026-05-22 经济性 V1：IRR 状态解释和方案总表导出调整

用户指出前一轮对“现金流缺少有效正负变号”的解释不准确。复现默认样例后确认：这类方案主要是“仅储能、无光伏、无风电”方案，而不是无储能方案。当前基线储能不能从电网充电，也没有新能源给储能补能，项目有储能投资和运维成本，但没有形成正向净现金流，因此现金流全为非正值，IRR 没有定义。

本次调整：
- FIRR 状态文案拆分为“现金流全为0”“现金流全为非正值，项目没有形成正向净现金流”“现金流全为非负值，项目缺少初始投资流出”，避免笼统提示“缺少有效正负变号”；
- 经济性汇总表默认隐藏到高级折叠区，不再作为主输出；
- 经济性测算完成后，方案总表 Excel 下载会在原方案总表后追加 `*_economy` 经济性字段，保持一个方案总表文件；所选方案年度现金流仍可在高级区单独下载；
- 显示格式按用户要求改为：百分比 1 位小数，万元金额 0 位小数，回收期 1 位小数，容量/功率若为整数则不显示小数、若有小数则最多显示 2 位。

验证记录：
- `python -m pytest tests\test_economy_v1.py tests\test_export.py tests\test_visualization_smoke.py tests\test_ui_import.py` 通过。
- `python -m pytest` 通过，89 个测试全部通过。

## 2026-05-22 候选方案生成：排除无绿电来源方案

用户进一步确认：无风也无光的组合不应作为绿电直连/微电网规划候选方案。即使配置了储能，在当前基线策略下储能只能由富余新能源充电，不能从电网充电；没有风电或光伏来源时，方案既没有绿电来源，也会污染后续经济性、筛选和推荐结果。

本次调整口径：
- 在 `generate_scenarios` 候选方案生成层直接跳过 `pv_capacity <= 0` 且 `wind_capacity <= 0` 的组合；
- 因此批量候选池不再包含“无新能源无储能方案”和“仅储能方案”；
- 底层单方案仿真器仍可用于手工构造极端回归工况，避免破坏 V0.1 技术基线测试能力；
- Streamlit 方案数量预估为 0 时，提示至少需要配置光伏或风电容量。

## 2026-05-22 项目文件夹瘦身：历史资料降级归档

用户在准备搭建推荐引擎前，确认希望先处理项目文件夹瘦身问题。讨论后形成判断：当前文件夹的主要问题不是大文件体量，而是活文档、历史快照、AI 构建提示词、软著材料和对标资料混在活跃路径里，容易干扰后续开发判断。

本次处理原则：
- 重要产品和计算口径继续沉淀到 `notes/PRODUCT_POLISH_LOG.md`，这是项目最重要的长期记忆文件之一；
- 历史资料采用“降级归档”而不是直接删除，避免丢失早期构建脉络；
- V0.1 基线文档继续保留在根目录，作为算法回归和口径复核资产；
- 软著资料暂不整理，继续保留原位置，不作为后续开发参考入口；
- 推荐引擎模块本轮不讨论、不实现，避免把文件夹整理和新业务模块混在一起。

已归档到 `archive/20260522_historical_build_materials/`：
- `prompts/` 早期 AI 分阶段构建提示词；
- `REVIEW_REPORT.md`、`ACCEPTANCE_CHECKLIST.md`、`PROJECT_STRUCTURE.md`；
- `docs/DISPATCH_CORE_STATUS_V0_2.md`；
- `docs/AI_HANDOFF_DISPATCH_STRATEGY_ROADMAP.md`；
- `docs/CODEX_RESTRAINED_REVIEW_PROMPT_GRID_CONNECTED_ECONOMY.md`。

已清理：
- `.pytest_cache/`；
- `src/` 和 `tests/` 下的 `__pycache__/`；
- `outputs/` 下的运行日志，保留 `outputs/.gitkeep`。

后续经验：
- 新增一次性提示词、评审草稿或状态快照时，应优先放入 `archive/` 或 `docs/review/` 等明确非活跃路径；
- 当前活跃开发入口仍以 `AGENTS.md`、`CLAUDE.md`、`notes/HANDOFF_FOR_NEW_MACHINE.md`、`docs/SOFTWARE_OVERVIEW_AND_INTERFACE.md`、`notes/PRODUCT_POLISH_LOG.md` 和架构重定向文档为主；
- 等推荐引擎第一版落地后，再考虑把架构重定向材料提炼成更短的 `docs/ARCHITECTURE.md`，不要在推荐引擎开工前做大规模文档合并。

## 2026-05-22 推荐引擎讨论：先区分投资主体结构

用户在准备推荐引擎前纠正了一个关键前提：绿电直连项目不能只用单一“经济最优”口径排序，必须先区分项目投资主体结构。

当前形成的领域判断：
- 同一主体结构：电源和负荷属于同一投资主体或同一经济决策边界，绿电直连更像增量投资经济性分析，关注新增投资相对于基准用能方案带来的全局收益最大化；
- 不同主体结构：电源侧和负荷侧是两个主体，应拆开看收益。电源侧投资方关注风、光、储和接入线路等资产投资收益；负荷侧用户关注用了多少绿电、绿电结算价格相对电网购电价格的变化，以及可选的绿证、碳相关或其他环境权益收益；
- 当前经济性 V1 更接近电源侧投资方视角，而不是同一主体全局增量收益或负荷侧收益；
- 绿证、碳相关收益暂不强行命名为“碳税”等固定术语，先作为可选的“环境权益收益 / 环境价值收益”高级参数，后续再按适用政策和用户场景精确定义。

已新增 `CONTEXT.md`，记录 `Project Investment Structure`、`Single-Entity Structure`、`Two-Entity Structure`、`Power-Side Investor`、`Load-Side User`、`Incremental Green Direct Power Investment`、`Environmental-Value Benefit` 等术语。

后续推荐引擎不应把所有项目都压成一个排序口径。推荐入口应先识别或让用户选择主体结构，再决定经济性视角和推荐标签。

补充修正：
- 推荐引擎默认入口不要求用户先选择投资主体结构；
- 系统默认应给出多视角推荐组合，把同一主体全局增量收益、电源侧投资收益、负荷侧用能 / 环境价值收益等视角下值得看的方案都列出来；
- 针对某一特定视角查看最优、次优、次次优方案，应作为高级的“按推荐视角专项排序”能力；
- 第 1 类同一主体全局增量收益和第 3 类负荷侧收益是重要工作，第一版推荐引擎可以先预留模型和标签位置，但不得在文档和代码结构中遗忘。

推荐标签术语补充：
- “高消纳”一词过于模糊，后续推荐标签不应单独使用；
- 应拆分为“高自发自用方案”（最大化 `self_use_rate`）、“高绿电占比方案”（最大化 `green_load_rate`）和“低弃电方案”（最小化 `curtail_rate`）；
- 低弃电不等于高自发自用，但在绿电直连默认上网比例不超过 20% 的政策约束下，两者高度相关，不能用“通过大量上网降低弃电”来解释二者差异；
- 更准确的差异是：高自发自用关注新能源最终供给负荷的比例；低弃电关注可用新能源没有被浪费的比例。即使上网受限，储能损耗、年末 SOC、允许上网额度内的上网电量、不同容量组合导致的可发电量分母变化，仍可能让两个标签选出不同方案；
- 第一版推荐组合应加入“政策达标最小投资方案”：在满足政策和可行性约束的方案中，选择初始建设投资最低的方案。该方案对同一主体、电源侧和负荷侧都有参考价值。

第一版默认推荐组合草案：
1. 同一主体全局增量收益方案：先预留席位，后续建立相对基准供能方案的增量收益口径；
2. 电源侧投资收益最佳方案：第一版可使用当前经济性 V1 结果，默认按电源侧 FIRR 优先筛选，FNPV 和回收期作为辅助展示 / tie-break 指标；
3. 负荷侧收益方案：先预留席位，后续补充绿电结算价格、负荷侧电网购电基准价格和可选环境权益收益；
4. 政策达标最小投资方案：满足政策和可行性约束下初始建设投资最低；
5. 高绿电占比方案：`green_load_rate` 最高；
6. 高自发自用方案：`self_use_rate` 最高；
7. 低弃电方案：`curtail_rate` 最低；
8. 低储能方案：先作为可选 / 辅助标签保留，后续通过实际推荐结果观察是否常与最小投资方案重合，再决定是否占默认席位。

政策达标最小投资方案口径：
- 第一版投资口径可使用经济性 V1 的建设期现金流出 `construction_cash_outflow`，但经济性 V1 需要补充独立的送出线路工程投资字段；
- 送出线路工程投资不能长期归入“其他固定资产投资”，因为它是绿电直连项目的刚性建设边界之一，通常随电源与负荷 / 接入点距离显著变化；
- 送出线路工程投资和其他固定资产投资均在 Year 0 建设期发生；
- “其他固定资产投资”仍可保留为用户输入的杂项总额，用于升压、计量、通信、管理用设施等未单列项目，但不应吞掉送出线路这一关键成本驱动项。
- 第一版送出线路工程投资输入方式确定为：用户直接输入“送出线路工程投资总额（万元，含税）”，暂不展开线路长度、单位造价、电压等级、架空 / 电缆等细项；
- Year 0 全部初始投资中可抵扣增值税的部分统一按 10% 建设投资进项税率计，包括风电、光伏、储能、送出线路工程投资和其他固定资产投资。

价格口径预留：
- 当前经济性 V1 中，上网电价和自发自用电价按全年平均固定价格计算，这是第一版简化，不应写死为长期边界；
- 后续电源侧收益应支持 8760 逐小时上网结算价格和自发自用结算价格；
- 负荷侧收益应支持固定电网购电价格作为第一版简化，并预留 8760 逐小时甚至 15min 电网购电价格曲线；
- 这些价格曲线应作为经济性和推荐层读取的时序价格输入，不应反向改变当前基线技术调度。若未来引入按电价优化储能充放电，必须作为新的显式调度策略另行命名。

电源侧排序口径补充：
- 用户确认第一版电源侧投资收益最佳方案更倾向以 FIRR 作为默认主排序指标；
- 原因是绿电直连尚不是成熟稳定模式，特别是在不同主体结构下，电源侧投资方通常更关注快速收回投资和项目抗风险能力；
- FNPV 仍应保留展示，并可作为 FIRR 接近时的辅助排序指标，但不作为默认主指标。
- 已确认第一版排序链：先筛政策达标且 FIRR 可可靠计算的方案；主排 FIRR 从高到低；辅助排序依次为静态回收期更短、动态回收期更短、FNPV 更高。

## 2026-05-23 经济性 V1：补充送出线路工程投资

用户确认：绿电直连项目的送出线路工程投资是 Year 0 建设期必需成本，不能长期混入“其他固定资产投资”。第一版直接由用户输入“送出线路工程投资总额（万元，含税）”，暂不拆分线路长度、单位造价、电压等级、架空 / 电缆等细项。

本次实现：
- `EconomicParams` 新增 `dedicated_connection_line_investment_with_vat`；
- 经济性 V1 建设投资现金流出新增送出线路工程投资；
- Year 0 初始投资可抵扣增值税继续统一按建设投资进项税率计算，默认 10%；
- 年度现金流新增 `dedicated_connection_line_depreciation`，按 20 年直线折旧并与风电、光伏、储能、其他固定资产折旧并列；
- 经济性汇总保留 `dedicated_connection_line_investment_with_vat`，便于推荐引擎和报告读取；
- Streamlit 经济性参数区新增“送出线路工程投资（万元，含税）”输入，并在经济性汇总表展示。

验证记录：
- `python -m pytest tests\test_economy_v1.py tests\test_ui_import.py` 通过，18 个测试全部通过。
- `python -m pytest` 通过，90 个测试全部通过。

## 2026-05-23 推荐与经济性口径继续澄清

### 1. 折旧口径

用户再次澄清折旧原则：
- Year 0 初始投资统一按 20 年、残值 0、直线法折旧；
- 运营期发生的新增可折旧投资，从发生年度的下一年开始，到运营期最后一年线性折旧，残值 0；
- 该口径会影响储能更换：储能更换当年仍作为现金流出并产生进项税，折旧从更换次年开始至运营期最后一年。

本次实现：
- 年度现金流新增 `bess_replacement_depreciation`；
- 储能更换折旧计入利润总额和所得税计算；
- 更新经济性 V1 口径文档，删除“储能更换不追加折旧”的旧口径。

验证记录：
- `python -m pytest tests\test_economy_v1.py tests\test_ui_import.py` 通过，19 个测试全部通过；
- `python -m pytest` 通过，91 个测试全部通过。

### 2. 运营期与光伏衰减

当前软件默认风电、光伏、储能经济评价运营期为 25 年。用户提出后续可考虑让用户分别定义风电、光伏运营期，但如果风光运营期不同，会导致 Year 21 以后自发自用、上网、弃电等技术电量不再等同于前 20 年，进而需要多年逐时或多年年度技术结果。

当前判断：
- 第一版不建议在方案遍历技术仿真中引入光伏组件线性衰减；
- 可在后续经济性或高级参数中预留年度发电衰减 / 年度电量修正口径；
- 若未来允许风电、光伏运营期不同，不能只改现金流年限，还必须定义不同年份技术电量如何变化；
- 储能经济评价运营期可先跟随项目最长运营期。

依据参考：
- NREL 资料显示，光伏组件常见退化通常缓慢，研究中位退化率约 0.5%/年，但不同气候、系统和组件条件下会变化；
- IEA PVPS Task 13 资料也将组件退化和寿命评估作为长期发电量预测问题，而不是必须混入每一次容量组合遍历的硬约束。

因此第一版可暂不在候选方案遍历中考虑光伏衰减，但需要在报告中说明“技术仿真使用代表年出力，不含逐年组件衰减”；后续可在经济性 V2 中通过年度衰减系数修正收入和电量。

### 3. CSV / Excel 优先原则

用户补充底层原则：有些数据处理如果在 CSV 或 Excel 表中更方便、更清晰、更可审查，就不必强行放进网页 UI。后续新增输入、参数推导或数据清洗功能时，必须先判断该逻辑适合放在网页控件中，还是更适合由用户在模板表中准备。

已同步到 `AGENTS.md` 和 `CONTEXT.md`。

### 4. 推荐模型席位优先级

用户确认第一版推荐组合的默认优先级：
1. 同一主体 FIRR 最优；
2. 电源侧 FIRR 最优；
3. 负荷侧综合用能收益最优（2026-05-24 修正：负荷侧不承担初始投资时不计算 FIRR）；
4. 工程代表方案：从政策达标最小投资、高绿电占比、高自发自用、低弃电中选一个，默认低弃电。

前三个席位是经济主体视角；第四个席位是工程特征视角。第一版同一主体和负荷侧可以先预留席位与接口，但不得在推荐模型中遗忘。

### 5. 推荐的下一步节奏

当前不建议继续扩散讨论或直接大规模实现推荐引擎。建议节奏：
1. 先把经济性 V1 当前状态作为 git checkpoint，保存送出线路工程投资、储能更换折旧、推荐席位和 CSV / Excel 优先原则；
2. 暂不开放风电、光伏分别设置运营期，继续采用项目统一默认运营期 25 年；
3. 方案遍历技术仿真暂不考虑光伏逐年衰减，继续使用代表年 8760 / 8784 结果；后续可在经济性 V2 中增加年度衰减系数，对收入和电量做年度修正；
4. 推荐引擎第一版应开独立小分支，实现独立 `recommendation/` 模块，先不碰调度；
5. 把 `visualization/chart_ui.py` 中临时代表方案选择逻辑迁移到推荐模块；
6. 推荐组合先实现可计算席位，不能完整计算的同一主体 FIRR 和负荷侧综合用能收益席位先保留结构、状态和说明。

## 2026-05-24 推荐席位计算口径与价格曲线草案

用户补充确认：负荷侧不承担新增初始投资时，不应把负荷侧推荐席位命名为“负荷侧 FIRR 最优”。该席位应改为“负荷侧综合用能收益最优”或“负荷侧节费最优”，核心比较绿电直连自发自用电量相对电网购电的节费，并可叠加用户自定义的环境价值收益。

已形成推荐席位口径草案，沉淀到：

- `docs/references/recommendation_engine/推荐引擎V1计算口径草案.md`

当前推荐组合口径修正为：

1. 同一主体 FIRR 最优：按绿电直连相对基准供能方案的增量投资收益分析，主排序 FIRR；
2. 电源侧 FIRR 最优：沿用当前经济性 V1 的电源侧投资收益视角，主排序 FIRR；
3. 负荷侧综合用能收益最优：负荷侧无初始投资时不算 FIRR，主排序年度综合用能收益或节费；
4. 工程代表方案：默认低弃电，可切换政策达标最小投资、高绿电占比、高自发自用。

负荷侧固定价口径暂定为：

```text
负荷侧年度综合用能收益 =
  self_use_energy
  * (
      grid_purchase_price_with_vat
      - green_power_settlement_price_with_vat
      + environmental_value_per_kwh
    )
```

其中环境价值收益作为高级选项在 V1 预留并可实现，默认值为 0；暂不强行命名为绿证、碳税或碳减排收益。两部制电价 V1 暂不计算，默认容量电费不因方案变化。

价格术语纠偏：

- 当前代码中的 `self_use_price_with_vat` 在推荐语境中更准确应称为“绿电结算价”：电源侧看作收入，负荷侧看作购电成本，同一主体下不能作为内部收入重复计算；
- 负荷侧和同一主体还需要补充“电网购电价格”输入，用于计算节省购电成本；
- 上网电价、绿电结算价、电网购电价格应在推荐 V1 支持 8760 / 8784 逐时曲线；15min 曲线后续再支持；
- 价格曲线只作为经济性和推荐层输入，不反向改变当前基线技术调度。

当时未决问题，随后已部分确认：

1. 是否正式将 UI 和文档中的“自发自用电价”统一改名为“绿电结算价”；
2. 同一主体 FIRR 中，节省购电成本的增值税和所得税处理如何简化；
3. 环境价值高级选项是否同时进入同一主体席位和负荷侧席位，还是 V1 先只进入负荷侧；
4. 逐时价格曲线第一版是否只接受 CSV/Excel 模板上传。

补充确认：

- 正式将“自发自用电价”重命名为“绿电结算价”，计算字段统一使用 `green_power_settlement_price_with_vat`。现有 `self_use_price_with_vat` 只能作为迁移期旧字段，不应作为推荐引擎的长期计算字段；
- UI 中可以解释“绿电结算价”就是自发自用绿电的结算电价；
- 所有推荐席位默认先在政策达标候选集中排序，政策不达标方案不参与默认推荐，只进入诊断或失败原因说明；
- 环境价值高级选项采用固定单价 `environmental_value_per_kwh`，暂不设计时间价值曲线；
- 环境价值高级选项适用于同一主体席位和负荷侧席位，但实际项目中负荷侧通常不一定能享受，必须由用户显式启用，默认 0；
- 逐时价格曲线第一版支持 8760 / 8784 小时，后续再支持 15min；
- 价格曲线模板必须采用 CSV/Excel 上传，不做网页逐项录入。对于这类呆板、重复、表格化的数据准备，网页逐项录入不符合项目的输入边界原则；
- 负荷侧综合用能收益不必只做固定价。由于它本质上是逐时自发自用电量与价差的加权求和，V1 可以直接支持固定价和 8760 / 8784 曲线两种模式。

此前剩余未决问题集中在同一主体 FIRR 的税费口径：自发自用少购电是否应体现少取得购电增值税进项、是否存在内部结算销项税、节省购电成本在所得税现金流中如何简化处理。2026-05-25 已形成 V1 税前简化口径，见下一节。

## 2026-05-25 同一主体购电节费与税前 FIRR 口径确认

用户提供《绿电直连同一主体购电节费与税费简化建模说明_讨论沉淀稿》后，复核确认：该算法可以在当前项目基础上实现，且不改变现有风光储技术调度逻辑。它应作为独立的“同一主体税前增量现金流模型”进入经济性和推荐层，不应混入当前 `evaluate_scenario_economy()`。

已沉淀文档：

- `docs/references/recommendation_engine/同一主体购电节费与税前FIRR口径.md`

关键结论：

- 同一主体合并口径下，内部绿电结算价不是项目整体新增收益来源，不参与同一主体 FIRR；
- 自发自用收益来自少向外部电网购电形成的净节费；
- 不能直接用总电费除以总电量计算 FIRR 节费；V1 默认用外部购电净成本单价，或按电费清单中的电能量/市场购电价格、上网环节线损费用、系统运行费用、输配电价、政府性基金及附加组价，并对含税项目价税分离；
- 同一主体 V1 主排序采用税前 FIRR，不默认计算所得税；
- 价格曲线模板在项目内不需要 `load_kwh`，因为自发自用电量来自技术仿真的 `hourly_detail`；
- 当前项目支持 8760 / 8784 小时输入，15min 后续需要同步扩展 `TimeParams.supported_hours`、输入校验、UI 和导出。

与现有经济性 V1 的边界：

- 现有经济性 V1 仍保留为电源侧投资收益模型；
- 同一主体模型应新增 `electricity_saving.py` / `single_entity_evaluator.py` 等独立模块；
- 当前代码中的 `self_use_price_with_vat` 长期应迁移为 `green_power_settlement_price_with_vat`，但同一主体模型不使用该字段计算整体收益；
- 同一主体税前 FIRR 建议使用扣除可抵扣增值税后的投资和成本基准，同时保留含税现金支出作为辅助展示；若未来要模拟真实含税现金流与增值税留抵，应作为高级税务现金流模型。

## 2026-05-25 同一主体税前 FIRR 第一版实现

本次进入推荐引擎 V1 的第一段实现，先完成“同一主体 FIRR 最优”席位需要的底层经济性评价，不直接实现 UI 推荐卡片。

实现边界：

- 新增 `AvoidedGridPurchaseParams`，只承载同一主体可复用的外部购电节费参数。默认使用一个固定值 `net_avoided_grid_cost_price`；组价模式才使用电能量/市场购电价格、上网环节线损费用、系统运行费用、输配电价、政府性基金及附加、购电增值税率等字段；
- 新增 `electricity_saving.py`，用于计算被替代外部购电净成本单价、自发自用节费、环境价值和上网不含税收入；
- 新增 `single_entity_evaluator.py`，生成同一主体税前年度现金流和 `single_entity_firr_pre_tax`、`single_entity_fnpv_pre_tax`、静态/动态回收期等指标；
- 原 `evaluate_scenario_economy()` 不改，继续作为电源侧投资收益近似模型，避免把同一主体节费口径混入电源侧经济性；
- 同一主体模型复用中性参数和工具：风光储/送出线路/其他固定资产投资、运维成本、储能更换年限、上网电价、折现率和 IRR 求解；
- 同一主体模型不使用 `self_use_price_with_vat`，也不生成 `self_use_revenue_with_vat` 字段；内部绿电结算价不作为同一主体整体收益。

验证记录：

- `python -m pytest tests\test_single_entity_economy.py tests\test_economy_v1.py` 通过，23 个测试全部通过；
- `python -m pytest` 通过，96 个测试全部通过。

## 2026-05-25 经济性逐年明细与视角分离

用户进一步确认：技术方案概览表只展示技术指标，不把经济性视角的 FIRR/FNPV 混入技术总览。几个经济性视角的指标也不能简单并排塞入同一个“概览表”，因为同一主体、电源侧、负荷侧的评价对象和现金流口径不同。后续若设计总视图，应在推荐席位都形成后再讨论。

本次实现调整：

- Streamlit 的“方案汇总 Excel”恢复为纯技术指标下载，不再因已计算经济性而自动追加经济性字段；
- 电源侧经济性 V1 在经济性区域单独展示和下载汇总表，并继续支持所选方案 Year 0-Year N 年度现金流 Excel；
- 同一主体税前经济性作为正式软件高级测算项接入 UI，用户可启用后默认输入 `net_avoided_grid_cost_price`；需要复核电费清单时再勾选“按电费清单组价”，按电能量/市场购电价格、上网环节线损费用、系统运行费用、输配电价、政府性基金及附加、购电增值税率等字段组价；
- 同一主体税前经济性在经济性区域单独展示和下载汇总表，并支持所选方案 Year 0-Year N 年度现金流 Excel；
- UI 中将原“自发自用电价”显示名改为“绿电结算价”，但底层旧字段 `self_use_price_with_vat` 暂作为迁移期字段保留；
- 经济性逐年明细不是临时复核包，而是正式软件的可审计输出能力。后续电源侧、同一主体、负荷侧和推荐席位相关经济性结果均应提供逐年详表或等价明细导出，避免黑箱化。

验证记录：

- `python -m pytest tests\test_ui_import.py tests\test_single_entity_economy.py` 通过，6 个测试全部通过；
- `python -m pytest` 通过，96 个测试全部通过。

## 2026-05-25 经济性参数分组纠偏

用户复核 UI 输入后指出：不能把通用经济参数塞进“同一主体高级参数”区，也不能用“可节省 / 不可节省 / 非增值税部分”等抽象命名让用户反向理解电费清单。该问题已作为后续开发规则沉淀。

纠偏原则：

- 参数按归属分组：技术调度参数、通用经济参数、视角专用经济参数必须分开。储能更换投资比例、储能更换进项税率、电池日历寿命等参数是通用经济参数，不属于同一主体口径；
- 电池循环寿命属于储能技术参数，当前用于技术结果中的年等效循环和按循环寿命估算更换年；电池日历寿命当前不参与小时调度，只在经济性中与循环寿命共同决定储能更换年份，因此 UI 放在储能参数区并明确说明；
- 用户侧电费输入应优先对应电费清单科目。默认模式只给一个“外部购电净成本单价”输入；需要复核或拆分时，再勾选“按电费清单组价”；
- 组价字段采用：电能量/市场购电价格、上网环节线损费用、系统运行费用、输配电价、政府性基金及附加。容需量电费和力调电费 V1 默认不参与节费或增费测算，并在 UI 中说明原因；
- 百分比类输入用百分数展示，默认不显示小数，例如折现率 6、企业所得税率 25、销项税率 13；内部仍转换为 decimal；
- 造价、投资、运维成本等金额类输入默认不显示小数，但用户输入小数时应支持。

本次实现调整：

- 经济性 UI 改用文本数字输入，使默认值不显示多余小数，同时保留用户输入小数的能力；
- “同一主体税前经济性（高级）”仅保留同一主体视角所需的外部购电净成本/组价和环境价值输入；
- 储能更换投资比例、储能更换进项税率移入通用经济参数区；
- 电池日历寿命移入侧边栏“储能参数”，并说明当前只影响经济性更换、不参与小时调度；
- `AvoidedGridPurchaseParams` 改为默认净成本单价 + 可选电费清单组价字段，废弃面向用户不友好的 `non_avoidable_*` / `avoidable_non_vat_fee` 命名。

## 2026-05-26 经济性年度明细表可复核性增强

用户复核 `single_entity_pre_tax_annual_cashflow_S0165` 后指出：年度现金流表不能只给方案编号和一组程序字段，否则用户无法直接判断方案规模、政策指标和字段计算关系。

已确认的详表规则：

- 所选方案年度现金流 Excel 应包含方案上下文，至少包括风电、光伏、储能功率、储能容量、主要政策指标、关键电量和经济性汇总；
- 年度现金流表头应带序号，方便在表内说明计算关系；
- 应提供字段说明表，逐项解释字段含义和计算公式，例如“自发自用购电节费 = 自发自用电量 × 被替代外部购电净成本单价”；
- 含义相近但口径不同的字段必须说明差异。例如“自发自用购电节费”是进入税前 FIRR 的净成本口径收益，“少付电网电费现金额”是现金辅助展示口径，不进入税前 FIRR；
- 储能更换字段必须解释含税现金流出和评价基础的关系：含税现金流出是实际含税支出展示口径；评价基础默认扣除可抵扣进项税后进入税前 FIRR。

本次实现：

- 同一主体年度现金流下载改为三张工作表：`方案说明`、`年度现金流`、`字段说明`；
- `方案说明` 展示方案类型、风光储规模、政策指标、电量指标和同一主体关键经济性指标；
- `年度现金流` 使用编号表头；
- `字段说明` 对每个编号字段给出含义或计算关系；
- 新增 UI 测试确认同一主体年度现金流工作簿包含三张工作表、编号表头、储能容量信息和计算说明。

## 2026-05-27 经济性输入入口再次纠偏

用户指出：推荐席位肯定要计算，因此不应把同一主体或负荷侧所需的固定价输入藏在“启用某视角”之后。经济性测算应当是一次点击后计算当前已实现的所有经济性视角，后续推荐席位也应沿用这个入口思路。

已确认规则：

- 固定价参数默认展示并提供默认值，例如 `外部购电净成本单价（元/kWh）`、`绿电结算价（元/kWh，含税）`；
- 价格曲线才作为高级参数处理，后续通过 CSV/Excel 上传，不做网页逐项录入；
- `绿电结算价（元/kWh，含税）` 的 UI 说明必须强调：它不是用户到户电价，不含输配电价、政府基金及附加、系统运行费和容需量电费等；
- 经济性参数按 `基本参数`、`成本费用`、`收入和税金` 等分区组织，暂不做资金来源/贷款，因为当前 V1 不考虑贷款；
- `基本参数` 不是只放运营期和折现率，也应包含 Year 0 建设投资相关参数：风电、光伏、储能单位造价，送出线路工程投资，其他固定资产投资，以及建设投资进项税率；
- `成本费用` 主要针对运营期费用。风光储运维、其他运行成本和运营期储能更换放在这里；储能更换作为小区单独展示，并说明“发生年份以日历寿命和循环寿命哪个先到为准”；
- 电费清单拆分字段不宜归入 `收入和税金` 或 `成本费用`，建议新增 `电费构成参数` 分区，用于承载电能量/市场购电价格、线损费用、输配电价、系统运行费、政府基金及附加等账单科目；
- 点击经济性测算时，应一次计算当前已实现的经济性视角。目前实现为电源侧经济性 V1 + 同一主体税前经济性；负荷侧综合用能收益是下一步讨论和实现对象。

本次实现调整：

- 移除“启用同一主体税前经济性测算”开关；
- 将 Year 0 建设投资参数移入 `基本参数` 的 Year 0 建设投资小区，建设投资进项税率随之放入该小区；
- 将运营期运维和储能更换保留在 `成本费用`，并补充储能更换触发说明；
- 将 `外部购电净成本单价` 默认放入 `收入和税金` 分区，与 `绿电结算价`、`上网电价`、环境价值等固定价参数并列；
- 将 `其他经营收入` 归入 `收入和税金` 分区下的高级折叠区。一般项目没有其他经营收入，默认不应占用主输入界面；
- 新增 `电费构成参数` 分区；“按电费清单组价覆盖外部购电净成本单价”和价格曲线说明放入该分区的高级折叠区；
- 将两个按钮合并为 `计算经济性 V1（当前已实现视角）`，一次计算电源侧和同一主体经济性结果。

术语补充：

- `外部购电净成本单价` 用于同一主体口径，表示每 1 kWh 自发自用绿电替代外部购电带来的税前净节费。它应等于原外部购网电电量类成本，扣除绿电直连自发自用仍需缴纳的费用；容需量电费、力调电费等非电量费用本阶段默认不参与；
- 它不同于负荷侧比较绿电结算价时使用的“电能量全电价”或到户电量电费口径。负荷侧节费要比较的是原购网电账单中会随绿电替代而减少的电量类费用，与绿电结算及仍需承担的输配、基金等费用之间的差额；
- 组价模式下，建议在 UI 和导出说明中同时展示公式：

```text
外部购电净成本单价 =
  原外部购网电电量类成本单价
  - 绿电直连自发自用仍需缴纳费用单价
```

展开为：

```text
原外部购网电电量类成本单价 =
  (电能量/市场购电价格 + 线损费用 + 系统运行费用 + 输配电价)
  ÷ (1 + 电网购电增值税率)
  + 政府性基金及附加

绿电直连自发自用仍需缴纳费用单价 =
  绿电仍缴输配电价 ÷ (1 + 电网购电增值税率)
  + 绿电仍缴政府性基金及附加
```

其中政府性基金及附加按无增值税电量附加处理，不参与价税分离。1192 号文系统运行费暂按下网电量缴纳，自发自用绿电不作为“绿电仍缴系统运行费用”扣减；若当前项目口径认为自发自用绿电仍缴输配电价和政府性基金及附加，则这两项不能算作节省；
- 在用户和绿电的结算价格为“绿电结算价 + 输配电费 + 政府基金及附加”的简化情形下，负荷侧节约电费可按：

```text
节约电费单价 =
  (电量电价 + 线损 + 输配 + 系统运行 + 政府基金及附加)
  - (绿电结算价 + 输配 + 政府基金及附加)
```

若输配和政府基金两边口径一致，可在差额中抵消；逐时价格版本则按每个时间步分别计算价差后乘以逐时自发自用电量。

## 2026-05-27 负荷侧可成交收益席位口径

用户指出：若负荷侧席位只按“综合用能收益绝对值最大”排序，在绿电到户价低于电网购电价时，会天然偏向更大的风光储规模和更多自发自用电量，可能推荐出电源侧完全不赚钱、交易无法成立的方案。

修正决策：

- 第三个默认推荐席位命名为 `负荷侧可成交收益最优`，不再用“纯负荷侧综合用能收益最大”作为默认推荐；
- 新增基础参数 `电源侧最低可接受 FIRR`，默认 7%，字段建议为 `min_power_side_acceptable_firr`。该参数放在基本参数区，不作为高级参数；
- 若用户清空该参数，则不对负荷侧可成交收益席位进行默认排序，并在推荐结果处提示“缺少电源侧最低可接受 FIRR，无法判断可成交性”；
- V1 暂不反算绿电结算价。推荐引擎只在用户给定绿电结算价、上网电价和费用参数条件下排序；反算绿电结算价属于价格谈判或均衡求解模型，后续版本再研究。

默认筛选链：

```text
政策达标
负荷侧年度综合用能收益 > 0
电源侧 FIRR 可可靠计算
电源侧 FIRR >= 电源侧最低可接受 FIRR
```

默认排序链：

```text
负荷侧年度综合用能收益从高到低
电源侧 FIRR 更高
电源侧静态回收期更短
初始投资更低
绿电占比更高
弃电率更低
```

高级或诊断模式可以保留 `纯负荷侧收益最大` 作为谈判边界参考，但必须提示电源侧 FIRR 未达标或交易不可成立风险。

## 2026-05-27 推荐方案 V1 试用实现

已实现四个默认推荐席位的第一版试用，并修正一次实现偏差：推荐引擎不能只显示负荷侧和工程代表两个席位；完成经济性评价后，应同时构造同一主体、电源侧、负荷侧和工程代表四个默认席位。同一 `scenario_id` 命中多个席位时合并标签，不硬凑重复卡片。

- `同一主体 FIRR 最优`：读取同一主体税前经济性汇总，只在政策达标且 `single_entity_firr_status == ok` 的候选集中排序，主排 `single_entity_firr_pre_tax` 从高到低，辅助看静态/动态回收期、FNPV、初始投资等；
- `电源侧 FIRR 最优`：读取电源侧经济性汇总，只在政策达标且 `firr_status == ok` 的候选集中排序，主排 `firr` 从高到低，辅助看静态/动态回收期、FNPV、建设投资等；
- `负荷侧可成交收益最优`：固定价版本。读取技术汇总、电源侧经济性汇总和当前经济性输入；先筛政策达标、负荷侧年度综合用能收益为正、电源侧 FIRR 可可靠计算且不低于 `电源侧最低可接受 FIRR`，再按负荷侧年度综合用能收益排序；
- `工程代表方案`：读取技术汇总，默认 `低弃电工程代表`，可切换 `政策达标最小投资`、`高绿电占比`、`高自发自用`；
- 推荐组合去重已实现：同一 `scenario_id` 命中多个席位时合并推荐标签，不硬凑重复卡片；
- 页面新增 `推荐方案 V1（试用）` 区域，并提供推荐组合 Excel 下载。下载工作簿包含推荐组合、电源侧经济性汇总、同一主体经济性汇总和负荷侧明细表，可复核排序依据、节约电费单价、负荷侧收益、电源侧 FIRR 门槛和可成交状态；
- `电源侧最低可接受 FIRR（%）` 放入经济性 `基本参数`，默认 7%。留空时负荷侧可成交收益席位不参与默认排序并提示缺少可成交性约束；
- V1 仍不反算绿电结算价。推荐只在用户给定价格和费用参数下排序。

纠偏补丁：

- 推荐组合去重合并不能只合并标签和推荐理由；若同一方案命中多个席位，最终展示行还必须合并后续席位带来的关键指标，例如负荷侧年度综合用能收益、负荷侧节约电费单价、电源侧 FIRR、同一主体 FIRR 等；
- 否则会出现“标签显示命中了负荷侧席位，但负荷侧指标为空或缺失”的误导性推荐表；
- 已增加回归测试，确保重复席位合并后保留后命中席位的指标。

实现文件：

- `src/green_direct/recommendation/recommendation_engine.py`
- `src/green_direct/recommendation/__init__.py`
- `tests/test_recommendation_v1.py`
- `src/green_direct/ui/app.py`
- `src/green_direct/ui/field_labels.py`

## 2026-05-25 方案遍历试用程序独立包装

用户提出希望先把“方案遍历计算并输出方案概览、方案详表”的能力单独包装成低门槛试用程序，发给其他同事试用，以便更快发现数据、计算口径、枚举范围和导出体验问题。

产品判断：

- 该试用入口应保持窄边界，只包装当前 V0.1 风光储技术遍历和导出能力，不把完整 Streamlit、图表、经济性评价和推荐引擎一起发出去；
- 试用程序输出全量枚举结果是为了内部试算和问题发现，不代表长期主产品体验会回到“全量枚举表优先”；
- 对外试用材料必须同时包含使用说明、调度策略和计算原理说明，避免同事把导出表误读为推荐结论。

本次实现：

- 新增 `src/green_direct/services/batch_trial_runner.py`，封装三条 CSV 读取、方案遍历、现有批量仿真和概览/详表导出；
- 新增 `src/green_direct/ui/batch_trial_gui.py`，提供 Tkinter 桌面试用入口；
- 新增 `packaging/pyinstaller/run_batch_trial_tool.py`、`GreenDirectBatchTrial.spec` 和 `scripts/build_batch_trial_exe.ps1`；
- 新增 `docs/BATCH_TRIAL_TOOL_USER_GUIDE.md` 和 `docs/BATCH_TRIAL_DISPATCH_AND_CALCULATION.md`；
- 更新 `docs/PACKAGING_NOTES.md`，区分完整 Streamlit 便携包和独立方案遍历试用程序。

边界说明：

- 本入口不改变核心调度策略；
- 本入口不新增经济性计算；
- 本入口默认仍输出全部逐小时明细 ZIP，方案数大时文件会很大，试用阶段建议先用较粗步长。

## 2026-05-27 经济性评价与推荐 V1 全局复核

用户提出需要对整个经济性评价模块做一次全局复核，使第一次接触项目的人能够快速看明白参数、口径、推荐席位和计算链路。

本次复核结论：

- 新增导览文档 `docs/ECONOMY_RECOMMENDATION_V1_MAP.md`，把经济性参数、技术 summary 字段、三类经济视角、四个推荐席位、代码入口和测试入口串成一张地图；
- 确认当前经济性 V1 分为三类视角：电源侧项目投资现金流、同一主体税前增量现金流、负荷侧可成交收益明细；
- 确认同一主体税前 FIRR 不使用绿电结算价作为整体收益，使用 `net_avoided_grid_cost_price` 计算自发自用购电节费；
- 修正一个重要口径风险：简化固定价模式下，负荷侧可减少购网费用单价不再从同一主体 `net_avoided_grid_cost_price` 间接推导，而是作为独立 UI 输入 `load_side_avoided_charge_price` 传入推荐引擎；
- 组价模式下，仍可由电费清单字段推导同一主体净节费单价和负荷侧现金口径单价，但文档中明确两者含义不同；
- 修正工程代表方案排序健壮性：缺少部分辅助排序列时不应因排序列和升降序长度不一致而崩溃。

后续建议：

- 继续把 Streamlit 中的经济性和推荐编排抽成服务层，形成更清楚的 `StudyResult` / `RecommendationPortfolio` 返回对象；
- 为负荷侧可减少购网费用单价补充更完整的组价导出说明；
- 价格曲线仍应通过 CSV/Excel 模板输入，不应在网页中逐项录入。

## 2026-05-28 价格口径、推荐默认席位与 UI 工作流复核

用户进一步追问三个口径和体验问题：

1. 同一主体 FIRR 的“外部购电净成本单价”和负荷侧可成交收益的“负荷侧可减少购网费用单价”有什么区别，是否可以减少输入；
2. “负荷侧可减少购网费用单价”和“负荷侧节约电费单价”有什么区别；
3. 同一主体 FIRR 最优、电源侧 FIRR 最优、低弃电工程代表经常重合，是否说明负荷侧指标有问题，是否应调整同一主体和工程代表席位。

本次结论：

- `net_avoided_grid_cost_price` 是同一主体税前净节费口径；`load_side_avoided_charge_price` 是负荷侧支付绿电结算价之前可减少的购网费用现金口径；两者不只是“多减一道绿电结算价”的关系，还存在税前/现金口径差异；
- `load_side_saving_price` 不是输入，而是计算结果：`load_side_avoided_charge_price - green_power_settlement_price_with_vat`；
- 为减少默认输入，固定价模式下 UI 默认只让用户填写“外部购电净成本单价”，并内部推导负荷侧筛选价；需要精确区分时，可启用电费清单组价或高级覆盖负荷侧可减少购网费用单价；
- 同一主体席位保留 FIRR 默认视角，同时支持切换为“动态回收期最短”，用于观察更偏快速回收的方案；
- 工程代表方案默认从“低弃电工程代表”调整为“政策达标最小投资”，低弃电保留为可切换视角；
- 新增价格曲线模板草案：`docs/templates/price_curves/price_curve_template.csv` 和 `docs/templates/price_curves/README.md`；
- 新增 UI/在线化重构草案：`docs/WEB_APP_WORKFLOW_AND_UI_RESTRUCTURE.md`。判断是不急于完整前后端重写，先把当前 Streamlit 拆成欢迎页、技术仿真、经济性评价、推荐方案与详细分析的工作流，再抽服务层和 ResultStore。

后续建议：

- 下一步先在 Streamlit 内做工作流拆分和服务层抽取，不直接开始完整在线化重写；
- 图表模块应围绕推荐方案和用户钉选方案重做，重点解决典型日、全年 8760 曲线缩放、多曲线指标分组和按需加载；
- 价格曲线模板先请用户确认字段，再接入读取、校验和计算。

## 2026-05-28 Streamlit 工作流 Phase 1 落地

在不改动技术仿真和经济性计算内核的前提下，已先把当前 Streamlit 从“一页到底”的体验拆成四个阶段：

- `欢迎页`：展示当前测算状态、方案数量和建议使用路径；
- `技术仿真`：保留曲线上传、方案遍历、储能参数、政策约束和技术结果高级下载；完成后提示进入经济性评价；
- `经济性评价`：只负责经济参数、经济性计算和经济性结果下载，不再顺手渲染推荐和图表；
- `推荐方案与详细分析`：集中展示推荐组合、用户指定方案和图表分析。

实现细节：

- `src/green_direct/ui/app.py` 新增 `WORKFLOW_PAGES`、`_render_workflow_navigation()`、`_render_welcome_page()`、`_render_recommendation_analysis_page()`；
- 经济性计算成功后保存 `recommendation_v1_inputs`，推荐页读取上一次经济性计算对应的价格、门槛和经济参数，避免推荐席位脱离经济性输入；
- 新增 `src/green_direct/services/study_runner.py`，提供 `run_economic_study()`、`build_recommendation_study()` 和 `RecommendationInputSnapshot`，让 UI 不再直接承担全部经济性与推荐编排；
- `src/green_direct/visualization/chart_ui.py` 的运行时序拆成 `典型季节日`、`关键运行日`、`全年8760曲线` 三个子视图；全年曲线支持范围滑块和多曲线开关；
- 全量枚举表和逐小时明细仍保留为高级展开和下载，不作为主页面默认输出。

验证结果：

- 2026-05-28 使用系统 Python 执行 `pytest`，114 项测试全部通过。

后续建议：

- 下一步抽出服务层和 `StudyResult`，否则 Streamlit 页面仍承担过多编排逻辑；
- 图表模块下一轮应直接消费推荐组合，减少 `chart_ui.py` 内部自选代表方案的临时逻辑；
- 在接入价格曲线模板前，先让用户确认 CSV 字段是否贴近实际电费清单。

## 2026-06-01 图表典型日与 UI 工作流继续打磨

用户要求四季典型日图表必须标注具体日期，并希望网页从“混在一起的一页”继续改成清晰的模块页面：欢迎页、方案仿真、经济性测算、方案推荐及图表概览、图表下载和报告生成。

本次口径与实现：

- 四季典型日从固定月份中位日升级为“季节中心日法”：春季取 3-5 月、夏季取 6-8 月、秋季取 9-11 月、冬季取 12/1/2 月，在完整 24 小时日期中按负荷、风光、储能、电网、弃电、SOC 等已有逐小时字段标准化后，选离季节平均曲线最近的真实日期；
- 典型日图表标题和说明显示 `MM/DD`，例如 `24H 典型日运行策略 · 春季 · 03/02`；
- 典型日曲线仍直接读取 `hourly_detail` 原始逐小时字段，不做平滑、插值或重新调度；
- Streamlit 导航改为五个页面，并保留旧页面名到新页面名的兼容映射，避免旧会话状态或非预期入口导致页面状态报错；
- 新增“图表下载和报告生成”页，集中下载方案汇总、逐小时明细、图表 HTML ZIP、技术+经济汇总和简版 Markdown 报告；
- 更新 `docs/CHART_MODULE_CURRENT_LOGIC.md` 和 `docs/WEB_APP_WORKFLOW_AND_UI_RESTRUCTURE.md`，同步新的典型日选择口径和五页面工作流。

验证结果：

- `tests/test_chart_data.py` 覆盖季节中心日选择和 MM/DD 输出；
- `tests/test_ui_import.py` 覆盖旧页面状态兼容、跳转 rerun 和简版报告典型日说明。

## 2026-06-02 浏览器批注修复：按钮跳转和总览图可读性

用户在浏览器中批注指出：欢迎页“开始方案仿真”和方案仿真页“进入经济性测算”按钮点击后仍报 `st.session_state.workflow_page cannot be modified after the widget with key workflow_page is instantiated`；推荐图表页的多方案雷达图叠加严重，且图例只有方案编号，无法对应风光储配置。

修正：

- 导航按钮不再直接写 `st.session_state["workflow_page"]`，而是写 `_workflow_page_target`；下一轮脚本开始、`st.radio(key="workflow_page")` 创建之前，再由 `_normalize_workflow_page()` 应用目标页面，符合 Streamlit widget 状态规则；
- 新增回归测试覆盖旧页面名映射、按钮排队跳转和下一轮应用目标页面；
- 方案总览中的多方案关键指标图从雷达图改为分组柱状对比图，避免多方案面片叠加；
- 图例从单纯 `S0002` 改为 `S0002 · 光20 风10 储3/6` 这类短容量标签，便于直接对应风光储配置；
- `docs/CHART_MODULE_CURRENT_LOGIC.md` 同步更新图表说明。

## 2026-06-02 UI 深度改造：工程软件工作台第一版

用户明确否定上一轮粗糙 Streamlit 表单堆叠原型，要求 UI 接近第二张参考设计：左侧深蓝固定导航、顶部项目状态栏、主区为紧凑工程工作台，并保持五个主模块：

- 欢迎页；
- 方案仿真；
- 经济性测算；
- 方案推荐及图表概览；
- 图表下载和报告生成。

本轮产品判断：

- UI 不能再把全量枚举表和逐项参数暴露成主体验，枚举只是内部搜索方法；
- 状态卡不应散落到每个业务页，适合放在欢迎页和顶部轻量状态条；
- 参数不能丢，但应分层收纳：关键参数直接可见，专业/高级参数折叠；
- 方案仿真和经济性测算页保留现有计算入口；推荐页主要展示代表方案、图表和复核明细；下载和报告集中在最后一个页面；
- 这轮只改 UI 信息架构和状态同步，不改变技术仿真、储能调度、经济性计算口径。

本次实现：

- `src/green_direct/ui/app.py` 新增工程工作台样式：深蓝侧栏、五模块导航、顶部项目状态条、紧凑页面标题和推荐方案卡片；
- 方案仿真页把曲线数据、候选方案池、政策约束和专业参数放入主工作区，侧栏只保留导航和轻量状态；
- 经济性测算页默认展开经济性参数工作台，保留 Year 0 投资、成本费用、收入税金、电费构成等现有参数，高级项折叠；
- 推荐页先渲染推荐卡片，再保留推荐组合明细和图表概览；
- 仿真、经济和推荐页不再放下载按钮，所选方案逐小时 CSV、汇总 Excel、年度现金流、推荐组合 Excel、图表 HTML ZIP 和简版 Markdown 报告集中到下载报告页；
- 仿真和经济计算完成后使用 `st.rerun()` 刷新顶部状态条，按钮跳转仍通过 pending target 状态避免 `workflow_page` widget key 报错。
- 推荐图表页已改为优先消费正式 `RecommendationPortfolio`，图表默认围绕推荐组合和用户手动加入方案；下载页图表 HTML ZIP 的多方案对比范围也收窄为“推荐组合 + 当前报告方案”；
- Demo 候选范围调整为 27 个小方案，其中包含政策达标候选，避免演示推荐页时所有卡片都是 `no_candidate`。

验证结果：

- `python -m pytest tests/test_ui_import.py tests/test_visualization_smoke.py tests/test_chart_data.py`，19 项通过；
- 全量 `python -m pytest`，124 项通过；
- 使用 bundled Playwright + 系统 Chrome 实际点击：欢迎页进入方案仿真、Demo 生成、进入经济性测算、经济性 V1 计算、进入推荐页、进入下载报告页；顶部状态条同步更新为 `27 个 / 15 达标`，推荐页 active strip 显示正式推荐席位标签和风光储配置，未出现 `st.session_state.workflow_page cannot be modified after the widget with key workflow_page is instantiated`。

## 2026-06-03 推荐图表页样板映射正式接入

用户要求不要停留在静态 UI DEMO 和映射文档，而是把“方案推荐及图表概览”推进为可运行、可测试、可浏览器验证的正式 Streamlit 页面。

本轮产品判断：

- 静态样板页只保留在 `docs/ui/` 中作为视觉和信息层级参考，mock 数据不得进入正式 Streamlit、计算链路、图表链路或导出链路；
- 推荐图表页应优先消费正式 `RecommendationPortfolio`，卡片和图表都围绕代表方案，不回到全量枚举表优先；
- 推荐页可以提供“下载与报告”入口和默认报告方案状态，但实际 CSV、Excel、HTML ZIP 和 Markdown 报告下载仍集中到最后一个页面，避免下载按钮散落到业务分析页；
- 底部状态栏只显示真实默认报告方案、逐小时台账数量和数据来源；真实版本号、帮助入口、项目路径等元数据尚未结构化时显示“待接入”，不使用样板页占位值。

本次实现要点：

- 顶部状态条新增数据时间范围，从 `batch_result.hourly_details` 中带 `timestamp` 的逐小时明细推导起止日期和小时数；
- 推荐方案卡片新增排序标识和 `export_rate` 上网比例，并修正 `no_candidate` / `pending` 状态，避免无候选席位被渲染成成功态；
- 推荐页底部新增下载报告入口，默认报告方案优先取推荐组合中的有效 `scenario_id`，并跳转到“图表下载和报告生成”页复用已有导出功能；
- 新增底部状态提示，明确正式页读取 `batch_result.summary`、`hourly_details` 和经济性 session 结果，不读取 `docs/ui/` mock。

边界：

- 未修改技术仿真、储能调度和经济性计算口径；
- 未改变数据结构和导出文件格式；
- 未引入 React/FastAPI/Vue 或新的大型依赖。

## 2026-06-03 推荐图表页视觉复核：功能闭环不等于 UI 达标

用户复核 `docs/ui/20260603-1638-codex` 截图后指出：当前页面虽然已经能读取真实推荐结果、图表和导出状态，但和参考样板仍相差很远。该反馈成立，问题不在计算链路，而在默认页面仍是 Streamlit 线性堆叠：

- 推荐页把完整图表分析模块作为主视图，导致页面过长，不像紧凑工程工作台；
- 推荐视角下拉框直接占据主页面，不符合“关键结果优先、专业控制折叠”的原则；
- 默认图表没有形成样板图中的“推荐卡片 + 多方案关键指标 + 24H 代表曲线 + 下载报告带”的一屏判读结构；
- Streamlit 默认顶部工具条和过宽侧栏破坏工程软件观感。

本轮整改方向：

- “方案推荐及图表概览”默认视图改为代表方案工作台，完整 `render_chart_analysis()` 只保留在高级展开区；
- 推荐卡片继续只读取正式 `RecommendationPortfolio`，图表只围绕推荐组合和默认报告方案，不搬入 `docs/ui/` mock；
- 推荐席位设置折叠，参数不丢但不压住主结果；
- 隐藏 Streamlit 默认顶部工具条，收窄侧栏，拉近深蓝导航 + 紧凑主区的视觉比例。

## 2026-06-03 推荐页与导出页继续收敛：默认视图只保留判读主线

在上一轮整改后，04 页已经形成“推荐卡片 + 代表图表 + 下载入口”的主线，但首屏仍被卡片和复核展开栏占用过多，05 页仍像两列下载清单，不像集中导出工作台。

本轮继续收敛：

- 推荐卡片从“多指标复核卡”压缩为“一眼判断卡”：保留绿电占比、自发自用率、弃电率、上网比例和一个与席位相关的经济性指标；
- 推荐卡片指标改为三列紧凑网格，状态标签不换行，首屏能同时看到推荐卡片和代表图表区；
- 推荐组合明细、负荷侧复核和完整图表分析统一放到默认图表/下载区之后的高级折叠区；
- 05“图表下载和报告生成”页改成导出工作台：顶部显示当前导出方案，下面分为“技术数据 / 图表包 / 经济与报告”三列，批量技术包、年度现金流和推荐组合 Excel 放入高级折叠区；
- 导出页仍只读取真实 `batch_result.summary`、`hourly_details`、`economy_v1_result`、`single_entity_economy_result` 和推荐输入，不接入样板页 mock。

验证：

- `python -m pytest tests/test_ui_import.py tests/test_visualization_smoke.py tests/test_chart_data.py`，25 项通过；
- 全量 `python -m pytest`，130 项通过；
- in-app 浏览器完成真实 Demo 流程验证：欢迎页 -> 方案仿真 Demo -> 经济性测算 -> 方案推荐页，未出现 `workflow_page` 状态修改报错，04 页首屏可见推荐卡片和代表图表；
- in-app 浏览器完成 05 页有结果态文本验证：从侧栏直接进入下载页时，默认导出方案已优先选推荐组合有效方案 `S0010`，而不是枚举首项 `S0001`；页面包含“技术数据 / 图表包 / 经济与报告 / 高级：年度现金流与推荐组合导出”四个导出工作区，未出现 `workflow_page` 状态修改报错。

## 2026-06-03 方案仿真页视觉整改：从原生表单堆叠改为工程工作台

用户指出 02“方案仿真”页仍然像 Streamlit 原生表单：参数密集、宽度利用不足、折叠参数展开后左右留白明显、导航仍有 radio 观感、低价值提示常驻主画面。该反馈成立，本轮只整改 UI 组织和状态呈现，不改变技术仿真、储能调度、政策筛选或经济性计算口径。

本次整改：

- 侧栏工作流导航从 `st.radio` 改为深蓝按钮式步骤入口，当前页面用自定义 active item 标识，继续通过 pending target 跳转，避免 `workflow_page` widget key 状态报错；
- 02 页改为三块紧凑工作台：`数据曲线 / 候选方案池 / 政策和电网约束`，放开主区最大宽度，避免左右两列拉长后出现大面积空白；
- 批量上传保持直接可见，单独覆盖、编码、时间列/数值列识别进入“高级：单独上传覆盖”和“数据识别复核”，参数不丢但默认不压住主流程；
- 储能 SOC、效率、循环寿命和日历寿命移到全宽专业折叠区，展开后按横向网格排列，不再在半屏列内下坠；
- Demo 生成后使用 pending 状态在下一次渲染启用示例曲线显示，避免已有结果但曲线卡仍显示“未选择”；
- 按钮、下载按钮、侧栏按钮、紧凑状态卡统一工程软件风格，减少 Streamlit 原生控件的视觉割裂。

验证：

- `python -m pytest tests/test_ui_import.py tests/test_visualization_smoke.py tests/test_chart_data.py`，25 项通过；
- in-app 浏览器真实点击 02 页：左侧 radio 数量为 0，活动导航为 `02 方案仿真`，页面显示三张曲线状态卡和当前表单方案数；
- in-app 浏览器点击 `一键生成 Demo 结果` 后，三张曲线卡显示示例文件和自动识别列，未出现 `workflow_page cannot be modified after the widget with key workflow_page is instantiated`。

## 2026-06-04 服务层抽取：run_technical_study 与 StudyResult 雏形

用户要求基于当前五页面工作流，继续把 `src/green_direct/ui/app.py` 中的业务编排抽到服务层；目标不是大迁移，而是先落一个最小可用的技术研究服务入口和顶层结果对象。

本次判断：

- 继续保留现有 V0.1 风光储技术内核，`run_technical_study()` 内部仍调用 `read_curve_set()` 和 `run_batch()`，不改变储能调度、政策筛选、经济性或推荐计算口径；
- `StudyResult` 先作为顶层结果雏形，不强制一次性改完图表、导出和推荐页面消费方式；
- Streamlit 仍兼容保存 `batch_result`，避免破坏既有经济性、推荐、图表和下载链路；同时新增 `study_result`，为后续逐步迁移到统一上层接口做准备。

本次实现：

- `src/green_direct/services/study_runner.py` 新增 `TechnicalStudyInput`、`TechnicalStudyResult`、`StudyResult` 和 `run_technical_study()`；
- 技术服务统一执行三条曲线读取、输入诊断承接、旧批量技术仿真、`config_snapshot` 生成和进度回调透传；
- `src/green_direct/ui/app.py` 的 Demo 测算和正式测算不再直接调用 `read_curve_set()` / `run_batch()`，改为收集输入后触发服务层；
- 经济性测算和推荐组合生成后，会把 `EconomicStudyResult` / `RecommendationStudyResult` 挂回 `StudyResult`，但当前 UI 仍保留旧 session 键作为兼容层；
- `tests/test_study_runner.py` 新增技术服务层回归测试，覆盖曲线读取、批量仿真、诊断、配置快照和 `StudyResult` 包装。

验证：

- `python -m pytest tests/test_study_runner.py tests/test_ui_import.py`，18 项通过；
- `python -m pytest tests/test_single_scenario.py tests/test_batch_runner.py tests/test_economy_v1.py tests/test_single_entity_economy.py tests/test_recommendation_v1.py tests/test_study_runner.py`，71 项通过。

## 2026-06-04 UI 工作流拆页与输入曲线高优先级悬浮指标

用户指出四个问题：导入曲线的关键基础指标缺失；侧栏模块入口尺寸不一致且折叠后找不到展开按钮；推荐与图表合在一个页面导致页面过长；年度能量流向 Sankey 文字像有描边、可读性差。

本次判断：

- 输入曲线的年总用电量、光伏年利用小时、风电年利用小时属于高优先级诊断信息，但不应常驻占用主表单空间；适合放在曲线状态卡右上角信息图标的 hover tooltip 中；
- 推荐和图表应拆成两个模块：`方案推荐` 只解决推荐席位、理由、风险和明细复核；`图表概览` 只解决代表方案图表、完整图表分析和下载报告入口；
- UI 展示指标只从当前已选列的 DataFrame 预览计算，不回写 `read_curve_set()`、`run_technical_study()`、`run_batch()` 或任何底层调度/经济性对象；
- 侧栏折叠态应保留 48px 深蓝工具轨，避免 Streamlit 默认 collapsed control 被内部布局压成 0x0 后用户找不到展开入口。

本次实现：

- 工作流从 5 页调整为 6 页：`欢迎页 / 方案仿真 / 经济性测算 / 方案推荐 / 图表概览 / 图表下载和报告生成`；
- 兼容旧别名：`方案推荐及图表概览`、`推荐方案与详细分析`、`方案推荐与图表概览` 继续跳转到新的 `方案推荐`；
- 曲线状态卡新增 hover 信息图标：负荷显示年总用电量，光伏和风电显示年利用小时，并附有效点数和时间范围；
- 侧栏模块按钮改为短标题、固定 `207px × 46px` 的同宽入口；折叠后保留 `48px` 侧边轨和可点击按钮，可重新展开；
- `方案推荐` 页面移除图表概览和完整 `render_chart_analysis()`，新增 `进入图表概览` 入口；
- 新增 `图表概览` 页面，复用正式推荐结果构造代表方案图表，完整图表分析仍放在高级折叠区；
- Sankey 图展示层调整为显式深色字体、轻量节点边框和更淡连线，改善文字可读性，不改变能量流向数值。

验证：

- `python -m py_compile src/green_direct/ui/app.py src/green_direct/visualization/chart_ui.py` 通过；
- `python -m pytest tests/test_ui_import.py tests/test_visualization_smoke.py tests/test_chart_data.py`，28 项通过；
- 全量 `python -m pytest`，134 项通过；
- in-app 浏览器验证：02 页 Demo 后三张曲线卡的 hover title 分别显示 `年总用电量：23,000 万kWh`、`光伏年利用小时：2,062 h`、`风电年利用小时：1,976 h`；
- in-app 浏览器验证：侧栏展开态模块入口同宽同高，折叠态保留 48px 工具轨并可重新展开；
- in-app 浏览器验证：04 页为 `方案推荐`，05 页为 `图表概览`，两页可独立点击且未出现 `workflow_page` 状态修改报错。

## 2026-06-04 图表概览重构：方案组合对比优先，下载报告回到最后一页

用户指出 02 页仍缺少可见的导入曲线关键指标，仿真页参数切页后会恢复默认值，顶部状态栏过度铺陈，05 图表概览页不应优先展示典型日曲线，也不应混入下载与报告区。

本次判断：

- 负荷电量、光伏利用小时、风电利用小时应放入深蓝侧栏的可见摘要框，而不是只藏在 hover tooltip；
- Streamlit 跨页面切换会清理未渲染的 widget 状态，仿真页关键输入需要额外保存到非 widget 持久副本；
- 图表概览的主视角应是推荐方案和用户指定方案的组合对比，典型日、能量流向和完整图表放入高级复核；
- “低弃电”“低上网”容易误解，应在图表上直接显示真实 `curtail_rate` 和 `export_rate`。

本次实现：

- 侧栏新增“导入曲线”摘要框，显示 `负荷电量`（亿kWh）、`光伏利用小时`（h）、`风电利用小时`（h），只读取曲线预览，不回写计算链路；
- 方案仿真页关键容量、政策、储能和列选择控件增加稳定 key，并通过 `__stored_value` 持久副本跨页面恢复；
- 顶部项目状态栏改为更紧凑的流程状态灯，显示方案仿真、经济性测算、方案推荐、图表概览、下载报告的完成状态；
- 05 图表概览页新增“方案组合选择”，支持从推荐方案和指定方案中自由组合；
- 主图改为“多方案关键指标对比”，直接展示绿电占比、自发自用率、弃电率和上网比例；
- 用“容量配置横向对比”替代首屏典型日曲线，典型日与完整图表分析保留在高级复核区；
- 05 页移除下载报告 handoff，下载与报告仍集中在 06 页；
- 高级图表模块中的多方案指标标签也从“低弃电 / 低上网”改为“弃电率 / 上网比例”。

验证：

- `python -m py_compile src/green_direct/ui/app.py src/green_direct/visualization/chart_ui.py` 通过；
- `python -m pytest tests/test_ui_import.py tests/test_visualization_smoke.py tests/test_chart_data.py`，31 项通过；
- 全量 `python -m pytest`，137 项通过；
- 新增 AppTest 回归：`光伏容量结束` 设置为 `18.0`，切到 `经济性测算` 再返回 `方案仿真` 后仍为 `18.0`；
- in-app 浏览器真实点击：欢迎页 -> 方案仿真 -> 一键生成 Demo 结果，侧栏出现负荷电量、光伏利用小时、风电利用小时，未出现 `workflow_page` 状态修改报错；
- in-app 浏览器真实点击：经济性测算 -> 方案推荐 -> 图表概览，05 页出现“推荐方案 / 指定方案”组合选择、“多方案关键指标对比”和“容量配置横向对比”，未出现下载报告区或 `workflow_page` 状态修改报错。

## 2026-06-04 价格曲线 V1 接入经济性与推荐排序

用户提供 `samples/湖南省2025年110kV下网电价曲线_8760小时.csv`，并明确当前绿电直供结算价和上网电价可以先按全年固定值处理，优先把下网电价曲线接入经济性和推荐排序，以便同一主体、负荷侧等视角因自发自用发生时段不同而形成差异。

本次判断：

- 价格曲线只属于经济性评价和推荐排序层，不反向改变风光储逐小时技术调度、SOC、上网、弃电或政策指标；
- 下网曲线优先按电费清单组价读取：电度电价、线损费、系统运行费、输配电价按含税处理，政府性基金及附加按不含增值税处理；
- 若曲线缺少“绿电仍缴输配电价”和“绿电仍缴政府性基金及附加”列，默认这两项仍需缴纳，分别等于同小时输配电价和政府性基金及附加；如项目政策明确免缴，应在 retained 列显式填 0；
- `下网电价合计` 仅作为用户复核列保留，当前不直接读取，避免把仍需缴纳的费用误算为节费；
- 模板中的中文说明行不适合作为可上传 CSV 数据行，新增英文 UTF-8 模板和 README 总体字段对照表。

本次实现：

- 新增 `src/green_direct/economy/price_curves.py`，支持 CSV / Excel 读取、中文字段映射、8760 / 8784 校验、时间戳 / hour_index / 行序对齐和逐方案年度金额聚合；
- `run_economic_study()` 增加可选 `price_curve`、`hourly_details` 和 `dt_hours`，曲线模式下先按每个 `scenario_id` 的逐小时台账聚合价格金额，再进入电源侧和同一主体年度现金流；
- 电源侧经济性支持曲线聚合后的绿电结算收入和上网收入覆盖；同一主体税前经济性支持曲线聚合后的外部购电节费、少付电费现金额、环境价值和上网不含税收入覆盖；
- 推荐引擎在曲线模式下读取逐场景负荷侧收益聚合列，负荷侧可成交收益不再只是统一固定价乘全年自发自用电量；
- Streamlit 经济性页新增价格曲线 CSV / XLSX 上传入口，上传后保存 `price_mode` 和 `price_curve_summary`，固定价模式仍为默认路径；
- 新增 `docs/templates/price_curves/price_curve_template_en.csv`，更新 `docs/templates/price_curves/README.md` 和 `docs/ECONOMY_RECOMMENDATION_V1_MAP.md`。

### 2026-06-04 模板字段纠偏

用户指出前一版模板把绿电结算价、上网电价、度电环境价值、增值税率、负荷侧可减少费用和同一主体外部购电净成本等网页端参数或派生结果也放进了价格曲线，输入边界过宽。

修正口径：

- 价格曲线 V1 模板只保留下网购电账单原始组分：`timestamp`、`hour_index`、`energy_market_price_with_vat`、`line_loss_price_with_vat`、`system_operation_fee_with_vat`、`transmission_distribution_tariff_with_vat`、`gov_fund_surcharge`；
- 绿电结算价、上网电价、度电环境价值继续作为网页端全年固定参数，不从曲线文件读取；
- 电网购电增值税率默认 13%，仍由网页端经济参数控制，不作为逐小时曲线字段；
- 负荷侧可减少费用和同一主体税前净节费由程序根据下网账单组分、税口径和仍缴费用口径推导，不要求用户填写；
- 正式推荐模板新增为 `docs/templates/price_curves/price_curve_template_down_grid.csv`；`README.md` 改为“推荐模板字段”和“不放入模板的字段”两张对照说明。

### 2026-06-04 下网曲线计算方法审阅文档

用户将正式模板调整为 `samples/price_curve_template_down_grid.csv`，字段包含下网账单价格组分以及 `month`、`peak_valley` 辅助复核列。

更新内容：

- 将用户模板同步到 `docs/templates/price_curves/price_curve_template_down_grid.csv` 作为文档副本；
- 新增 `docs/PRICE_CURVE_ECONOMY_CALCULATION_METHOD.md`，逐项说明模板字段如何被读取、校验、对齐，以及如何推导同一主体税前净节费、负荷侧可减少购网费用、负荷侧年度收益和推荐排序字段；
- 明确 `month` 和 `peak_valley` 当前只作复核/展示辅助列，不参与计算；
- 修正对齐逻辑：若 `timestamp` 不匹配且显式 `hour_index` 不完整，不再直接报错，而是 warning 后按文件行序对齐；当前正式模板已填满 `hour_index`，会优先按 `hour_index` 对齐；
- 待用户审阅确认的关键口径包括：输配电价和政府性基金及附加是否默认仍缴、系统运行费是否按下网电量缴纳、是否需要把尖峰平谷标签展示到 UI/报告。

### 2026-06-04 价格曲线 UI 状态流纠偏

用户指出：如果已经在“方案仿真”页上传电价曲线，“经济性测算”页不应再次要求选择曲线；相关固定价/组价操作应置灰，并在页面显著提示已有电价曲线。

修正口径：

- 电价曲线作为项目级输入，上传入口放在“方案仿真”页数据曲线区；
- 上传后保存到 `project_price_curve_data` / `project_price_curve_meta`，经济性页自动使用该对象；
- 经济性页不再提供电价曲线二次上传入口；
- 已有项目级曲线时，外部购电净成本固定输入、电费清单组价开关和负荷侧可减少购网费用单独覆盖置灰，避免覆盖逐小时曲线推导结果；
- 绿电结算价、上网电价和环境价值仍可编辑，因为它们当前不是下网曲线字段；
- 更换项目级电价曲线或重新运行技术仿真时，清空旧经济性和推荐结果，防止旧结果与新输入混用。

验证：

- `python -m pytest tests/test_price_curves.py tests/test_study_runner.py tests/test_single_entity_economy.py tests/test_recommendation_v1.py`，22 项通过。

## 2026-06-06 Product Design UI 审计与改造路线

本轮按 Product Design 审计方式，只读运行当前 Streamlit 应用，目标是全面复核各页面模块、交互流程、图表/导出体验，并产出不触碰底层计算逻辑的 UI 改造路线。

本轮判断：
- 当前六页工作流方向正确：欢迎页、方案仿真、经济性测算、方案推荐、图表概览、图表下载和报告生成已经比早期全量枚举表入口更接近“绿电直连 / 微电网方案策划工作台”；
- 主要问题不是单纯视觉美化，而是任务分层仍需收口：经济性测算页参数过长且主 CTA 不在首屏，推荐页理由和风险需要更清晰，图表页应继续强化“复核”而不是重复推荐，导出页应产品化为交付中心；
- 图表页完成态已经围绕推荐组合和用户指定方案，不再默认围绕全量枚举表，方向符合当前产品原则；
- 窄屏布局存在严重遮挡，左侧导航覆盖主内容，后续 UI 改造应把响应式问题列为 P0；
- 当前 `src/green_direct/ui/app.py` 同时承载全局 CSS、工作流状态、页面渲染、经济性入口、推荐卡片、图表概览和导出动作，后续应逐步抽出 UI state、status、cards、pages 组件，但不应在一次改造中大迁移；
- `src/green_direct/visualization/chart_ui.py` 自带图表 CSS 和图表分析入口，后续需要和主工作台 token/卡片/状态规范对齐。

本轮交付：
- 新增审计目录 `docs/ui/audit-20260606-product-design/`；
- 新增 `FLOW_CAPTURE_NOTES.md`，记录欢迎页 -> 方案仿真 Demo -> 经济性测算 V1 -> 方案推荐 -> 图表概览 -> 下载报告主流程截图与证据限制；
- 新增 `UI_AUDIT_REPORT.md`，按页面列出 UX、信息架构、视觉层级、可访问性、图表表达、空状态/错误状态和导出体验问题；
- 新增 `UI_REDESIGN_ROADMAP.md`，把改造拆成工作台外壳、输入诊断、经济任务台、推荐决策页、图表复核页、交付中心和组件抽取阶段；
- 新增 `docs/ui/prototype-dashboard.html` 静态原型，只使用 mock 数据验证目标布局和交互节奏，不接入正式计算链路。

验证：
- 只读启动当前 Streamlit 应用，使用本地 Chromium/Playwright fallback 截图验证主流程；
- Demo 结果生成后，方案池为 27 个方案、22 个达标；
- 经济性 V1 计算完成后，推荐页、图表页和导出页进入可查看状态；
- 未运行全量 pytest，因为本轮只新增审计文档和独立静态原型，未修改正式代码。

### 2026-06-06 欢迎页定位修正：从欢迎页改为项目启动台

用户反馈 `prototype-dashboard.html` 只展示 04-06，缺少 01-03，并追问欢迎页本身是否有存在意义。

本轮判断：
- 对工程测算 / 方案策划平台来说，单纯“欢迎页”价值较低，容易变成说明文字和推荐使用路径；
- 首页可以保留，但不应叫“欢迎页”，更适合定位为“项目启动台”或“项目总览”；
- 项目启动台应回答三个问题：当前项目是否准备好、下一步最短路径是什么、已有结果是否可信可交付；
- 首页应展示项目上下文、输入曲线状态、候选方案池、推荐/经济/导出可用状态、默认报告方案、缺失项和项目边界，而不是重复介绍产品功能；
- 若未来有项目管理、历史项目、模板、权限或保存功能，启动台还可承接“新建项目 / 导入项目包 / 继续上次研究”。

本轮实现：
- 重写 `docs/ui/prototype-dashboard.html` 为完整六页原型：`01 项目启动 / 02 方案仿真 / 03 经济测算 / 04 方案推荐 / 05 图表复核 / 06 交付导出`；
- 01 页改为项目启动台，展示输入准备、候选方案池、推荐状态、交付准备、下一步建议和项目边界；
- 02 页补输入诊断、候选方案池、政策与电网约束；
- 03 页补核心经济参数、价格输入、结果回馈、Year 0 建设投资和待复核项；
- 04-06 保留上一版推荐、图表复核和交付导出结构。

验证：
- 使用本地 Chromium 打开 `docs/ui/prototype-dashboard.html`，逐页验证 01-06 均可切换；
- 新增原型截图 `33-prototype-01-launch.png` 至 `38-prototype-06-exports.png`。

### 2026-06-06 正式 Streamlit 第一轮落地：01 项目启动台 + 03 经济执行区

用户认可新版 `prototype-dashboard.html` 的整体方向，同时强调 02 方案仿真和 03 经济性计算有大量输入参数，正式映射到底层代码时不能把已有功能搞没。

本轮判断：
- 01 可以先正式落地为项目启动台，因为它主要读取现有 session/result 状态，不涉及底层计算；
- 02/03 暂不大改参数表单。方案仿真页保留全部上传、列识别、容量范围、政策、SOC、效率和寿命控件，只增加任务边界提示；
- 经济页可以先增加首屏执行/结果概览，但原经济参数工作台完整保留；
- 新增顶部经济计算按钮必须复用原 `run_economic_study()` 分支，不能复制一套新计算逻辑；
- 方案推荐和图表复核 UI 可在小范围试用后继续局部调整，本轮不扩大重构面。

本轮实现：
- `WORKFLOW_PAGE_META["欢迎页"]` 的用户展示改为 `项目启动台 / 项目启动`，内部 page key 仍保留 `欢迎页`，并新增 `项目启动` / `项目启动台` 旧状态兼容别名；
- `_render_welcome_page()` 改为项目启动台，展示输入准备、候选方案池、推荐状态、交付准备、下一步建议和项目边界；
- 02 方案仿真页新增任务边界 callout，明确外层三栏只负责组织，不改变技术仿真、储能调度或参数 key；
- 03 经济性测算页新增 `_render_economy_task_overview()`，首屏显示技术结果、经济执行状态、结果回馈，并提供顶部 `计算经济性 V1` 按钮；
- 顶部 `run_economy_v1_top` 和原底部 `run_economy_v1_all` 共用同一段经济计算逻辑；
- 新增 `docs/ui/UI_IMPLEMENTATION_MAPPING_20260606.md`，记录原型区块到正式 UI/结果对象/底层函数的映射和后续护栏。

验证：
- `python -m py_compile src/green_direct/ui/app.py` 通过；
- `python -m pytest tests/test_ui_import.py`：22 项通过；
- `python -m pytest tests/test_visualization_smoke.py tests/test_chart_data.py`：11 项通过；
- 浏览器验证 01 项目启动台、02 方案仿真边界提示、03 Demo 后经济执行区正常渲染；
- 浏览器点击 03 顶部 `计算经济性 V1` 后，经济计算完成，推荐和图表状态变为可查看。

### 2026-06-08 UI 映射自查：批量电价曲线与图表复核结构

用户反馈批量导入中的电价曲线不能识别，并追问经济性参数区是否忘记了电价曲线导入入口；同时指出图表概览中关键指标与政策底线关系不清、容量配置柱状图表达一般、典型日/能量流向不应藏在高级折叠区。

本轮判断：
- 既定口径仍是下网电价曲线作为项目级输入在“方案仿真”页上传，经济性页自动使用，不在经济性页二次上传；
- 现有 UI 的问题不是底层计算未接入，而是批量上传入口只识别负荷、光伏、风电，导致用户把电价曲线一起上传时被提示未识别；
- 经济性页需要更清楚展示“当前价格来源”和“曲线对齐诊断”，否则用户难以判断曲线是否真的参与后续计算；
- 图表概览不应只用普通柱状图展示关键指标，应直接表达政策底线余量/缺口；
- 容量配置不适合继续用混单位横向柱状图作为主表达，更适合用容量指纹矩阵；
- 典型日、能量流向和经济性复核属于图表模块核心，不应默认藏在高级折叠区；
- 嵌入的完整图表复核不应再重复一套“方案总览”和方案选择，应尽量复用图表概览页的方案组合。

本轮实现：
- `src/green_direct/ui/app.py` 的批量上传入口改为“批量上传项目曲线文件”，可同时识别三条技术 CSV 和一条项目级下网电价曲线 CSV/XLSX/XLSM；
- 技术曲线仍只纳入负荷、光伏、风电 CSV，不支持的技术曲线文件类型只做 UI 提示，不进入技术仿真；
- 批量识别到的下网电价曲线保存到 `project_price_curve_data` / `project_price_curve_meta`，经济性页继续只读自动使用；
- `economy_v1_result` 保存 `price_curve_diagnostics`，经济性页展示“价格曲线对齐诊断”；
- 图表概览主图改为“政策底线余量矩阵”和“容量配置指纹矩阵”；
- `render_chart_analysis()` 增加外部方案组合和当前方案参数，图表概览页不再把详细图表复核放进高级折叠区，且嵌入时不重复展示“方案总览”页签；
- 新增 `docs/ui/UI_MAPPING_SELF_AUDIT_20260608.md`，记录本次自查、已改项和后续计划；
- 更新 `docs/ui/UI_IMPLEMENTATION_MAPPING_20260606.md`，补充 2026-06-08 的映射变化。

验证：
- `python -m py_compile src/green_direct/ui/app.py src/green_direct/visualization/chart_ui.py` 通过；
- `python -m pytest tests/test_ui_import.py tests/test_price_curves.py tests/test_study_runner.py`：36 项通过；
- `python -m pytest tests/test_ui_import.py tests/test_visualization_smoke.py tests/test_chart_data.py`：36 项通过。
- 本地浏览器验收走通 Demo 方案仿真、经济性 V1、图表概览；图表页可见“政策底线余量矩阵”“容量配置指纹矩阵”和“详细图表方案”，截图见 `docs/ui/audit-20260606-product-design/screenshots/49-streamlit-20260608-chart-overview-waited.png`。

后续计划：
- 将价格曲线来源、识别字段、对齐模式写入简版报告和图表包 meta；
- 在经济性页增加“价格来源分解”卡片，明确曲线提供下网账单组分，网页仍提供绿电结算价、上网电价、环境价值和税率；
- 继续收敛 `chart_ui.py` 内部 selector，长期让图表模块只有一套方案选择状态；
- 浏览器验收批量上传三条技术曲线和一条下网电价曲线的完整经济性流程。

### 2026-06-08 图表概览细节修正：弃电率、容量结构和详细方案选择

用户继续反馈图表概览细节：
- 政策底线余量矩阵应把弃电率放上去；
- “容量配置指纹矩阵”命名奇怪，且色带最高值过深；
- 嵌入详细图表区的“图表分析：方案图谱”“当前图表”等标题与页面不匹配；
- 详细图表方案切换不够明显，且只看方案编号无法判断具体风光储配置；
- 默认应看推荐的几个方案，但其他任一已计算方案也要能选。

本轮判断：
- 弃电率应进入主矩阵，但当前 `PolicyParams` 没有弃电率上限输入，因此不伪造政策红线，按“低优运行指标”展示；
- 容量主图更适合叫“容量配置结构矩阵”，而不是“指纹矩阵”；
- 详细图表复核应作为图表页的内生区域，不应再显示旧独立组件的 hero 标题；
- 方案选择要分成两个层级：上方推荐/加入方案用于组合对比；下方“详细图表方案”可从全部已计算方案中选择。

本轮实现：
- 政策底线矩阵新增 `curtail_rate` 弃电率列；
- 容量矩阵标题改为“容量配置结构矩阵”，色带改为更柔和的浅蓝区间；
- 图表页方案组合选择和详细方案选择下方都展示 `scenario_id` 与光伏、风电、储能功率/容量文字；
- “详细图表方案”改为从全部已计算方案中选择，默认仍取推荐组合第一项；
- 嵌入 `render_chart_analysis()` 时关闭旧 hero，当前方案条改为“当前复核方案”。

验证：
- `python -m py_compile src/green_direct/ui/app.py src/green_direct/visualization/chart_ui.py` 通过；
- `python -m pytest tests/test_ui_import.py tests/test_visualization_smoke.py tests/test_chart_data.py`：36 项通过。
- 完整相关测试 `python -m pytest tests/test_ui_import.py tests/test_price_curves.py tests/test_study_runner.py tests/test_visualization_smoke.py tests/test_chart_data.py`：47 项通过；
- 本地浏览器验收 Demo → 经济性 V1 → 图表概览通过，确认弃电率列、容量配置结构矩阵、全部方案详细下拉和旧 hero 移除；截图见 `docs/ui/audit-20260606-product-design/screenshots/51-streamlit-20260608-chart-overview-tuned.png`。

### 2026-06-08 指定单方案仿真与图表方案按钮切换

用户继续反馈：
- 02 方案仿真缺少“指定某个特定风光储配置计算”的入口；
- 数据曲线区和其他参数区不必等宽，导入曲线区可以更紧凑；
- 05 图表概览里的推荐方案卡片看起来能点，但实际不能切换详细图表，只能用下拉框；
- 绿电接入前后的负荷到户综合单价、绿电占比、绿电结算价格、下网加权平均电价、下网比例等指标很重要，但绿电后综合到户价涉及经济口径，不能未经确认直接写死；
- 遍历计算偏慢，后续需要评估并行、剪枝和结果存储。

本轮判断：
- 指定单方案不应新建第二套计算器，而应作为“候选方案池”的另一种输入方式，将指定风光储容量转成只含 1 个候选的 `scenario_grid`，继续走 `run_technical_study()` / `run_batch()` / `run_single_scenario()` 原链路；
- 该改动不改变储能调度、政策指标、经济计算或推荐排序口径；
- 图表方案卡片必须是 Streamlit 原生按钮，而不是不可点击 HTML；按钮点击不能直接修改已经实例化的 selectbox key，需写入 pending key 并在下一次渲染前同步；
- “绿电前后综合到户价”需要先确认展示口径：尤其是固定价模式下使用哪个下网到户价近似，以及绿电后是否按含税现金口径把自发自用绿电结算价和仍缴费用纳入分子。

本轮实现：
- 02 方案仿真页的候选方案池新增 `容量范围遍历 / 指定单方案` 单选模式；
- 指定单方案模式新增光伏容量、风电容量、储能功率、储能容量 4 个输入，自动推导储能时长 `bess_energy / bess_power`；
- 指定单方案校验：至少需要光伏或风电容量；储能功率为 0 时储能容量必须为 0；储能功率大于 0 时储能容量也必须大于 0；
- 数据曲线、候选方案池、政策约束三栏宽度调整为 `[0.9, 1.22, 1.0]`，让导入曲线区更紧凑、候选方案池更宽；
- Demo 技术曲线加载会忽略 samples 目录中的价格曲线模板，避免把 `price_curve_template_down_grid.csv` 提示为未知技术曲线；
- 05 详细图表复核的方案卡片改为真实按钮，点击后通过 `_chart_overview_pending_detail_scenario` 同步到 `chart_overview_active_detail_scenario`，避免 Streamlit session_state 实例化后修改错误；
- 新增浏览器验收截图 `docs/ui/audit-20260606-product-design/screenshots/streamlit-20260608-chart-button-s0027.png`。

验证：
- `python -m py_compile src/green_direct/ui/app.py` 通过；
- `python -m pytest tests/test_ui_import.py tests/test_visualization_smoke.py tests/test_chart_data.py`：39 项通过；
- 本地 Streamlit `http://localhost:8502` 验收：02 页切换到“指定单方案”后显示 4 个指定容量输入，当前表单方案数为 1，使用 Demo 曲线后可完成单方案技术仿真；
- 本地 Streamlit 验收：一键 Demo 生成 27 个方案，经济性 V1 完成后进入 05，点击 S0027 方案按钮后，下拉框和“当前复核方案”均同步到 S0027，未再出现 `st.session_state... cannot be modified after the widget ... is instantiated` 错误。

待用户确认：
- 绿电前综合到户电价是否定义为 `sum(总负荷电量 * 下网到户含税现金价) / 总负荷电量`；
- 绿电后综合到户电价是否定义为 `(下网电量 * 下网到户含税现金价 + 自发自用绿电量 * (绿电结算价含税 + 自发自用仍缴输配电/基金等费用)) / 总负荷电量`；
- 固定价模式下，如果没有逐小时下网曲线，是否用当前“外部购电净成本单价/负荷侧可减少购网费用单价”近似绿电前下网到户价，还是需要新增一个明确的“固定下网到户综合电价”输入。

后续性能计划：
- P0：先通过“指定单方案”和更窄方案池减少不必要遍历；
- P1：在 UI 中强化方案数预估和慢速提醒，避免用户无意生成上万组合；
- P2：评估 `run_batch()` 的可选并行执行。建议先做显式开关或 `workers=auto` 参数，保持默认串行，确保输出顺序、错误表、progress callback 和内存占用可控后再启用；
- P3：中长期引入结果存储/按需逐小时明细，避免每次页面切换都持有过多方案的 8760/8784 明细。

### 2026-06-09 绿电前后到户综合价口径确认与 UI 落地

用户确认绿电接入前后负荷到户综合电价口径：
- 绿电前：有逐时下网电价时，按 `sum(逐时负荷电量 * 逐时下网到户含税价) / 总负荷电量`；无逐时下网电价时，使用用户提供的 `下网到户含税现金价`。
- 绿电后：有逐时下网电价时，按 `(sum(逐时下网电量 * 逐时下网到户含税价) + 自发自用绿电量 * (绿电结算价含税 + 输配电价 + 政府基金及附加)) / 总负荷电量`；无逐时下网电价时，按 `(下网电量 * 下网到户含税价 + 自发自用绿电量 * (绿电结算价含税 + 输配电价 + 政府基金及附加)) / 总负荷电量`。

本轮判断：
- 该指标是负荷侧最关心的“接入绿电前后账单变化”展示口径，不等同于同一主体经济性中的 `net_avoided_grid_cost_price`，也不应复用“负荷侧可减少购网费用单价”近似。
- 曲线模式必须在 `price_curves.py` 内按逐时台账聚合，不能在 UI 层用年度汇总近似；固定价模式可在服务层读取 `total_load_energy`、`grid_import_energy`、`self_use_energy` 计算。
- 新增字段只作为经济汇总、推荐和图表展示字段，不改变技术调度、BESS 约束、FIRR 现金流主体公式或推荐排序核心口径。
- 03/04/05 都应展示同一套字段：绿电前综合到户价、绿电后综合到户价、绿电占比、绿电结算价、绿电后绿电到户价、下网加权价、下网比例和价差。

本轮实现：
- `src/green_direct/economy/price_curves.py` 的逐时曲线派生结果新增 `down_grid_landed_price_with_vat`、`green_self_use_landed_price_with_vat`，并在逐方案价格汇总中新增绿电前后到户价、价差、下网加权价和相关电量字段。
- `src/green_direct/services/study_runner.py` 新增固定价模式到户价汇总，并把同一组 `landed_price_summary` 合并进电源侧和同一主体经济性结果；曲线模式沿用逐时曲线汇总。
- `src/green_direct/recommendation/recommendation_engine.py` 允许推荐组合携带到户价展示字段，便于推荐卡片直接展示。
- `src/green_direct/ui/app.py` 的 03 经济性测算页新增“负荷到户电价展示口径”输入区：固定下网到户含税现金价、绿电后仍缴输配电价、绿电后仍缴政府基金及附加；03 结果区新增“负荷到户电价对比”卡片。
- 04 方案推荐卡片新增绿电前/后到户价、绿电结算价、下网加权价和下网比例。
- 05 图表概览页把经济汇总中的到户价字段合并到图表组合 summary，新增“方案组到户电价对比”卡片，并继续保留政策底线余量矩阵、容量配置结构矩阵和详细图表复核切换。
- 浏览器验收截图保存到 `docs/ui/audit-20260606-product-design/screenshots/streamlit-20260609-chart-overview-landed-cards.png` 和 `docs/ui/audit-20260606-product-design/screenshots/streamlit-20260609-landed-price-chart-overview.png`。

验证：
- `python -m py_compile src\green_direct\economy\price_curves.py src\green_direct\services\study_runner.py src\green_direct\recommendation\recommendation_engine.py src\green_direct\ui\app.py` 通过。
- `python -m pytest tests\test_price_curves.py tests\test_study_runner.py`：13 项通过。
- `python -m pytest tests\test_ui_import.py tests\test_visualization_smoke.py tests\test_chart_data.py tests\test_price_curves.py tests\test_study_runner.py`：54 项通过。
- `python -m pytest -q`：157 项通过。
- 本地 Streamlit `http://localhost:8502` 浏览器验收：Demo 技术仿真完成，528 个方案 / 62 达标；03 经济性测算出现新增固定到户价输入并成功渲染“负荷到户电价对比”；04 推荐卡片展示到户价字段；05 图表概览展示方案组到户价卡片，且点击 S0162 方案按钮后详细图表切换正常。

### 2026-06-09 图表交付修正：新增 Word 友好 PNG 图片包

用户反馈网站下载的图表不是所见即所得，也不方便直接放入 docx；网页内图表效果可以接受，但导出图片需要结合 A4 页面比例调整长宽，尽量保持显示效果和信息完整。用户同时提醒 GPT 讨论稿未读取本地文件，必须审慎使用。

本轮判断：
- 现有 `chart_html_{scenario_id}.zip` 只包含 Plotly HTML 和 meta，适合网页交互复核，不适合作为 Word 插图交付物；
- Plotly HTML 默认随浏览器容器响应式调整，无法保证插入 docx 后保持网页视觉比例；
- 图表图片导出应作为交付中心的独立包，与 HTML ZIP 并存：HTML 用于交互复核，PNG 用于 Word / 报告插图；
- PNG 导出必须复用现有图表清单和 `ChartResult`，只读消费技术、经济和推荐结果，不改变底层调度、经济公式或推荐排序。

本轮实现：
- `src/green_direct/visualization/export_charts.py` 新增 `ChartImageExportProfile`、`DOCX_A4_PORTRAIT_PROFILE` 和 `chart_to_png_bytes()`，导出前复制 Plotly figure 并应用报告版宽高，避免污染网页展示图；
- `src/green_direct/ui/app.py` 抽出共享图表清单，HTML ZIP 和 PNG ZIP 使用同一批图表：当前方案政策图、四季典型日、SOC、电网交换、月度流向、热力图和推荐组合多方案对比；
- 06 下载页新增 `chart_png_docx_{scenario_id}.zip`，包含 PNG、每图 meta、`chart_manifest.csv` 和 `README.md`；
- PNG 默认面向 A4 纵向 Word 正文，建议 16 cm 宽插入，画布宽度 1800px；典型日图 1300px 高，全年 / 热力图 1000px 高，月度 / 多方案图 900px 高；
- `requirements.txt` 将 Plotly 下限调整为 `plotly>=6.1`，并新增 `kaleido>=1.0`；如缺少 Kaleido 或可用 Chrome / Chromium，UI 会提示 PNG 失败原因，HTML ZIP 仍可下载；
- `docs/CHART_MODULE_CURRENT_LOGIC.md` 更新 HTML / PNG 图表包分工和静态图片环境要求。

验证：
- `python -m py_compile src/green_direct/ui/app.py src/green_direct/visualization/export_charts.py` 通过；
- `python -m pytest tests/test_ui_import.py tests/test_visualization_smoke.py tests/test_chart_data.py tests/test_chart_contracts.py` 通过。

### 2026-06-09 启动入口修复：避开端口冲突与旧 Streamlit 状态

用户反馈新增 PNG 图表包后网页无法进入，报错为 `ImportError: cannot import name 'DOCX_A4_PORTRAIT_PROFILE'`，并怀疑再次与其他项目网页地址冲突。

本轮判断：
- 当前源码中 `DOCX_A4_PORTRAIT_PROFILE` 已存在，新的 Python 进程可正常导入 `green_direct.visualization.export_charts` 和 `green_direct.ui.app`；
- 问题不是该符号在源码中缺失，而是本机仍有旧 Streamlit 进程占用 8501 / 8502：8502 为本项目旧实例，8501 为无法确认归属的裸 `app.py` 实例；
- 旧 `START_GREEN_DIRECT_APP.bat` 只要发现 8501 有监听就直接打开浏览器并退出，可能把用户带到其他项目、旧实例或错误状态页面；
- 启动入口应默认从 8503 起选端口，遇到其他项目占用时自动向后查找，并且只停止可确认属于本项目的旧 Streamlit 进程。

本轮实现：
- 新增 `scripts/start_green_direct_app.ps1` 作为统一开发启动器：启动前做导入自检，检查 `DOCX_A4_PORTRAIT_PROFILE`、`streamlit` 和 `green_direct.ui.app`；优先使用 `.venv\Scripts\python.exe`；只停止命令行中可识别为本项目的旧 Streamlit 进程；默认从 8503 到 8515 自动选择空闲端口；
- `START_GREEN_DIRECT_APP.bat` 改为薄包装，调用统一 PowerShell 启动器，不再盲目打开 8501；
- `scripts/run_streamlit_8503.cmd` 去除硬编码绝对路径，改为调用统一启动器；
- `packaging/portable/启动绿电直连测算工具.bat` 改为从 8503 到 8515 选择空闲端口，不再因为 8501 被占用就直接打开；
- `packaging/pyinstaller/run_green_direct_app.py` 默认端口改为 8503，并在 8503-8515 范围内自动选择空闲端口。

验证：
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_green_direct_app.ps1 -CheckOnly` 通过，识别到本项目旧进程并选择 `http://localhost:8503`；
- 新启动器已停止本项目旧 8502 实例，并在 `http://localhost:8503` 启动干净服务；
- `Invoke-WebRequest http://localhost:8503` 返回 200，页面内容未包含 `ImportError` / `Traceback` 标记；
- `python -m py_compile src/green_direct/ui/app.py src/green_direct/visualization/export_charts.py packaging/pyinstaller/run_green_direct_app.py` 通过；
- `python -m pytest tests/test_ui_import.py tests/test_visualization_smoke.py tests/test_chart_data.py tests/test_chart_contracts.py` 通过。

### 2026-06-10 C 盘清理后的 Streamlit HTML/CSS 渲染兼容修复

用户反馈清理 C 盘后，`http://localhost:8503/` 页面把 `<style>` 和 `<div class="...">` 直接当文本显示，侧栏和工作台样式失效。
本轮判断：
- 当前监听 `8503` 的进程确认为本项目 `src/green_direct/ui/app.py`，不是其他项目占用；
- `.venv` 中 Streamlit 为 `1.57.0`，项目原来大量使用 `st.markdown(..., unsafe_allow_html=True)` 注入纯 HTML/CSS；
- 后端 `streamlit.testing.v1.AppTest` 显示这些元素的 `allow_html=True`，但浏览器端仍可能裸显，说明应按新版官方推荐把纯 HTML/CSS 走 `st.html`；
- 不改变技术仿真、经济性、推荐排序或图表计算逻辑。
本轮实现：
- `src/green_direct/ui/app.py` 新增 `_install_html_render_compat(st)`；
- 当当前 Streamlit 提供 `st.html` 时，将 `unsafe_allow_html=True` 的纯 HTML/CSS 输出路由到 `st.html`，旧版没有 `st.html` 时保留原 `st.markdown` 行为；
- 同时兼容 `DeltaGenerator.markdown`，覆盖列容器等局部容器中的 HTML 片段；
- 已重启统一启动器，当前本项目服务运行在 `http://localhost:8503`；此前检测到的 `8501` 裸 `app.py` 不作为本项目目标入口处理，最终监听状态只保留本项目 `8503`；
- 后续用户上传文件时出现 `Failed to fetch dynamically imported module .../static/js/axios...js`，经检查该 JS 分块在服务器端可正常返回 `200`，全部 Streamlit JS 分块也均可访问，判断为浏览器旧缓存/动态模块状态问题，优先通过强制刷新或重开入口恢复；
- `scripts/start_green_direct_app.ps1`、`packaging/portable/启动绿电直连测算工具.bat` 和 `packaging/pyinstaller/run_green_direct_app.py` 均将 `TEMP/TMP/TMPDIR` 指向项目内 `.runtime/tmp`，减少上传、导出和临时文件对 C 盘临时目录的占用。
- `requirements.txt`、`requirements-runtime.txt` 和 `pyproject.toml` 将 Streamlit 依赖收窄为 `streamlit>=1.57,<1.58`，避免未来重装环境时静默升级到未验证的新前端版本。
验证：
- `python -m py_compile src/green_direct/ui/app.py` 通过；
- `python -m pytest tests/test_ui_import.py -q`：31 项通过；
- `python -m pytest -q`：160 项通过；
- AppTest 运行首页无异常，HTML/CSS 片段不再作为 markdown 元素输出；
- Headless Chrome DOM 检查未再发现裸显的 `&lt;style&gt;` / `&lt;div class=` 标记。
- `http://localhost:8503/static/js/axios.bXBZHvsg.js` 返回 `200`，全部 156 个 Streamlit JS 分块返回 `200`；
- 重启后启动日志显示 `Temp: Z:\Projects\20260515_8760\.runtime\tmp`；
- `python -m py_compile packaging/pyinstaller/run_green_direct_app.py src/green_direct/ui/app.py` 通过；
- `python -m pytest tests/test_ui_import.py -q`：31 项通过。

### 2026-06-10 Streamlit 前端分块与 PNG 导出环境全面排查

用户继续反馈页面存在多处细节问题：方案仿真、经济和图表页出现 `TypeError: Failed to fetch dynamically imported module` 红框，涉及 `Metric.*.js`、`PlotlyChart.*.js` 等 Streamlit 前端分块；下载页提示部分 PNG 未能导出。

本轮判断：
- 新开浏览器标签完整跑通首页、Demo 技术仿真、经济性 V1、图表概览和下载页，未复现 `Metric` / `PlotlyChart` 动态模块红框；
- 正确的前端分块 URL 可返回 `application/javascript`，例如 `PlotlyChart.B6LaAfIh.js`、`Metric.CFtF4sc2.js`、`axios.bXBZHvsg.js`；
- 若旧标签继续请求旧 hash 或肉眼相近但不存在的分块名，Streamlit 会回落返回 HTML 首页，浏览器动态 import 该 HTML 时就会显示红色模块加载错误；因此旧标签需要强制刷新或重开入口；
- PNG 失败是真问题：当前 `.venv` 缺少 `kaleido`，即使本机有 Chrome，也无法导出 Plotly 静态 PNG；
- Streamlit 1.57 已开始提示 `use_container_width` 弃用，应改成 `width="stretch"`，减少后续升级噪音和潜在兼容问题。

本轮实现：
- `src/green_direct/ui/app.py` 和 `src/green_direct/visualization/chart_ui.py` 全量替换旧 `use_container_width=True` 为 `width="stretch"`；
- `src/green_direct/visualization/export_charts.py` 在 PNG 导出前自动查找本机 Chrome / Edge，并设置 `BROWSER_PATH` 供 Kaleido 使用；
- `scripts/start_green_direct_app.ps1`、`packaging/portable/启动绿电直连测算工具.bat` 和 `packaging/pyinstaller/run_green_direct_app.py` 启动时自动设置 `BROWSER_PATH`，并继续将 `TEMP/TMP/TMPDIR` 指向项目内 `.runtime/tmp`；
- `requirements-runtime.txt` 和 `pyproject.toml` 补齐 `plotly>=6.1` 与 `kaleido>=1.0`，与 PNG 图表包能力保持一致；
- 当前机器已安装 `kaleido==1.3.0` 到项目 `.venv`，安装缓存放在 `Z:\Projects\20260515_8760\.runtime\pip-cache`，避免继续占用 C 盘 pip 缓存。

验证：
- `python -m py_compile src/green_direct/ui/app.py src/green_direct/visualization/chart_ui.py src/green_direct/visualization/export_charts.py packaging/pyinstaller/run_green_direct_app.py` 通过；
- `python -m pytest tests/test_chart_contracts.py tests/test_visualization_smoke.py tests/test_ui_import.py -q`：42 项通过；
- `python -m pytest -q`：160 项通过；
- `pip check`：No broken requirements found；
- 直接调用 `chart_to_png_bytes()` 已生成 PNG 字节，自动设置 `BROWSER_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe`；
- 统一启动器重启后服务运行于 `http://localhost:8503`，日志显示 `Temp: Z:\Projects\20260515_8760\.runtime\tmp` 和 Chrome 路径；
- 浏览器完整链路验收：Demo 结果 27 个方案 / 22 达标，经济性测算完成，图表概览 `redBoxCount=0`，下载页生成 `下载 Word 友好 PNG ZIP` 按钮且未出现“部分 PNG 未能导出”。

### 2026-06-10 PNG 图表包生成交互修正：避免复选框长时间转圈

用户反馈 06 下载报告页勾选“准备所选方案 Word 友好 PNG ZIP”后长时间转圈，看起来没有反应。

本轮判断：
- PNG ZIP 生成不是前端卡死，而是后台逐张调用 Kaleido / headless Chrome 渲染高分辨率 Plotly 图片；
- 一个图表包会包含当前方案政策图、四季典型日、SOC、电网交换、月度流向、热力图和多方案对比等十余张图，首次渲染本来就可能需要几十秒到数分钟；
- 旧 UI 用 checkbox 触发重任务不合适：checkbox 保持选中后，Streamlit 页面重跑时容易重复进入生成逻辑，用户只能看到 spinner，缺少进度和完成后的缓存状态。

本轮实现：
- 06 下载页将“准备所选方案 Word 友好 PNG ZIP”复选框改为“生成 Word 友好 PNG ZIP”按钮；
- 新增导出签名 `_chart_png_docx_export_signature()`，按当前方案、对比范围、逐小时数据范围和图片版式识别缓存；
- 生成后的 ZIP、warnings 和文件名存入 `st.session_state["chart_png_docx_export"]`，当前导出范围不变时页面重跑不再重复生成；
- `_build_chart_png_docx_zip()` 支持 `progress_callback`，UI 中显示进度条和“已完成 N/M：图表名”；
- 页面增加说明：首次生成会逐张调用 Kaleido/Chrome 渲染高分辨率图片，通常需要几十秒到数分钟；生成后会缓存。

验证：
- `python -m py_compile src/green_direct/ui/app.py` 通过；
- `python -m pytest tests/test_ui_import.py tests/test_chart_contracts.py -q`：35 项通过；
- `python -m pytest -q`：160 项通过；
- 浏览器验收：Demo 技术仿真后进入 06，图表包区域出现“生成 Word 友好 PNG ZIP”按钮，不再显示旧复选框；页面包含首次生成耗时与缓存说明，未出现动态模块红框。

### 2026-06-10 Streamlit 重启后页面重置与下载失效修正

用户反馈网页“整个都重置了”，Chrome 下载记录中出现 zip “无法从网站上提取文件”。

本轮判断：
- 直接原因是本轮修复 PNG 生成交互时重启了 Streamlit 服务；
- 当前软件仍以 Streamlit `session_state` 作为主要会话结果存储，服务重启会清空内存中的 `batch_result`、经济结果、下载按钮 payload 和图表包缓存；
- Chrome 下载链接依赖当前 Streamlit 会话内存，服务重启或旧会话断开后，正在下载或尚未点击完成的 zip 链接会失效；
- 长期方向仍应引入正式 `ResultStore`，但当前可先用项目本地运行快照降低重启损失。

本轮实现：
- 新增项目本地快照文件 `.runtime/latest_session_snapshot.pkl`，保存最近一次关键结果；
- 快照包含 `study_result`、`batch_result`、`config_snapshot`、经济结果、推荐输入、曲线状态和已生成的 PNG 图表包缓存；
- 技术仿真完成、经济性 V1 完成、PNG ZIP 生成完成后自动写入快照；
- App 启动时若当前会话没有 `batch_result`，自动从本地快照恢复，并提示“已从项目本地快照恢复最近一次测算结果”；
- `.runtime/` 已加入 `.gitignore`，快照和临时文件留在项目盘，不进入版本库。

验证：
- `python -m py_compile src/green_direct/ui/app.py` 通过；
- `python -m pytest tests/test_ui_import.py -q`：32 项通过；
- `python -m pytest -q`：161 项通过；
- 已用 Demo 数据写出 `Z:\Projects\20260515_8760\.runtime\latest_session_snapshot.pkl`；
- 重启服务后浏览器验证自动恢复为 27 个方案 / 22 达标，并显示恢复提示，未出现动态模块红框。

### 2026-06-10 图表网页与 ZIP 导出一致性修正

用户反馈网页端和 `chart_png_docx` ZIP 图表存在配色、阈值表达、图名和图表项缺失问题：多色图在 PNG 中变黑，政策阈值用点不直观，季节典型日文件名夹带日期，且需要补充关键运行日和 8760 全年图。

本轮判断：
- PNG 发黑的主要原因是部分 Plotly Express 图依赖默认主题配色，静态 Kaleido 导出时没有稳定继承网页端色板；
- 网页端 24H 运行策略图与导出 S03 图不是同一套构图，导致网页看到的效果和 ZIP 图片不一致；
- 季节典型日仍应记录真实选中日期用于审计，但文件名和图表主标题不应随日期变化。

本轮实现：
- 新增 `src/green_direct/visualization/style.py`，统一网页和导出的能源色板；上网使用蓝色、下网使用中性灰，避免颜色过近；
- S02 政策指标图把“阈值”从散点改为并列对照柱；
- S03 24H 图表改为网页端同款运行策略图：正向柱为光伏/风电可发、储能放电、下网，负向柱为储能充电、上网、弃电，下方为 SOC；
- 月度来源、月度新能源去向、多方案新能源去向、容量/政策对比、弃电率散点和年度热力图均使用显式颜色或色阶，避免 PNG 静态导出变黑；
- 图表 ZIP 清单新增五类关键运行日和全年 8760/8784 小时运行曲线；
- 季节典型日导出文件名改为 `typical_spring` / `typical_summer` 等稳定名称，真实日期只写入 meta；
- PNG ZIP 缓存签名升级，避免页面恢复后继续下载旧风格缓存包；
- `docs/CHART_MODULE_CURRENT_LOGIC.md` 更新网页/导出同源、稳定命名和新增图表项口径。

验证：
- `python -m py_compile src/green_direct/visualization/style.py src/green_direct/visualization/single_scenario_charts.py src/green_direct/visualization/multi_scenario_charts.py src/green_direct/visualization/heatmap_charts.py src/green_direct/visualization/chart_ui.py src/green_direct/visualization/export_charts.py src/green_direct/ui/app.py` 通过；
- `python -m pytest tests/test_chart_contracts.py tests/test_visualization_smoke.py tests/test_ui_import.py -q`：44 项通过；
- `python -m pytest -q`：162 项通过。

### 2026-06-10 PNG 后台生成、经济参数紧凑化与图表表达二次修正

用户继续反馈：06 页生成附图时切换页面会打断，PNG ZIP 生成速度仍偏慢；03 页经济性基本参数区域过高，单位造价和运维成本缺少快速微调；S09 电网交换功率图口径看起来不对；S10 全年曲线把 SOC、弃电、上网和其他功率线混在一起过乱；S02 政策阈值用并列柱仍不够直观。

本轮判断：
- PNG ZIP 属于重型静态图导出，不应由一个前台 Streamlit rerun 长时间占住页面；
- Plotly 6.7 已支持 `plotly.io.write_images()` 批量图片导出，可优先用于多图 PNG 提速，失败时再逐张回退；
- S09 展示标题采用“上网为正、下网为负”，因此图中净交换应显式按 `grid_export_power - grid_import_power` 展示；原始 `grid_exchange_power` 保留为导出复核字段，不改变调度台账；
- S10 更适合按“供需与下网 / 上网与弃电 / SOC”分面展示，避免所有指标挤在同一个坐标轴；
- S02 政策阈值适合用每个指标上的水平阈值线表达，实际值保留柱状图。

本轮实现：
- 06 页 PNG ZIP 生成改为后台线程任务，用户可以切换到其他页面继续操作；返回下载页时自动轮询任务状态并读取已完成结果；
- PNG 下载按钮增加 `on_click="ignore"`，减少点击下载导致的额外页面重跑；
- PNG ZIP 底层优先使用 `charts_to_png_bytes_batch()` 批量渲染，异常时写入 warnings 并逐张回退；
- 03 页经济性参数工作台压缩标题、列距和输入框高度，Year 0 投资、成本费用、储能更换更紧凑；
- 风电单位造价默认值改为 5000 元/kW，光伏单位造价默认值改为 2800 元/kW；常调用的风/光/储单位造价、风/光/储运维成本提供贴近输入框的紧凑 `-` / `+` 微调控件，步长按字段内部定义，不再用大面积数字按钮或额外说明文字占版面；
- S09 电网交换功率图改为显式净交换 `上网 - 下网`；
- S10 全年 8760/8784 小时运行曲线改为三行分面；
- S02 政策指标图改为“实际值柱 + 阈值线 + 阈值标注”。

验证：
- `python -m py_compile src/green_direct/ui/app.py src/green_direct/visualization/export_charts.py src/green_direct/visualization/single_scenario_charts.py src/green_direct/economy/economic_inputs.py` 通过；
- `python -m pytest -q`：164 项通过；
- 使用真实本地快照导出 PNG ZIP：20 张 PNG、0 个 warnings、约 21 秒；
- 后台任务提交/轮询路径实测完成并写回缓存，约 17 秒；
- 浏览器验收：03 页默认风电造价 5000、光伏造价 2800，单位造价和运维成本使用紧凑 `-` / `+` 微调控件且不再显示步长说明；06 页显示后台生成说明和重新生成提示，未出现动态模块红框。

### 2026-06-10 交互流畅性与状态去重修正

用户继续反馈：顶部状态条和侧边栏/页面标题重复，06 页点击 PNG 生成后缺少明确进度和结果，03 页经济参数自定义 `-` / `+` 控件仍然不够紧凑且点击反应慢。

本轮判断：
- 当前页面已有侧栏导航、侧栏流程状态和页面标题，顶部再展示“当前模块 / 流程状态 / 数据时间”属于重复信息，会挤压主要工作区；
- 经济参数不应使用自定义按钮修改 `session_state` 再强制整页 rerun，常规数字输入优先使用 Streamlit 原生 `number_input`，交互和容量遍历保持一致；
- PNG ZIP 后台任务需要在同一卡片中展示“运行中 / 完成 / 失败”和耗时，不能只给一次性提示。

本轮实现：
- 停止渲染顶部状态条，保留侧栏导航、侧栏流程状态和页面主标题；
- 03 页常调经济参数改为原生 `number_input`：单位造价步长 100，运维成本步长 1，移除自定义贴边按钮；
- 经济参数输入高度进一步压缩，储能更换收到“高级：储能更换”折叠区，优先让常用投资和成本输入在首屏内完成；
- 06 页 PNG ZIP 后台任务新增共享进度状态，图表包区域使用局部刷新，每 2 秒刷新任务状态，运行中展示阶段、耗时和完成数，完成后直接出现下载按钮；
- 不改变技术仿真、经济计算、推荐排序或图表计算口径。

验证：
- `python -m py_compile src/green_direct/ui/app.py` 通过；
- `python -m pytest tests/test_ui_import.py::test_chart_png_docx_background_job_stores_finished_result tests/test_ui_import.py::test_chart_png_docx_zip_contains_png_manifest_and_matches_html -q`：2 项通过；
- `python -m pytest tests/test_ui_import.py tests/test_economy_v1.py -q`：51 项通过。

### 2026-06-10 单方案容量输入去冗与排版修正

用户反馈 02 页“指定单方案”下的容量输入字段反复出现“指定”，且四列排布稀疏、标签换行导致视觉歪斜；03 页经济性参数区仍有输入框撑得过宽、行列留白明显的问题。

本轮判断：
- “指定单方案”已经由单选入口表达，字段标签不需要再次写“指定”；
- 单方案配置只有四个核心参数，放成四列会挤压中文标签，改成两行两列更稳定，也更接近参数面板；
- 03 页基础经济参数应避免三列撑满全屏，Year 0 建设投资的常用字段应尽量在同一行完成，减少空白行；
- 该修改只影响 UI 文案和布局，不改变候选方案生成、储能时长推导、校验或技术仿真链路。

本轮实现：
- 候选方案池说明改为“支持容量范围遍历，也支持单方案配置”；
- 单方案输入字段改为“光伏容量、风电容量、储能功率、储能容量”；
- 单方案输入从一行四列改为两行两列，避免长标签换行和控件参差；
- 03 页经济性参数工作台的基本参数行改为四列节奏，Year 0 建设投资六个输入压到同一行，减少大块空白和错位感。

验证：
- `python -m py_compile src/green_direct/ui/app.py` 通过；
- `python -m pytest tests/test_ui_import.py -q`：33 项通过；
- `python -m pytest -q`：164 项通过；
- 浏览器验收 `http://localhost:8503`：02 页“指定单方案”下四个字段显示为两行两列，页面不再包含“指定光伏容量 / 指定风电容量 / 指定储能功率 / 指定储能容量 / 指定单个风光储配置”；03 页基本参数保持同一行节奏，Year 0 六个建设投资输入已压到同一行。

### 2026-06-10 经济参数工作台拆卡与表单批处理

用户进一步指出：不要过度守旧，原来的结构如果不服务主要目标就应该改；03 页经济参数不应继续作为一个大框堆叠所有字段，常调参数也不应每点一次就触发整页迟滞。

本轮判断：
- “保留 V0.1 字段口径”不等于“保留旧 UI 结构”。围绕当前产品目标，经济参数页的主任务是快速完成轻量经济测算并把结果交给推荐和导出；
- 03 页应按任务拆成小工作卡：运行口径、建设投资、运维成本、收入和税金、到户电价展示、高级参数；
- Streamlit 数字控件如果裸露在页面上，每次变化都会触发 rerun，页面越重越容易出现 0.7s~1s 的迟滞；经济参数应放入提交型表单，用户先在前端完成多项调整，点击“计算经济性 V1”后再统一提交；
- 高级参数保留但默认收起，不把低频字段挤占首屏；顶部只保留经济测算相关状态，不再重复展示全局模块和数据时间。

本轮实现：
- 移除 03 页“经济性参数工作台”大 expander，改为多个 bordered 小卡片；
- 顶部执行状态压缩成一行小状态条，保留“返回方案仿真 / 查看方案推荐”导航；
- 经济参数放入 `st.form("economy_v1_params_form")`，顶部和底部各提供一个表单提交按钮；
- 常调造价和运维成本继续使用原生 `number_input` 步进，但因位于表单内，编辑过程不再触发整页 rerun；
- 电费清单组价、其他经营收入和储能更换仍保留在高级折叠区，字段不丢失，计算口径不变。

验证：
- `python -m py_compile src/green_direct/ui/app.py` 通过；
- `python -m pytest tests/test_ui_import.py -q`：33 项通过；
- `python -m pytest -q`：164 项通过；
- 浏览器验证 `http://localhost:8503`：03 页旧“经济性参数工作台”大框不再出现；首屏可见运行口径、建设投资、运维成本、收入和税金，且顶部可见“计算经济性 V1”；
- 浏览器交互测量：风电单位造价从 5000 改为 5100 的前端响应约 82ms，页面保持在当前区域，不再因单次编辑整页跳动；控制台仅有刷新/重连类 `WebSocket onclose` warning，无红框模块错误。

### 2026-06-11 项目级电价曲线旧状态兼容修正

用户反馈：只上传三条 8760 风光负荷曲线、未提供电价曲线时，经济性测算仍提示“价格曲线行数 8784 与逐小时明细行数 8760 不一致”。
本轮判断：
- 6 月 4 日接入的下网电价曲线是项目级输入，并会保存到 `.runtime/latest_session_snapshot.pkl`；
- 如果上一轮或示例模板留下了 8784 行项目级电价曲线，新一轮上传 8760 技术曲线并重新仿真后，旧电价曲线状态仍可能被经济性页自动使用；
- 这不是风、光、负荷三条曲线自身不一致，而是“旧项目级电价曲线”与“当前逐小时明细”不匹配，提示对用户不够友好。

本轮实现：
- `src/green_direct/ui/app.py` 新增项目级电价曲线兼容检查；
- 打开经济性页前，若旧电价曲线行数与当前逐小时明细行数不一致，自动清除旧曲线并切回固定价/网页组价模式；
- 新技术仿真结果写入会话和本地快照前，也会清除与当前结果不兼容的旧电价曲线；
- 行数匹配时不误删用户主动上传的项目级电价曲线；
- 底层 `run_economic_study()` 显式传入不匹配价格曲线时仍保留报错，避免静默吞掉真正的数据问题。

验证：
- `python -m py_compile src/green_direct/ui/app.py` 通过；
- `python -m pytest tests/test_ui_import.py::test_incompatible_project_price_curve_is_discarded_for_current_hourly_rows tests/test_ui_import.py::test_matching_project_price_curve_is_kept_for_current_hourly_rows -q`：2 项通过；
- `python -m pytest tests/test_ui_import.py tests/test_price_curves.py tests/test_study_runner.py -q`：48 项通过。

### 2026-06-11 单方案场景下多方案散点图跳过

用户反馈：指定单方案测算后，“弃电率 vs 自发自用率”图只显示一个孤立点，不清楚图的意义。
本轮判断：
- 该图本质是多方案权衡图：横轴自发自用率，纵轴弃电率，颜色表达绿电占比，点大小表达储能容量；
- 它用于比较多组候选方案的取舍，例如“更高自发自用率是否伴随更高弃电”；
- 指定单方案时只有一个点，没有横向比较关系，不应作为主要图表展示；同时百分比坐标不应因单点自动缩放到负值或 150%。

本轮实现：
- `src/green_direct/visualization/multi_scenario_charts.py` 调整 `build_curtailment_vs_self_consumption_scatter()`；
- 当对比范围少于 2 个方案时，跳过该图并返回明确提示；
- 多方案时继续生成散点图，并将自发自用率、弃电率坐标轴固定为 0% 到 100%；
- `docs/CHART_MODULE_CURRENT_LOGIC.md` 补充 M05 单方案跳过规则。

验证：
- `python -m py_compile src/green_direct/visualization/multi_scenario_charts.py` 通过；
- `python -m pytest tests/test_visualization_smoke.py::test_multi_scenario_charts_smoke tests/test_visualization_smoke.py::test_curtailment_scatter_skips_single_scenario -q`：2 项通过；
- `python -m pytest tests/test_visualization_smoke.py tests/test_chart_contracts.py tests/test_ui_import.py -q`：49 项通过。

### 2026-06-12 价格曲线必须来自当前上传

用户反馈：只上传负荷、光伏、风电三条技术曲线时，02 / 03 页仍显示已上传项目级下网电价曲线，并在经济性测算中尝试使用 `price_curve_template_down_grid.csv`。

本轮判断：
- 根因不是三条技术曲线识别错误，而是运行时快照把旧的 `project_price_curve_data` / `project_price_curve_meta` 恢复到了新会话；
- 电价曲线属于可选经济性输入，不能像仿真结果一样从历史快照静默恢复；
- 只要用户本次没有上传电价曲线，经济性就必须回到固定价/网页组价模式；
- 02 页面向最终用户，不应常驻显示“任务边界”这类实现说明；曲线识别摘要和电价曲线说明应默认收起或放在帮助提示里。

本轮实现：
- 运行时快照不再保存或恢复项目级电价曲线；
- 新增当前会话上传标记，`_project_price_curve_data()` 只承认本次明确上传的曲线；
- 进入主流程时会清除未确认的历史电价曲线状态，并同步清空旧经济性/推荐结果；
- Demo 或普通技术仿真如果没有同时上传电价曲线，会清除旧项目级电价曲线；
- 02 页移除“任务边界”主界面提示，三条技术曲线摘要改为默认收起；
- “下网电价曲线”入口改为可选折叠区，说明放入上传控件帮助提示；
- 03 页电价状态文案改为“本次使用已上传的曲线”，不再使用“检测到/自动使用”这类容易误解为历史复用的表述。

验证：
- `python -m py_compile src/green_direct/ui/app.py` 通过；
- `python -m pytest tests/test_ui_import.py tests/test_price_curves.py tests/test_study_runner.py -q`：50 项通过；
- `python -m pytest -q`：169 项通过；
- 浏览器刷新 `http://localhost:8503` 后，02 页旧的 `price_curve_template_down_grid.csv` 状态、逐时电价曲线提示和“任务边界”主界面文案不再出现；03 页显示“当前未上传项目级下网电价曲线”，价格口径为“固定价/网页组价”。

### 2026-06-15 内部多人试用上线边界与缓存隔离

用户明确：“上线”指内部 10-20 人多人访问，不只是单机前台；同时希望把方案遍历和经济性测算性能优化提上日程，并开始设想后台账户管理。

本轮判断：
- 2026-06-10 引入的 `.runtime/latest_session_snapshot.pkl` 适合单机防重启丢结果，但不适合多人部署默认开启，否则新会话可能恢复上一位用户结果；
- PNG ZIP 后台任务表是进程级全局变量，必须按 Streamlit 会话隔离；只按方案 ID、时间范围和行数签名也不足以判断图表缓存是否仍对应当前数据；
- 内部试用可以先保留 Streamlit 前台，但必须把“运行态隔离、任务队列、ResultStore、账户/项目/角色”作为后续架构主线；
- 性能优化不应只做前端等待提示，核心方向是“汇总优先、明细按需、技术仿真并行、经济性批量化、后台任务化”。

本轮实现：
- `src/green_direct/ui/app.py` 新增 `GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT` 开关；默认直接 `streamlit run` 不保存、不恢复运行快照；
- 本地 Windows 启动器、portable 启动器和 PyInstaller 入口显式设置 `GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=1`，保留单机体验；
- 运行快照不再保存 PNG ZIP 二进制缓存；
- PNG ZIP 后台任务 key 增加会话 ID，避免不同会话复用同一全局任务；
- PNG ZIP 签名增加 `summary`、所选方案 `hourly_detail` 和对比方案表的数据指纹；
- 新技术仿真完成后清除旧 PNG 导出缓存；
- 新增 `docs/INTERNAL_PILOT_ARCHITECTURE_PLAN.md`，记录内部试用边界、账户后台模型、任务队列/ResultStore、性能优化路线和 Claude Code 两轮提示词；
- `notes/TODO.md`、`notes/HANDOFF_FOR_NEW_MACHINE.md` 同步更新多人上线和性能路线。

验证：
- `python -m pytest tests/test_ui_import.py::test_runtime_snapshot_round_trips_session_state tests/test_ui_import.py::test_runtime_snapshot_is_disabled_by_default tests/test_ui_import.py::test_chart_png_docx_signature_changes_when_export_data_changes tests/test_ui_import.py::test_chart_png_docx_background_job_stores_finished_result tests/test_ui_import.py::test_clear_chart_export_cache_removes_session_job -q`：5 项通过。

### 2026-06-15 大批量性能优化第一步：汇总优先接口

用户强调方案遍历和经济性测算在成千上万方案下会很慢，需要把性能优化提上工程日程。

本轮判断：
- 真正缩短总计算时间需要并行技术仿真和经济性批量化，但这两项会触及更大的任务调度和结果存储设计；
- 当前可以先做低风险接口准备：默认旧行为不变，大批量模式可选择只常驻 summary，减少逐小时明细和年度现金流表的内存、快照、下载缓存压力；
- 这一步不改变任何储能调度、政策筛选或经济性指标计算口径。

本轮实现：
- `run_batch()` 新增 `retain_hourly_details` 和 `hourly_detail_scenario_ids`；
- `TechnicalStudyInput` / `run_technical_study()` 接入上述参数，并把明细保留策略写入 `config_snapshot["detail_retention"]`；
- `evaluate_batch_economy()` 和 `evaluate_batch_single_entity_pre_tax_economy()` 新增 `retain_annual_cashflows` 和 `annual_cashflow_scenario_ids`；
- `run_economic_study()` 接入年度现金流保留策略；
- 默认参数保持旧行为：继续保存所有逐小时明细和年度现金流，现有 UI 不受影响。

验证：
- `python -m pytest tests/test_batch_runner.py tests/test_study_runner.py tests/test_economy_v1.py -q`：33 项通过。
