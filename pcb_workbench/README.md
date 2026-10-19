# PCB 工作台（V4 `.epcb2` 源码读取 + 意图式/精确几何渲染）

只读工具，面向**布局审阅**：把 V4 文件夹工程（`.eprj3`）里的
`pcb/*.epcb2` 直接解析成「器件 / 焊盘 / 走线 / 过孔 / 覆铜 / 网络」，
渲染成按**网络**着色的局部图，并可选 Shapely 布尔几何做精确铜层。

## 为什么直接读 `.epcb2`

官方 `lceda_pcb.py extract`（`.epro2` 导出）在本工程会因 **MULTI 层矩形
FILL 挖孔** 报 `UNSUPPORTED_MULTI_CUTOUT`；而 `.epcb2` 源码里
`LINE/VIA/POUR` 自带 `netName`、`PAD_NET` 自带 `padNet`，足以做网络级
几何分析，不依赖导出几何。

## 用法（仓库根目录）

```bat
rem PCB 概要 + 网络走线统计（--exact 额外算每层精确铜面积）
python -m pcb_workbench stats  "<工程目录>" --pcb PCB1 [--exact]

rem 某器件焊盘网络
python -m pcb_workbench pads   "<工程目录>" --pcb PCB1 --designator U601

rem 局部渲染：U601 周围 350 mil，只看 Top 层
python -m pcb_workbench render "<工程目录>" --pcb PCB1 ^
       --around U601,350 --layers top --scale 3 --out u601.png

rem 精确几何（POURED 实铜缓存 + 全焊盘 + 孔挖除）
python -m pcb_workbench render "<工程目录>" --pcb PCB1 ^
       --around U601,350 --layers top --exact --arc-tol 0.05 --out u601_exact.png

rem 逐铜层渲染 + 面积统计（Top/Bottom/Inner1/Inner2 + 合成图）
python -m pcb_workbench layers "<工程目录>" --pcb PCB1 ^
       --around U601,350 --scale 2 --outdir layers [--approx]

rem 批量 DFM：走线宽度 / 覆铜窄颈 / 同层间距 / 过孔环宽
python -m pcb_workbench dfm "<工程目录>" --pcb PCB1 ^
       --min-track 0.20 --min-neck 0.20 --min-clearance 0.15 ^
       --min-annular 0.10 [--layers top,bottom] [--json]
```

`--pcb` 可给标题（`PCB1`）或文件名（`PCB1.epcb2`）；工程有多个 PCB 时必填。
`--layers top|bottom|inner1|inner2|all|1,2,15,16` 可组合；坐标单位 mil。

## 两种精度

| 模式 | 覆铜 | 焊盘 | 孔 | 用途 |
|---|---|---|---|---|
| 默认（审阅） | `POUR` 边框填充 | `defaultPad` 近似（RECT/ROUND） | 过孔画圆环 | 快速看网络走向/器件位置 |
| `--exact` | **`POURED` 实铜缓存**（含 clearance/热焊盘/挖孔），按 owner `fineness` 半宽描边 | RECT(圆角百分比)/OVAL/ELLIPSE/POLYGON + padOffset/relativeAngle | 过孔 + THT 圆孔/槽孔挖除 | 面积、铜覆盖率、层视图、近邻/间距粗判 |

`--exact` 的几何是 **Shapely 多边形布尔并集**（按层/按网络），不是 EDA
截图；渲染只负责上色。`--arc-tol` 控制 `POURED` 里 ARC 段的弦高容差。

### 精确模式的边界（必读）

1. **铺铜缓存可能落后**：`POURED` 是上次覆铜的快照；若之后又改了走线/
   焊盘，本工具不会重算铺铜。`stats --exact` / 渲染会在
   `max_cache_ticket < max_copper_ticket` 时告警（本工程当前即如此：
   214379 < 216391，需在 LCEDA 重新覆铜才是最终铜）。
2. 圆弧按弦高采样（默认 0.05 mil），不是解析弧；面积误差很小但非零。
3. `specialPad`（自定义多形状焊盘）未支持，按 `defaultPad` 处理并告警
   （本工程为 0 个）。
4. MULTI 层的机械挖孔/槽不参与铜布尔（本工程的大矩形 MULTI FILL 不是
   铜挖孔；若你的板用它做 NPTH，需要单独扣除）。
5. 不做 DRC/间距/热/制造签核；Gerber 对拍仍是独立步骤。

## DFM 批处理（第一版）

`dfm` 子命令基于精确几何做批量检查，输出 JSON 或可读清单：

| 检查 | 方法 | 说明 |
|---|---|---|
| `track` | 记录值 | 走线宽度 < 阈值；精确到 `LINE.width` |
| `neck` | 矢量腐蚀拓扑 | 覆铜窄颈/热焊盘辐条/孤立窄铜；检测“连通分量变化”的最小宽度，非真骨架宽度 |
| `clearance` | Shapely 距离 | 同层不同**命名网络**的最小间距；铺铜缓存落后时只用走线/焊盘/过孔，避免缓存假重叠 |
| `annular` | 记录值 | 过孔/THT（ROUND 孔）环宽；跳过 NPTH/无网络机械孔 |

**边界**：不检查阻焊/丝印/孔到铜/孔间距/板边间距；`neck` 对平滑渐变颈缩
可能低估；clearance 不含无网络铜（机械/图形）；结果受 `POURED` 缓存新鲜度
影响（会告警）。这是 DFM 辅助清单，不是制造签核。

