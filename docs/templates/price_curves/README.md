# 价格曲线输入模板草案

状态：2026-05-28 草案，待试用确认。  
模板文件：`price_curve_template.csv`

## 1. 用途

价格曲线只影响经济性评价和推荐排序，不反向改变当前风光储逐小时调度。

第一版建议支持 8760 / 8784 小时。15 分钟曲线后续再扩展，需要同步确认技术仿真输入、`dt_hours`、逐时明细和图表展示。

## 2. 对齐规则

优先使用 `timestamp` 与逐时明细对齐；如果没有时间戳，则使用 `hour_index`。

```text
timestamp: 建议格式 yyyy-mm-dd HH:MM
hour_index: 从 0 开始，8760 小时为 0...8759，8784 小时为 0...8783
```

导入时应校验：

- 行数必须与技术逐时明细一致；
- `timestamp` 或 `hour_index` 至少有一个可用；
- 价格列允许留空，留空时使用页面固定价；
- 价格不得为负；
- 税率类字段应在 0 到 1 之间。

## 3. 最小可用列

| 字段 | 单位 | 含义 | 用途 |
|---|---:|---|---|
| `timestamp` | 时间 | 与逐时明细对齐 | 必填其一 |
| `hour_index` | 整数 | 与逐时明细对齐 | 必填其一 |
| `green_power_settlement_price_with_vat` | 元/kWh，含税 | 绿电结算价 | 电源侧收入、负荷侧购电成本 |
| `grid_export_price_with_vat` | 元/kWh，含税 | 上网电价 | 电源侧和同一主体上网收入 |
| `load_side_avoided_charge_price` | 元/kWh | 负荷侧可减少购网费用现金单价 | 负荷侧可成交收益 |
| `net_avoided_grid_cost_price` | 元/kWh | 同一主体外部购电税前净节费单价 | 同一主体税前 FIRR |
| `environmental_value_per_kwh` | 元/kWh | 环境价值，高级项 | 同一主体、负荷侧 |

## 4. 账单组价列

如果用户不想分别填写 `load_side_avoided_charge_price` 和 `net_avoided_grid_cost_price`，可以只填写同一组电费清单列，由程序内部推导两个口径：

| 字段 | 单位 | 含义 |
|---|---:|---|
| `energy_market_price_with_vat` | 元/kWh，含税 | 电能量 / 市场购电价格 |
| `line_loss_price_with_vat` | 元/kWh，含税 | 上网环节线损费用 |
| `system_operation_fee_with_vat` | 元/kWh，含税 | 系统运行费用 |
| `transmission_distribution_tariff_with_vat` | 元/kWh，含税 | 输配电价 |
| `gov_fund_surcharge` | 元/kWh | 政府性基金及附加，不参与增值税价税分离 |
| `green_direct_retained_transmission_distribution_tariff_with_vat` | 元/kWh，含税 | 自发自用绿电仍需缴纳的输配电价 |
| `green_direct_retained_gov_fund_surcharge` | 元/kWh | 自发自用绿电仍需缴纳的政府性基金及附加 |
| `grid_purchase_vat_rate` | decimal | 电网购电增值税率 |

内部推导：

```text
负荷侧可减少购网费用单价 =
  电能量/市场购电价格
  + 线损费用
  + 系统运行费用
  + 输配电价
  + 政府性基金及附加
  - 绿电仍缴输配电价
  - 绿电仍缴政府性基金及附加
```

```text
同一主体外部购电净成本单价 =
  (电能量/市场购电价格 + 线损费用 + 系统运行费用 + 输配电价 - 绿电仍缴输配电价)
  / (1 + 电网购电增值税率)
  + 政府性基金及附加
  - 绿电仍缴政府性基金及附加
```

## 5. 两个容易混淆的字段

`load_side_avoided_charge_price` 是负荷侧在支付绿电结算价之前，因少买电网电而减少的费用单价。

`load_side_saving_price` 不建议作为输入字段，它是计算结果：

```text
load_side_saving_price =
  load_side_avoided_charge_price
  - green_power_settlement_price_with_vat
```

同一主体视角中，`green_power_settlement_price_with_vat` 是内部转移价格，不作为项目整体收益。

## 6. 当前不纳入的内容

- 容需量电费；
- 力调电费；
- 融资、贷款和资本金 IRR；
- 税收优惠自动判断；
- 电价驱动的储能优化调度。

这些内容后续可以作为高级模型单独加入，不应混入价格曲线 V1 模板。
