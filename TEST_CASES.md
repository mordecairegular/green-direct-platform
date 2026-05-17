# TEST_CASES.md：测试用例规范

## 1. 测试原则

所有核心算法必须可测试。

V0.1 必须至少包含：

- 数据读取测试；
- 数据校验测试；
- 单方案逐时平衡测试；
- 储能 SOC 测试；
- 批量方案生成测试；
- 指标计算测试；
- 输出文件测试；
- Streamlit 入口基本可导入测试。

## 2. Case 1：无新能源、无储能

输入：

```text
load = [10, 20, 30]
pv = [0, 0, 0]
wind = [0, 0, 0]
C_pv = 0
C_wind = 0
P_bess = 0
E_bess = 0
```

预期：

```text
grid_import = [10, 20, 30]
self_use = [0, 0, 0]
export = [0, 0, 0]
curtail = [0, 0, 0]
total_load = 60
grid_import_total = 60
```

## 3. Case 2：无储能，新能源小于负荷

输入：

```text
load = [10, 10, 10]
renewable = [5, 6, 7]
```

预期：

```text
direct_self_use = [5, 6, 7]
grid_import = [5, 4, 3]
export = [0, 0, 0]
curtail = [0, 0, 0]
```

## 4. Case 3：无储能，新能源大于负荷，不允许上网

输入：

```text
load = [10, 10, 10]
renewable = [12, 15, 8]
allow_export = false
```

预期：

```text
direct_self_use = [10, 10, 8]
curtail = [2, 5, 0]
grid_import = [0, 0, 2]
export = [0, 0, 0]
```

## 5. Case 4：无储能，新能源大于负荷，允许上网

输入：

```text
load = [10, 10, 10]
renewable = [12, 15, 8]
allow_export = true
export_power_max = very large
```

预期：

```text
direct_self_use = [10, 10, 8]
export = [2, 5, 0]
curtail = [0, 0, 0]
grid_import = [0, 0, 2]
```

## 6. Case 5：储能充电受功率限制

输入：

```text
load = [10]
renewable = [20]
P_bess = 3
E_bess = 10
soc_initial = 0.5
soc_max = 0.9
eta_charge = 1.0
allow_export = false
```

预期：

```text
surplus = 10
bess_charge = 3
curtail = 7
soc_end = 0.8
```

## 7. Case 6：储能充电受容量限制

输入：

```text
load = [10]
renewable = [20]
P_bess = 10
E_bess = 10
soc_initial = 0.85
soc_max = 0.9
eta_charge = 1.0
allow_export = false
```

预期：

```text
surplus = 10
bess_charge = 0.5
curtail = 9.5
soc_end = 0.9
```

## 8. Case 7：储能放电受功率限制

输入：

```text
load = [20]
renewable = [10]
P_bess = 3
E_bess = 10
soc_initial = 0.9
soc_min = 0.1
eta_discharge = 1.0
```

预期：

```text
deficit = 10
bess_discharge = 3
grid_import = 7
soc_end = 0.6
```

## 9. Case 8：储能放电受容量限制

输入：

```text
load = [20]
renewable = [10]
P_bess = 10
E_bess = 10
soc_initial = 0.15
soc_min = 0.1
eta_discharge = 1.0
```

预期：

```text
deficit = 10
bess_discharge = 0.5
grid_import = 9.5
soc_end = 0.1
```

## 10. Case 9：储能效率损耗

输入：

```text
两小时：
load = [10, 20]
renewable = [20, 10]
P_bess = 10
E_bess = 20
soc_initial = 0.5
soc_min = 0
soc_max = 1
eta_charge = 0.9
eta_discharge = 0.9
allow_export = false
```

第 1 小时：

```text
surplus = 10
charge = 10
battery increase = 9
```

第 2 小时：

```text
deficit = 10
可放电足够
discharge_to_load = 10
battery decrease = 10 / 0.9 = 11.111...
```

预期：

```text
储能损耗 > 0
SOC 不越界
负荷平衡成立
```

## 11. Case 10：8760 / 8784 行校验

输入：

- 8760 行数据：应通过；
- 8784 行数据：应通过；
- 8759 行数据：应报错；
- 三条曲线行数不一致：应报错。

## 12. Case 11：自发自用两种算法一致性

对每小时检查：

```text
load - grid_import == direct_self_use + bess_discharge_to_load
```

容差：

```text
1e-6
```

## 13. Case 12：SOC 滚动

检查：

```text
SOC_start[t+1] == SOC_end[t]
```

容差：

```text
1e-9
```

## 14. Case 13：储能不能同时充放电

每小时检查：

```text
not (bess_charge > 0 and bess_discharge > 0)
```

## 15. Case 14：政策指标判断

构造方案：

```text
self_use_rate = 0.59
green_load_rate = 0.31
export_rate = 0.10
```

预期：

```text
pass_policy = false
fail_reasons 包含 自发自用率不足
```

## 16. Case 15：全部容量为 0

输入：

```text
C_pv = 0
C_wind = 0
P_bess = 0
E_bess = 0
```

预期：

```text
全部负荷由电网购电
无除零错误
政策指标能够安全返回 0 或 null
```
