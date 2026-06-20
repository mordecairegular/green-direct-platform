# ALGORITHM_SPEC.md：逐时能量平衡与储能调度算法说明

## 1. 算法定位

本算法用于绿电直连项目风光储容量配置方案的逐时技术测算。

当前算法采用“贪心调度策略”：

- 新能源优先供负荷；
- 富余新能源优先充储能；
- 储能充满或受功率限制后，剩余电量按规则上网或弃电；
- 新能源不足时，储能优先放电供负荷；
- 储能不足后，剩余负荷由电网购电。

该策略不是经济性最优调度，但适合 V0.1 阶段进行容量配置可行性筛选。

## 2. 时间尺度

- 默认时间步长：dt = 1 小时；
- 支持 8760 小时普通年；
- 支持 8784 小时闰年；
- 所有功率单位为“万千瓦”；
- 所有电量单位为“万千瓦时”。

因为 dt = 1 小时，所以数值上：

```text
万千瓦 × 1小时 = 万千瓦时
```

但代码中必须保留 dt 参数，为未来支持 15 分钟或 10 分钟数据预留。

## 3. 输入曲线

### 3.1 负荷曲线

```text
P_load[t]
```

单位：万千瓦。

负荷曲线保留真实值，不做标幺化。

### 3.2 光伏曲线

```text
pv_pu[t]
```

单位：无量纲，标幺值。

### 3.3 风电曲线

```text
wind_pu[t]
```

单位：无量纲，标幺值。

## 4. 容量参数

```text
C_pv       光伏装机容量，万千瓦
C_wind     风电装机容量，万千瓦
P_bess     储能额定功率，万千瓦
E_bess     储能额定容量，万千瓦时
```

储能时长：

```text
duration = E_bess / P_bess
```

C 倍率：

```text
c_rate = P_bess / E_bess
```

常见关系：

```text
0.5C  = 2 小时储能
0.25C = 4 小时储能
```

## 5. 储能参数

```text
soc_initial      初始 SOC，默认 0.5
soc_min          最小 SOC，默认 0.1
soc_max          最大 SOC，默认 0.9
eta_charge       充电效率，默认 0.95
eta_discharge    放电效率，默认 0.95
cycle_life       循环寿命，默认 6000 次
```

储能电量状态：

```text
E_bat_start[t] = SOC_start[t] × E_bess
E_bat_end[t]   = SOC_end[t] × E_bess
```

## 6. 每小时新能源出力

```text
P_pv[t] = C_pv × pv_pu[t]
P_wind[t] = C_wind × wind_pu[t]
P_gen[t] = P_pv[t] + P_wind[t]
```

对应电量：

```text
E_gen[t] = P_gen[t] × dt
E_load[t] = P_load[t] × dt
```

## 7. 每小时调度逻辑

### 7.1 初始化

```text
soc = soc_initial
E_bat = soc_initial × E_bess
```

### 7.2 每小时开始

```text
SOC_start[t] = soc
E_bat_start[t] = E_bat
```

计算：

```text
E_gen = P_gen[t] × dt
E_load = P_load[t] × dt
```

### 7.3 情景 A：新能源出力大于等于负荷

条件：

```text
E_gen >= E_load
```

调度顺序：

1. 新能源直接供负荷：

```text
E_self_direct = E_load
```

2. 计算富余新能源：

```text
E_surplus = E_gen - E_load
```

3. 储能可充电量受三个约束：

```text
可用于充电的富余新能源 = E_surplus
储能功率上限 = P_bess × dt
储能剩余可充空间对应的交流侧输入 = (soc_max × E_bess - E_bat_start) / eta_charge
```

所以：

```text
E_charge_from_renewable = min(
    E_surplus,
    P_bess × dt,
    (soc_max × E_bess - E_bat_start) / eta_charge
)
```

4. 储能电量更新：

```text
E_bat_end = E_bat_start + E_charge_from_renewable × eta_charge
```

5. 剩余富余电量：

```text
E_surplus_after_charge = E_surplus - E_charge_from_renewable
```

6. 若允许上网：

年度上网比例约束是年度积分约束，不是每小时约束。V0.1 支持两种模式：

- `export_control_mode = post_check`：逐小时按功率上限上网，最后统一校核年度上网比例；
- `export_control_mode = annual_cap_runtime`：运行中累计年度上网额度，超过年度额度后转弃电。

默认建议使用 `post_check`，因为它更透明，更适合容量方案筛选。

上网电量：

```text
E_export = min(E_surplus_after_charge, P_export_max × dt)
```

若不允许上网：

```text
E_export = 0
```

7. 弃电：

```text
E_curtail = E_surplus_after_charge - E_export
```

8. 购电：

```text
E_grid_import = 0
```

### 7.4 情景 B：新能源出力小于负荷

条件：

```text
E_gen < E_load
```

调度顺序：

