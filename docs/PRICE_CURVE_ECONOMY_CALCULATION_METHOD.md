# 电价曲线经济性与推荐计算方法（审阅版）

状态：2026-06-04
对应模板：`samples/price_curve_template_down_grid.csv`
实现入口：`src/green_direct/economy/price_curves.py`、`src/green_direct/services/study_runner.py`

当前样例模板采用 2020 闰年时间戳，共 8784 行，`hour_index` 已填满 0...8783；普通年价格曲线使用 8760 行。

## 1. 总体边界

价格曲线 V1 只接入经济性测算和推荐排序，不改变现有风光储逐小时技术调度。

当前模板只表达“下网购电账单组分随小时变化”。绿电结算价、上网电价、度电环境价值、电网购电增值税率仍来自网页端全年固定参数，不从电价曲线文件读取。

UI 工作流中，电价曲线作为项目级输入在“方案仿真”页上传；进入“经济性测算”页后自动使用，不需要也不允许再次选择同一曲线。若已上传项目级曲线，经济性页会禁用固定外部购电净成本、电费清单组价开关和负荷侧单独覆盖等会与曲线口径冲突的控件，并显示当前使用的曲线状态。

当前实现使用电价曲线拉开差异的主要视角是：

- 同一主体 FIRR / 回收期：按自发自用发生小时计算少买外部电网电形成的税前净节费；
- 负荷侧可成交收益：按自发自用发生小时计算负荷侧可减少购网费用，再扣减绿电结算成本；
- 推荐排序：同一主体席位和负荷侧席位会随下网电价曲线变化；电源侧席位目前仍主要由固定绿电结算价、固定上网电价和投资成本决定。

## 2. 模板字段如何使用

`samples/price_curve_template_down_grid.csv` 当前包含：

| 字段 | 是否参与计算 | 用法 |
|---|---|---|
| `timestamp` | 是 | 优先用于与技术仿真的逐小时明细对齐 |
| `hour_index` | 是 | 当完整填写 0...8759 或 0...8783 时，可作为回退对齐键 |
| `energy_market_price_with_vat` | 是 | 电度电价 / 电能量或市场购电价格，含税 |
| `line_loss_price_with_vat` | 是 | 线损费，含税 |
| `system_operation_fee_with_vat` | 是 | 系统运行费，含税 |
| `transmission_distribution_tariff_with_vat` | 是 | 输配电价，含税；当前默认自发自用绿电仍需缴纳，因此不计入可避免节费 |
| `gov_fund_surcharge` | 是 | 政府性基金及附加，不含增值税；当前默认自发自用绿电仍需缴纳，因此不计入可避免节费 |
| `month` | 否 | 用户复核/筛选辅助列，程序忽略 |
| `peak_valley` | 否 | 尖峰平谷标签，用户复核/展示辅助列，程序忽略 |

程序只把可识别字段标准化到内部价格表，未识别的辅助列不会进入计算。

## 3. 读取、校验和对齐

读取支持 CSV 和 Excel。CSV 当前支持 UTF-8、UTF-8-SIG、GBK、GB18030；用户模板含中文分时标签时，GBK 文件可正常读取。

导入校验：

- 行数必须为 8760 或 8784；
- 至少有 `timestamp` 或 `hour_index` 中的一个；
- 至少识别到一个下网账单价格字段；
- 参与计算的价格字段不得为负；
- 价格曲线行数必须与每个方案的逐小时技术明细行数一致。

对齐顺序：

1. 若价格曲线和技术逐时明细的 `timestamp` 集合完全一致，按 `timestamp` 重排对齐；
2. 若时间戳不一致，但 `hour_index` 完整、唯一且覆盖全部小时，按 `hour_index` 对齐；
3. 若 `hour_index` 不完整或不可用，按文件行序对齐，并给出 warning。

