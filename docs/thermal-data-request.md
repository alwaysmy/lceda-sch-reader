# Fresnel V2.1 热模型输入清单

`pcb_workbench thermal` 不会为缺失的器件功耗/封装热阻猜数。当前能自动
读取的是 **PCB 实际叠层** 和 **封装 footprint**；下面这些必须由
datasheet、实测或供应商提供。

## 已确认/可直接用的数据

| 项 | 值 | 来源 |
|---|---|---|
| 板叠层 | Top 1.378 mil / 7628 8.283 / Inner1 0.598 / 1.1 mm core / Inner2 0.598 / 7628 / Bottom 1.378，总 1.586 mm | `.epcb2` `LAYER_PHYS` |
| U601 封装 | 24-LFCSP 4×4 mm，θJC = **1.65 °C/W**，θJA = **37 °C/W** | ADN8834 datasheet |
| U602 | FTC252012S1R0MBCA，DCR **35 mΩ typ / 42 mΩ max** | 器件规格书 |
| L214 | SWPA6045S680MT，DCR **289 mΩ typ / 376 mΩ max** | 器件规格书 |
| L602/L603 | GZ2012D601TF，DCR **300 mΩ** | BOM/器件规格书 |

## 必须补的输入

### 1. 工作点

- TEC 实际电流（RMS/DC）和 TEC 电压；当前 PDN demo 用 0.5 A 只是假设。
- `+3V5_TEC` 总电流，以及 L600/L601/L602/L603 各自的电流分配。
- U602 的 RMS 电流（TEC 斩波波形）和开关频率。
- U900 模块的 TEC/激光器热耗；这部分不在 PCB 铜里，必须单独给。

### 2. 器件功耗

每个器件给 `power_w`，或给 `loss_model: i2r` + `current_a` +
`resistance_ohm`（工具按 `I²R` 算）。U601 还需要开关/导通/静态损耗
分解；不能只拿“1.5 A 控制器”当功耗。

### 3. 封装热阻

- `three_node`：`theta_jb`（结到板）、`theta_jc`（结到壳）、
  `theta_ca`（壳到环境，含对流/辐射条件）。
- `two_node`：`theta_jb` + `theta_ja`。
- 每个值必须给 `source` 和 `data_quality`（datasheet/measured/vendor/
  estimate）；estimate 会保留标记，不会伪装成 datasheet。
- U601 目前只有 θJC/θJA，**缺 θJB/θCA**；不能从 θJA 反推 θJB。
- U602/L214/L602/L603 只有 DCR，**没有封装 θ**；需要供应商热阻、
  JEDEC 测试或实测。
- U900 是 DFB 激光器模块，PCB 上没有它的封装热模型；需要模块 datasheet
  或热界面/散热器实测。

### 4. 边界条件

- 环境温度；自然对流还是强制风冷，风速/风道。
- 板子安装方式（水平/垂直、是否贴散热器、是否在密闭腔体）。
- 上/下表面换热系数、板边换热、辐射发射率。
- U900/激光器与板/壳体的热连接（TIM、螺钉、压接）。

## 当前状态

`specs/thermal_fresnel.template.json` 只填了已确认的 θJC/DCR，其余是
`null`。直接运行会被拒绝，并列出缺失项；这是有意的：

```text
$ python -m pcb_workbench thermal ... --spec thermal_fresnel.template.json
热模型输入不完整，拒绝运行：
 - 缺少 ambient_c
 ...
 - U601 缺少有效 theta_jb
 - U602 loss_model=i2r 但缺 current_a
```

在数据补齐前，不会发布 Fresnel 的器件结温/板温数字。
