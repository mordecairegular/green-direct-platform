# 独立方案遍历试用程序调度与计算说明

状态：试用入口计算口径说明
最近更新：2026-05-27

## 1. 计算来源

独立方案遍历试用程序不另写一套算法。它调用当前仓库中的 V0.1 风光储技术仿真：

- `src/green_direct/io/read_curves.py`
- `src/green_direct/batch/scenario_generator.py`
- `src/green_direct/batch/batch_runner.py`
- `src/green_direct/core/single_scenario_simulator.py`
- `src/green_direct/core/bess_dispatch.py`
- `src/green_direct/core/metrics.py`

因此它与 Streamlit 主程序的技术调度口径保持一致。

## 2. 风光出力和站用电

每小时先计算光伏和风电原始出力：

```text
pv_power = pv_pu * pv_capacity
wind_power = wind_pu * wind_capacity
```

如果光伏或风电标幺值为负，不自动截断，而是作为站用电处理：

```text
pv_generation_power = max(pv_power, 0)
wind_generation_power = max(wind_power, 0)
pv_station_use_power = max(-pv_power, 0)
wind_station_use_power = max(-wind_power, 0)
```

风光正发电先抵扣站用电，抵扣后的净新能源再进入负荷、储能、上网和弃电分配。

## 3. 储能调度基线

当前策略是并网风光储贪心调度：

```text
新能源先供负荷
-> 富余新能源给储能充电
-> 储能充不下的富余电量上网或弃电
-> 新能源不足时储能放电供负荷
-> 储能不足后由电网下网
```

硬约束：

- 储能只能从富余新能源充电；
- 储能不能从电网充电；
- 储能不能同小时充电和放电；
- 储能不能放电上网；
- 储能放电只用于补足负荷或站用电缺口；
- SOC 逐小时滚动；
- SOC 受 `soc_min` 和 `soc_max` 限制；
- 充放电受储能功率、容量和效率限制。

## 4. 上网和下网约束

如果允许上网，程序按上网比例控制模式处理年度上网额度。默认模式为：

```text
annual_cap_runtime
```

即运行过程中累计上网电量，额度用完后后续富余新能源转为弃电。

`grid_exchange_power_limit` 同时约束上网和下网功率：

- 上网超过限制的部分计入因交换功率限制导致的弃电；
- 下网超过限制的部分计入下网功率限制导致的缺口；
- 只要存在下网缺口，方案会被判为不达标。

## 5. 政策指标

主要指标包括：

```text
self_use_rate = self_use_energy / total_renewable_generation
green_load_rate = self_use_energy / total_load_energy
export_rate = grid_export_energy / total_renewable_generation
curtail_rate = curtail_energy / total_renewable_generation
```

其中：

```text
self_use_energy = direct_self_use_energy + bess_discharge_to_load
```

在当前基线中，储能只能由新能源充电，所以储能放电供负荷计入新能源自发自用。

## 6. 不包含的能力

该试用程序暂不包含：

- 经济性评价；
- 推荐方案排序；
- 图表分析；
- 柴油发电机；
- 离网可靠性；
- 电价时段优化；
- 储能套利；
- 数学规划优化。

这些能力应在主程序和后续架构模块中继续演进，不应塞进该窄边界试用入口。