因此，当前样例即使技术曲线年份与模板年份不同，也可以通过完整 `hour_index` 对齐。若后续用户文件的 `hour_index` 不完整，程序会 warning 后按行序对齐；为减少歧义，正式项目数据建议始终把 `hour_index` 填满。

## 4. 每小时有效价格推导

对任一小时 `t`，从模板读取：

```text
E_t = energy_market_price_with_vat
L_t = line_loss_price_with_vat
S_t = system_operation_fee_with_vat
T_t = transmission_distribution_tariff_with_vat
G_t = gov_fund_surcharge
```

网页端读取：

```text
r_vat = 电网购电增值税率，默认 13%
P_green = 绿电结算价，含税，全年固定值
P_export = 上网电价，含税，全年固定值
P_env = 度电环境价值，全年固定值，默认 0
```

当前 V1 假设：

```text
自发自用绿电仍需缴纳输配电价 T_t
自发自用绿电仍需缴纳政府性基金及附加 G_t
系统运行费 S_t 按下网电量缴纳，自发自用绿电不再另缴
```

因此每小时负荷侧可减少购网费用现金单价为：

```text
P_load_avoid_t =
  E_t + L_t + S_t + T_t + G_t
  - T_t - G_t
= E_t + L_t + S_t
```

每小时同一主体外部购电税前净节费单价为：

```text
P_net_avoid_t =
  (E_t + L_t + S_t + T_t - T_t) / (1 + r_vat)
  + G_t - G_t
= (E_t + L_t + S_t) / (1 + r_vat)
```

政府性基金及附加 `G_t` 是不含税项目，不参与价税分离。由于当前默认仍需缴纳，它在上述两个节费口径中被扣回。

以模板首小时为例：

```text
E_t = 0.30872
L_t = 0.027
S_t = 0.05
T_t = 0.1104
G_t = 0.04625

P_load_avoid_t = 0.30872 + 0.027 + 0.05 = 0.38572 元/kWh
P_net_avoid_t = 0.38572 / 1.13 = 0.34135 元/kWh
```

## 5. 逐方案年度金额聚合

技术仿真输出的逐小时明细仍是唯一的能量来源。价格曲线不重新调度储能，也不改变 SOC、上网、弃电或政策指标。

对任一方案 `scenario_id` 和小时 `t`：

```text
self_use_energy_t =
  (direct_self_use_power_t + bess_discharge_power_t) * dt_hours

export_energy_t =
  grid_export_power_t * dt_hours
```

当前储能基线策略只允许可再生富余电量充电，储能放电不送网，因此 `bess_discharge_power_t` 计入自发自用绿电。

年度聚合：

```text
annual_self_use_saving =
  sum(self_use_energy_t * P_net_avoid_t)

annual_avoided_grid_purchase_cash_saving =
  sum(self_use_energy_t * P_load_avoid_t)

annual_green_power_cost_or_revenue =
  sum(self_use_energy_t * P_green)

annual_export_revenue_with_vat =
  sum(export_energy_t * P_export)

annual_environmental_value =
  sum(self_use_energy_t * P_env)
```

虽然 `annual_green_power_cost_or_revenue` 和 `annual_export_revenue_with_vat` 在曲线模式下也会进入聚合表，但目前使用的是网页端固定价格，不由下网电价曲线决定。

## 6. 各视角如何使用这些金额

### 6.1 电源侧视角

电源侧收入仍为：

```text
绿电收入 = self_use_energy * P_green
上网收入 = export_energy * P_export
```

其中 `P_green` 和 `P_export` 都是网页端全年固定值。所以下网电价曲线本身不改变电源侧收入曲线，只会在结果表里标记 `price_mode = hourly_curve` 并携带有效价格摘要。

电源侧 FIRR 最佳席位目前仍主要由投资、运维、储能更换、固定绿电结算价、固定上网电价和税费参数决定。

### 6.2 同一主体视角

同一主体把项目看成一个整体，不把内部绿电结算价当作新增收益。它使用自发自用绿电替代外部购电形成的税前净节费：

