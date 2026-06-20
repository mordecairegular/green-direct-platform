# ECONOMY_EXTENSION_SPEC.md：未来经济性评价模块预留说明

## 1. 当前版本原则

V0.1 不实现经济性评价。

但 V0.1 的数据结构必须为经济性评价预留接口。

## 2. 技术测算结果向经济性模块提供的数据

每个方案至少提供：

```text
scenario_id
pv_capacity
wind_capacity
bess_power
bess_energy
total_load_energy
total_renewable_generation
self_use_energy
grid_import_energy
grid_export_energy
curtail_energy
bess_charge_energy
bess_discharge_energy
bess_loss_energy
annual_equivalent_cycles
replacement_year
max_grid_import_power
max_grid_export_power
hourly_grid_import
hourly_grid_export
hourly_bess_charge
hourly_bess_discharge
```

## 3. 未来经济性输入参数

未来 V1.0 可增加：

### 3.1 投资参数

```text
pv_capex_per_kw
wind_capex_per_kw
bess_power_capex_per_kw
bess_energy_capex_per_kwh
grid_connection_cost
land_cost
engineering_cost
```

### 3.2 运维参数

```text
pv_om_rate
wind_om_rate
bess_om_rate
fixed_om_cost
```

### 3.3 电价参数

```text
grid_purchase_price
export_price
time_of_use_price
transmission_distribution_price
government_fund
system_operation_fee
```

### 3.4 财务参数

```text
discount_rate
project_lifetime
loan_ratio
loan_interest_rate
tax_rate
depreciation_years
```

### 3.5 储能更换参数

```text
battery_replacement_cost
battery_replacement_year
battery_residual_value
```

## 4. 未来经济性输出

```text
total_capex
annual_om_cost
annual_grid_purchase_cost
annual_export_revenue
annual_energy_saving
annual_cashflow
npv
irr
payback_period
lcoe
```

## 5. 架构要求

当前代码应保留：

```text
src/green_direct/economy/
```

目录，并放置空接口文件：

```text
economic_inputs.py
economic_evaluator.py
```

但不要在 V0.1 中实现具体经济性计算。

## 6. 重要原则

经济性模块只能读取技术测算结果，不能反向修改逐时能量平衡结果。

正确依赖方向：

```text
技术测算模块 → 经济性评价模块
```

禁止：

```text
经济性模块 → 修改储能调度逻辑
```
