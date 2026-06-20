# 同一主体购电节费与税前 FIRR 口径

> 状态：V1 设计口径已落第一版代码，2026-05-25。本文沉淀“同一主体 FIRR 最优”推荐席位的可实现算法。它是规划测算口径，不替代项目税务专项意见。

## 1. 结论

同一主体推荐席位可以实现，但不能复用当前电源侧经济性 V1 的“自发自用电费收入”模型。

V1 应新增一个独立的“同一主体税前增量现金流模型”：

```text
同一主体税前现金流 =
  自发自用购电节费
  + 上网不含税收入
  + 其他外部收益
  - 新增运维成本
  - 储能更换等资本性支出
  - 其他项目现金成本
```

这里的“自发自用购电节费”来自少向外部电网购电，不来自内部绿电结算。因此同一主体 FIRR 不使用 `green_power_settlement_price_with_vat`。

## 2. 与现有项目基础的关系

不冲突的部分：

- 技术仿真的 `self_use_energy`、`grid_export_energy`、`hourly_detail` 可以直接作为计算基础；
- 当前风、光、储、送出线路、其他固定资产投资字段可以复用；
- 当前储能更换触发逻辑和更换年份可以复用；
- 当前 `dt_hours` 保留参数，有利于后续 15min 扩展；
- 推荐层仍然只读取技术结果，不改变调度。

需要分开的部分：

- 当前 `evaluate_scenario_economy()` 更接近电源侧投资收益模型，它把 `self_use_energy` 乘以结算电价作为售电收入，并计算销项税、进项税留抵、所得税和税后净现金流；
- 同一主体模型中，自发自用不应被当作内部售电收入，也不应默认产生对应销项税；
- 同一主体 V1 主排序采用税前 FIRR，不默认计算所得税；
- 绿电结算价只用于电源侧、负荷侧或不同法人/不同主体结算视角，不用于同一主体合并口径的整体收益。

因此实现时建议新增独立模块，例如：

```text
src/green_direct/economy/electricity_saving.py
src/green_direct/economy/single_entity_evaluator.py
```

## 3. 固定价输入参数

同一主体 V1 固定价模式默认使用一个简化输入：

| 字段 | 中文名 | 单位 | 默认值 | 说明 |
|---|---|---:|---:|---|
| `net_avoided_grid_cost_price` | 外部购电净成本单价 | 元/kWh | 用户输入 | 同一主体口径下每 1 kWh 自发自用绿电替代外部购电带来的税前净节费；已剔除本阶段不考虑的容需量电费、力调电费等非电量费用，并已按净成本口径处理 |
| `grid_export_price_with_vat` | 上网含税电价 | 元/kWh | 用户输入 | 上网收入价税分离后进入税前现金流 |
| `output_vat_rate` | 上网电力销售增值税率 | decimal | 0.13 | 用于上网收入价税分离 |
| `environmental_value_per_kwh` | 环境价值单价 | 元/kWh | 0 | 高级选项，默认不计 |

如用户需要从电费清单复核，则启用“按电费清单组价”模式。组价字段应尽量对应电费清单：

| 字段 | 中文名 | 单位 | 默认值 | 说明 |
|---|---|---:|---:|---|
| `energy_market_price_with_vat` | 电能量/市场购电价格 | 元/kWh，含税 | 用户输入 | 作为电量电费的主体项目 |
| `line_loss_price_with_vat` | 上网环节线损费用 | 元/kWh，含税 | 0 | 如清单列项则填写 |
| `system_operation_fee_with_vat` | 系统运行费用 | 元/kWh，含税 | 0 | 如清单列项则填写 |
| `transmission_distribution_tariff_with_vat` | 输配电价 | 元/kWh，含税 | 用户输入 | 如清单列项则填写 |
| `gov_fund_surcharge` | 政府性基金及附加 | 元/kWh | 用户输入 | 按无增值税电量附加处理 |
| `green_direct_retained_transmission_distribution_tariff_with_vat` | 绿电仍缴输配电价 | 元/kWh，含税 | 默认等于输配电价 | 自发自用绿电仍需缴纳的输配电价 |
| `green_direct_retained_gov_fund_surcharge` | 绿电仍缴政府性基金及附加 | 元/kWh | 默认等于政府性基金及附加 | 自发自用绿电仍需缴纳的政府性基金及附加 |
| `grid_purchase_vat_rate` | 外部购电增值税率 | decimal | 0.13 | 用于价税分离 |

