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
| `cli.py` | `stats` / `pads` / `render` / `layers` 子命令 |

回归：`probes/verify_pcb_workbench.py`（转角像素断言 + 精确面积/覆盖率/
缓存状态 + 实板 pad 面积）。
