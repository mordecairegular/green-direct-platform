# OUTPUT_SCHEMA.md：输出结果格式

## 1. 输出文件类型

V0.1 输出：

1. Excel 汇总文件；
2. CSV 逐小时明细文件；
3. 可选 JSON 配置快照。

## 2. 方案汇总表

文件名建议：

```text
scenario_summary.xlsx
```

字段：

| 字段名 | 说明 |
|---|---|
| scenario_id | 方案编号 |
| pv_capacity | 光伏装机容量，万千瓦 |
| wind_capacity | 风电装机容量，万千瓦 |
| bess_power | 储能功率，万千瓦 |
| bess_energy | 储能容量，万千瓦时 |
| bess_duration | 储能时长，小时 |
| bess_c_rate | 储能 C 倍率 |
| total_load_energy | 用户总用电量，万千瓦时 |
| total_renewable_generation | 新能源总可用发电量，万千瓦时 |
| direct_self_use_energy | 新能源直接供负荷电量，万千瓦时 |
| bess_discharge_to_load | 储能放电供负荷电量，万千瓦时 |
| self_use_energy | 新能源自发自用电量，万千瓦时 |
| grid_import_energy | 电网购电量，万千瓦时 |
| grid_export_energy | 上网电量，万千瓦时 |
| curtail_energy | 弃电量，万千瓦时 |
| bess_charge_energy | 储能充电电量，万千瓦时 |
| bess_loss_energy | 储能损耗，万千瓦时 |
| self_use_rate | 自发自用率 |
| green_load_rate | 绿电占用电比例 |
| export_rate | 上网比例 |
| curtail_rate | 弃电率 |
| annual_equivalent_cycles | 年等效循环次数 |
| replacement_year | 预计更换年份 |
| max_grid_import_power | 最大购电功率 |
| max_grid_export_power | 最大上网功率 |
| final_soc | 年末 SOC |
| pass_policy | 是否达标 |
| fail_reasons | 不达标原因 |

## 3. 逐小时明细表

文件名建议：

```text
hourly_detail_{scenario_id}.csv
```

字段：

| 字段名 | 说明 |
|---|---|
| scenario_id | 方案编号 |
| timestamp | 时间 |
| hour_index | 小时序号 |
| load_power | 负荷功率 |
| pv_power | 光伏出力 |
| wind_power | 风电出力 |
| renewable_power | 新能源总出力 |
| direct_self_use_power | 新能源直接供负荷 |
| bess_charge_power | 储能充电功率 |
| bess_discharge_power | 储能放电功率 |
| grid_import_power | 购电功率 |
| grid_export_power | 上网功率 |
| curtail_power | 弃电功率 |
| soc_start | 小时初 SOC |
| soc_end | 小时末 SOC |
| bess_energy_start | 小时初储能电量 |
| bess_energy_end | 小时末储能电量 |
| hour_case | 小时场景 |

## 4. 小时场景枚举

```text
GEN_SHORT_GRID_IMPORT
GEN_SHORT_BESS_DISCHARGE
GEN_SHORT_BESS_DISCHARGE_AND_GRID_IMPORT
GEN_SURPLUS_DIRECT_EXPORT
GEN_SURPLUS_CHARGE_BESS
GEN_SURPLUS_CHARGE_EXPORT
GEN_SURPLUS_CHARGE_EXPORT_CURTAIL
GEN_SURPLUS_CURTAIL
GEN_BALANCED
NO_RENEWABLE_GRID_IMPORT
```

## 5. Excel 工作表建议

```text
Summary
Policy_Passed
Policy_Failed
Top_By_Green_Load_Rate
Top_By_Low_Curtail_Rate
Config
Warnings
```

## 6. 结果排序

V0.1 不做经济性排序，但可提供技术指标排序：

1. 是否达标；
2. 绿电占用电比例从高到低；
3. 自发自用率从高到低；
4. 上网比例从低到高；
5. 弃电率从低到高；
6. 储能容量从小到大。

注意：该排序不是最终推荐方案，只是技术筛选辅助。