回归：`probes/verify_pcb_dfm.py`（松/严阈值双向断言、空网络过滤、缓存字段）。

## PDN 2.5D FDM + 热力图

`pdn` 子命令把选中网络的**精确铜几何**栅格化成电阻网络，解电压场，
输出逐层电压/电流密度和总电流密度热力图；`--thermal`（默认开）再做
一个简化的 2D 热扩散，输出温度图。

```bat
python -m pcb_workbench pdn "<工程目录>" --pcb PCB1 ^
       --spec pcb_workbench\specs\pdn_tec_neg.json ^
       --outdir pdn_out [--grid 0.05] [--no-thermal] [--json]
```

Spec 是 JSON（不需要 PyYAML）：

```json
{
  "net": "TEC_NEG",
  "voltage": 1.0,
  "current": 0.5,
  "source": {"designator": "U602", "pad": "2"},
  "sinks": [{"designator": "U900", "pad": "14"}],
  "layers": [1, 2],
  "grid_mm": 0.05,
  "board_mm": 1.6,
  "ambient_c": 25,
  "convection_w_m2k": 10,
  "copper_um": {"1": 35, "2": 35, "15": 15, "16": 15},
  "thermal": true
}
```

- `source` 焊盘固定为 Dirichlet 电压，`sinks` 分担总电流；源/汇必须在
  **同一个连通铜分量**内，否则报错并给分量编号，不会静默跨岛。
- `layers` 用 LCEDA 层号（1=Top，2=Bottom，15=Inner1，16=Inner2）。
  省略时用全部铜层。
- `copper_um` 给每层铜厚；外层默认 35 µm、内层默认 15 µm。
- `grid_mm` 默认 0.1 mm；细走线/窄颈建议 0.05 mm。
- 过孔按镀铜桶电阻连接相邻层（默认 25 µm 镀层、板厚 `board_mm`）。

输出：

```
pdn_<net>_L1_voltage.png / _current.png   # 逐层
pdn_<net>_voltage_all.png                 # 各层取最大电位
pdn_<net>_current_all.png                 # 各层取最大
pdn_<net>_thermal.png                     # 简化 2D 温度
pdn_<net>_summary.json                    # IR drop / R / Jmax / P / Tmax
```

图上深灰是**同层其他网络铜**作为上下文，彩色是选中网络的场；`SRC`/
`SINK` 是焊盘中心。电流图默认按 99.5% 分位裁剪色标（标题保留真实最大值），
避免单个网格热点把其余区域压成蓝色。

### 模型与边界

- 每层 4 邻域薄铜片，`G = σ·t`（S）；层间过孔 `R = ρL/A`。
- 稀疏线性系统 `A·V=b`，源固定电压、汇注入负电流；只保留源汇所在
  连通分量，孤立铜岛丢弃并在 `dropped_nodes` 计数。
- 电流密度由边电流 `|I|/(t·h)` 得到；功率按 `I²/G` 累加（含过孔）。
- 热模型：铜/FR4 等效面导热 + 上下表面对流（`h` 为总对流系数，两侧各
  `h`），热源是 PDN 功率；不含 TIM、器件、风道、辐射和 3D 过孔导热。

**精度校验**：单层直导线 FDM 与 `R=ρL/(wt)` 对比误差 **0.5%**
（`probes/verify_pdn_solver.py`）。Fresnel TEC_NEG 在 0.5 A 下：
0.1 mm 网格 IR drop 25.35 mV，0.05 mm 网格 27.35 mV（约 8% 网格差），
对应 R≈50.7–54.7 mΩ、P≈12.6–13.6 mW；最大电流密度对网格更敏感，
只用于 hotspot 定位。**这是设计预检，不是制造/热签核**；最终 PDN 用
PADEN/padne 交叉验证，热用 Elmer/PrePoMax 或实测。

## 渲染为什么是「意图式」

不是通用 EDA 截图，而是为审阅问题服务：

- **颜色 = 网络**（不是层），一眼看出 TEC_POS/TEC_NEG/PVIN/VREF 怎么走、
  和谁靠近；`--layers` 再按层过滤。
- **圆头线帽 + 端点圆盘**：逐段 `LINE` 渲染在 45°/T 型关节处会留缺口，
  现每段两端补 `width/2` 圆盘；2× 超采样 LANCZOS。
- 分层视图逐层输出（Top/Bottom/Inner1/Inner2），可加合成图。

## 文件

| 文件 | 作用 |
| --- | --- |
| `v4.py` | `.epcb2` 日志解析、器件/焊盘/网络/走线/覆铜数据模型、网络统计 |
| `render.py` | 意图式渲染（网络配色、层过滤、圆头关节、超采样）+ `--exact` 入口 |
| `exact.py` | Shapely 精确几何：POURED 缓存、全焊盘、孔、ARC 采样、层并集/面积 |
| `pdn.py` | 2.5D FDM PDN（电压/电流密度/功率）+ 简化 2D 热 + 热力图 |
| `cli.py` | `stats` / `pads` / `render` / `layers` / `dfm` / `pdn` 子命令 |
| `specs/` | `pdn_tec_neg.json`、`pdn_3v5_tec.json` |

回归：`probes/verify_pcb_workbench.py`（转角像素断言 + 精确面积/覆盖率/
缓存状态 + 实板 pad 面积）；`probes/verify_pdn_solver.py`（解析直导线
0.5% + 实板 TEC_NEG 求解/功耗/连通性 smoke）。