1. 新能源全部直接供负荷：

```text
E_self_direct = E_gen
```

2. 计算负荷缺口：

```text
E_deficit = E_load - E_gen
```

3. 储能可放电量受三个约束：

```text
负荷缺口 = E_deficit
储能功率上限 = P_bess × dt
储能可释放的交流侧电量 = (E_bat_start - soc_min × E_bess) × eta_discharge
```

所以：

```text
E_discharge_to_load = min(
    E_deficit,
    P_bess × dt,
    (E_bat_start - soc_min × E_bess) × eta_discharge
)
```

4. 储能电量更新：

```text
E_bat_end = E_bat_start - E_discharge_to_load / eta_discharge
```

5. 剩余负荷由电网购电：

```text
E_grid_import = E_deficit - E_discharge_to_load
```

6. 上网和弃电：

```text
E_export = 0
E_curtail = 0
E_charge_from_renewable = 0
```

## 8. SOC 滚动

每小时结束后：

```text
SOC_end[t] = E_bat_end / E_bess
SOC_start[t+1] = SOC_end[t]
```

如果 E_bess = 0，则储能所有相关变量均为 0。

## 9. 自发自用口径

### 9.1 负荷侧绿电自发自用电量

```text
E_self_use = E_self_direct + E_discharge_to_load
```

这里的储能放电量必须只来自此前富余新能源充电。

### 9.2 新能源发电量流向口径

由于储能存在效率损耗，不能简单把“储能放电供负荷”当作新能源发电量流向。

建议内部同时统计两个平衡口径：

#### 口径 A：新能源发电量流向平衡

```text
E_gen_total
= E_self_direct_total
+ E_charge_from_renewable_total
+ E_export_total
+ E_curtail_total
```

#### 口径 B：负荷供电平衡

```text
E_load_total
= E_self_direct_total
+ E_discharge_to_load_total
+ E_grid_import_total
```

#### 口径 C：储能损耗

```text
E_bess_loss
= E_charge_from_renewable_total
- E_discharge_to_load_total
- (E_bat_end_final - E_bat_initial)
```

如果不强制年末 SOC 回到初始 SOC，应单独显示 SOC 年末偏差。

## 10. 政策指标

```text
新能源总可用发电量 = E_gen_total
新能源自发自用电量 = E_self_direct_total + E_discharge_to_load_total
用户总用电量 = E_load_total
上网电量 = E_export_total
弃电量 = E_curtail_total
```

### 10.1 新能源自发自用率

```text
self_use_rate = 新能源自发自用电量 / 新能源总可用发电量
```

默认要求：

```text
self_use_rate >= 0.60
```

### 10.2 绿电占用电比例

```text
green_load_rate = 新能源自发自用电量 / 用户总用电量
```

默认要求：

```text
green_load_rate >= 0.30
```

2030 年前目标可设置为：

```text
green_load_rate >= 0.35
```

### 10.3 上网比例

```text
export_rate = 上网电量 / 新能源总可用发电量
```

默认要求：

```text
export_rate <= 0.20
```

### 10.4 弃电率

```text
curtail_rate = 弃电量 / 新能源总可用发电量
```

弃电率不是 V0.1 默认硬约束，但必须输出。

## 11. 储能寿命估算

年等效循环次数：

```text
annual_equivalent_cycles = E_discharge_to_load_total / E_bess
```

若 E_bess = 0，则循环次数为 0。

预计更换年份：

```text
replacement_year = cycle_life / annual_equivalent_cycles
```

若 annual_equivalent_cycles = 0，则 replacement_year = null 或 infinity。

## 12. 方案达标判断

一个方案达标需要同时满足：

```text
self_use_rate >= self_use_rate_min
green_load_rate >= green_load_rate_min
export_rate <= export_rate_max
```

如果不允许上网：

```text
E_export_total == 0
```

不达标原因应明确列出：

- 自发自用率不足；
- 绿电占用电比例不足；
- 上网比例超限；
- 不允许上网但出现上网；
- 最大上网功率超限；
- 数据异常。

## 13. 必须保留逐小时结果

每个方案必须能够输出逐小时明细，用于人工复核：

- 时间；
- 负荷；
- 光伏出力；
- 风电出力；
- 新能源总出力；
- 直接供负荷；
- 储能充电；
- 储能放电；
- SOC_start；
- SOC_end；
- 上网；
- 弃电；
- 购电；
- 小时场景。

## 14. 重要禁止事项

1. 禁止储能从电网充电；
2. 禁止储能同时充电和放电；
3. 禁止 SOC 超过上限或低于下限；
4. 禁止忽略储能功率约束；
5. 禁止忽略储能容量约束；
6. 禁止把储能损耗错误计入弃电；
7. 禁止只输出汇总结果而不保留逐小时过程；
8. 禁止把经济性评价混入 V0.1 核心算法。