```text
同一主体自发自用节费 =
  annual_self_use_saving
= sum(self_use_energy_t * P_net_avoid_t)
```

该金额覆盖固定价模式下的：

```text
self_use_energy * 固定外部购电净成本单价
```

因此两个方案即使全年自发自用电量相同，只要自发自用发生在不同下网电价小时，同一主体 FIRR、FNPV、静态/动态回收期都可能不同。

同一主体还会使用固定上网电价计算上网收入的不含税金额；当前上网电价不是曲线输入。

### 6.3 负荷侧可成交收益视角

负荷侧先计算少买电网电减少的现金费用：

```text
负荷侧减少购网费用 =
  annual_avoided_grid_purchase_cash_saving
= sum(self_use_energy_t * P_load_avoid_t)
```

再扣除购买绿电的成本，并加上环境价值：

```text
负荷侧现金收益（不含环境价值） =
  annual_avoided_grid_purchase_cash_saving
  - sum(self_use_energy_t * P_green)

负荷侧年度收益 =
  负荷侧现金收益（不含环境价值）
  + sum(self_use_energy_t * P_env)
```

`P_green` 和 `P_env` 仍来自网页端固定输入。

该视角排序前还会检查电源侧最低可接受 FIRR。若用户没有提供最低可接受电源侧 FIRR，负荷侧席位会显示为 pending / 不可排序，而不是直接推荐一个不可交易方案。

### 6.4 工程代表视角

工程代表视角仍以技术指标和工程约束为主，例如容量、投资规模、绿电占比、自发自用率、弃电率等。价格曲线不改变技术调度，因此不改变这些技术指标。

当价格曲线模式已运行时，工程代表方案可以展示同一套经济摘要，但它的工程筛选逻辑不以电价曲线重新优化。

## 7. 推荐排序中的数据流

整体链路：

```text
上传下网电价曲线
-> read_price_curve()
-> align_price_curve_to_hourly()
-> build_effective_hourly_prices()
-> apply_price_curve_to_summary()
-> evaluate_batch_economy()
-> evaluate_batch_single_entity_pre_tax_economy()
-> build_recommendation_study()
```

曲线模式会向年度 `summary` 追加这些覆盖字段：

| 字段 | 用途 |
|---|---|
| `price_mode` | 标记 `hourly_curve` |
| `price_curve_alignment` | 记录 `timestamp` / `hour_index` / `row_order` |
| `self_use_saving_override` | 同一主体税前自发自用节费 |
| `avoided_grid_purchase_cash_saving_override` | 负荷侧减少购网费用现金额 |
| `load_side_cash_saving_without_environment_override` | 负荷侧扣除绿电结算成本后的现金收益 |
| `load_side_annual_benefit_override` | 负荷侧年度收益，用于负荷侧席位排序 |
| `net_avoided_grid_cost_price_effective` | 按自发自用小时加权后的同一主体净节费单价 |
| `load_side_avoided_charge_price_effective` | 按自发自用小时加权后的负荷侧减少购网费用单价 |

推荐引擎优先使用这些 override 字段。没有价格曲线时，继续使用固定价模式。

## 8. 当前需审阅确认的口径

1. 是否确认 V1 默认“自发自用绿电仍缴输配电价和政府性基金及附加”，因此这两项不计入可避免节费。
2. 是否确认系统运行费按下网电量缴纳，自发自用绿电默认不再另缴。
3. `month` 和 `peak_valley` 当前只作为用户复核标签，不参与计算；后续是否需要在 UI 或报告里展示。
4. 是否要求正式模板的 `hour_index` 必须填满。当前程序允许不完整时按行序回退，但填满更利于审计。
5. 是否需要在后续版本支持特殊政策下“绿电不再缴纳输配电价/政府基金”的高级参数。若需要，建议放在网页端或单独高级表，不放入当前下网电价曲线模板。