输入提示必须强调：

```text
容需量电费、力调电费等默认不随自发自用电量按 kWh 线性变化，
V1 不计入节费测算，也不计入增加成本测算。后续如要考虑，应作为独立高级模型。
```

注意：`net_avoided_grid_cost_price` 不等同于负荷侧比较绿电结算价时使用的到户电量电费或电能量全电价。前者是同一主体增量投资收益评价中的税前净节费单价；后者用于负荷侧判断绿电结算后实际少付了多少电费。

面向用户的中文公式可写为：

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

其中政府性基金及附加按无增值税电量附加处理，不参与价税分离。1192 号文系统运行费暂按下网电量缴纳，自发自用绿电不作为“绿电仍缴系统运行费用”扣减；若当前项目口径认为自发自用绿电仍缴输配电价和政府性基金及附加，则这两项不能算作节省。

## 4. 固定价计算公式

默认简化模式：

```text
net_avoided_grid_cost_price =
  用户直接输入的外部购电净成本单价
```

按电费清单组价模式：

```text
grid_purchase_taxable_price_with_vat =
  energy_market_price_with_vat
  + line_loss_price_with_vat
  + system_operation_fee_with_vat
  + transmission_distribution_tariff_with_vat
```

```text
green_direct_retained_taxable_fee_with_vat =
  green_direct_retained_transmission_distribution_tariff_with_vat
```

```text
net_avoided_grid_cost_price =
  (grid_purchase_taxable_price_with_vat - green_direct_retained_taxable_fee_with_vat)
  / (1 + grid_purchase_vat_rate)
  + gov_fund_surcharge
  - green_direct_retained_gov_fund_surcharge
```

自发自用购电节费：

```text
self_use_saving =
  self_use_energy * net_avoided_grid_cost_price
```

中文公式：

```text
自发自用购电节费 =
  自发自用电量 * 被替代外部购电净成本单价
```

辅助展示指标：

```text
avoided_grid_purchase_cash_saving =
  self_use_energy * avoided_grid_purchase_cash_price
```

“少付电网电量电费现金额”只用于展示，不作为 V1 税前 FIRR 排序收益。

上网不含税收入：

```text
grid_export_revenue_without_vat =
  grid_export_energy * grid_export_price_with_vat / (1 + output_vat_rate)
```

## 5. 逐时价格曲线

同一主体逐时价格曲线采用 CSV/Excel 上传，不做网页逐项录入。

项目内实现时，价格曲线模板不需要 `load_kwh`，因为自发自用电量来自技术仿真的 `hourly_detail`。

建议模板字段：

| 字段 | 单位 | 是否必需 | 说明 |
|---|---|---|---|
| `timestamp` | 时间 | 必需 | 与 `hourly_detail.timestamp` 对齐 |
| `hour_index` | 整数 | 推荐 | 时间戳不完全匹配时用于回退对齐 |
| `energy_market_price_with_vat` | 元/kWh，含税 | 可选 | 电能量/市场购电价格 |
| `line_loss_price_with_vat` | 元/kWh，含税 | 可选 | 上网环节线损费用 |
| `system_operation_fee_with_vat` | 元/kWh，含税 | 可选 | 系统运行费用 |
| `transmission_distribution_tariff_with_vat` | 元/kWh，含税 | 可选 | 输配电价 |
| `gov_fund_surcharge` | 元/kWh，无增值税 | 可选 | 政府性基金及附加 |

`net_avoided_grid_cost_price` 是程序根据上述下网账单组分、增值税率和仍缴费用口径推导的结果，不作为 V1 价格曲线模板输入。上网电价当前继续使用网页端固定参数。

每个时段：

```text
self_use_energy_t =
  (direct_self_use_power_t + bess_discharge_power_t) * dt_hours
```

```text
period_self_use_saving =
  self_use_energy_t * net_avoided_grid_cost_price_t
```

全年：

```text
annual_self_use_saving =
  sum(period_self_use_saving)
```

V1 支持 8760 / 8784 小时曲线。15min 后续支持；届时需要同步扩展输入校验、UI 文案、导出和图表对时间步长的假设。

## 6. 税前 FIRR 现金流

同一主体 V1 主排序使用税前 FIRR。建议现金流字段命名上明确 `pre_tax`，避免与现有电源侧税后/含税现金流混淆。

```text
pre_tax_cash_flow_0 =
  - initial_investment_basis
```

```text
pre_tax_cash_flow_year =
  self_use_saving
  + grid_export_revenue_without_vat
  + other_external_revenue
  - operating_cost_basis
  - bess_replacement_basis
  - other_project_cash_cost
```

`initial_investment_basis` 和 `bess_replacement_basis` 推荐按可抵扣增值税后的不含税投资额进入税前 FIRR；同时保留含税现金支出作为辅助展示。若未来需要模拟真实含税现金流和增值税留抵，应作为高级税务现金流模型，不混入 V1 主排序。

## 7. 校验规则

基础校验：

- `net_avoided_grid_cost_price >= 0`
- `energy_market_price_with_vat >= 0`
- `line_loss_price_with_vat >= 0`
- `system_operation_fee_with_vat >= 0`
- `transmission_distribution_tariff_with_vat >= 0`
- `gov_fund_surcharge >= 0`
- `0 <= grid_purchase_vat_rate <= 0.20`
- `0 <= output_vat_rate <= 0.20`

诊断提示：

- 如果用户把容需量、力调等非电量费用摊入 `net_avoided_grid_cost_price` 或组价字段，报告中会高估节费，应在 UI 中明确提示；
- 如果项目所在地已明确电费清单口径，应优先使用“按电费清单组价”模式，让输入项与清单科目对应。

## 8. 报告说明模板

```text
本测算采用同一经济主体税前合并口径。内部绿电结算价不作为项目整体收益来源，自发自用收益按“被替代外部购电净成本”计算。简化模式下，用户直接输入外部购电净成本单价；组价模式下，按电能量/市场购电价格、上网环节线损费用、系统运行费用、输配电价、政府性基金及附加等电费清单项目组价，并对含税项目进行价税分离。容需量电费、力调电费默认不随自发自用电量按 kWh 线性变化，不参与本阶段节费测算。税前 FIRR 作为 V1 方案排序主指标；税后测算涉及项目主体、内部结算、所得税优惠、折旧政策和亏损弥补等复杂事项，应由项目税务顾问复核。
```

## 9. 后续扩展

- 简化税后 FIRR；
- 不同法人主体下的内部绿电结算、发票和所得税分摊；
- 输配电费机制单独建模；
- 系统运行费从按电量向按容量或占用容量过渡后的适配；
- 容需量电费优化；
- 力调电费和无功补偿模块；
- 绿证、CCER、碳配额或其他环境价值模块；
- 15min 曲线统一导入格式。

## 10. 第一版实现位置

当前已实现固定价版本：

- `src/green_direct/economy/economic_inputs.py`：新增 `AvoidedGridPurchaseParams`；
- `src/green_direct/economy/electricity_saving.py`：计算被替代外部购电净成本单价、自发自用节费、环境价值和上网不含税收入；
- `src/green_direct/economy/single_entity_evaluator.py`：输出同一主体税前年度现金流、`single_entity_firr_pre_tax`、`single_entity_fnpv_pre_tax`、静态/动态回收期；
- `src/green_direct/ui/app.py`：在经济性评价区默认提供同一主体税前经济性所需固定价参数，经济性测算一次计算当前已实现的电源侧和同一主体视角。所选方案年度现金流工作簿包含 `方案说明`、`年度现金流`、`字段说明` 三张表；
- `tests/test_single_entity_economy.py`：锁定固定价节费、绿电结算价不参与同一主体收益、投资基础价税分离和环境价值高级项。

特别注意：现有 `evaluate_scenario_economy()` 未改，仍作为电源侧投资收益近似模型。同一主体 evaluator 只复用投资、运维、储能更换年限、折现率和 IRR 工具等中性能力，不复用电源侧的自发自用售电收入现金流。

技术方案汇总表和经济性视角输出分离：方案汇总表保持纯技术指标；电源侧经济性和同一主体税前经济性分别在经济性区域下载汇总表与年度现金流明细。年度现金流明细是正式软件的可审计输出，不是一次性复核材料。
