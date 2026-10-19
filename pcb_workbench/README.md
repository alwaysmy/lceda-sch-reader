# PCB 工作台（V4 `.epcb2` 源码读取 + 意图式区域渲染）

只读工具，面向**布局审阅**：把 V4 文件夹工程（`.eprj3`）里的
`pcb/*.epcb2` 直接解析成「器件 / 焊盘 / 走线 / 过孔 / 覆铜 / 网络」，
并渲染成按**网络**着色的局部图。

## 为什么直接读 `.epcb2`

官方 `lceda_pcb.py extract`（`.epro2` 导出）在本工程会因 **MULTI 层矩形
FILL 挖孔** 报 `UNSUPPORTED_MULTI_CUTOUT`；而 `.epcb2` 源码里
`LINE/VIA/POUR` 自带 `netName`、`PAD_NET` 自带 `padNet`，足以做网络级
几何分析，不依赖导出几何与 Shapely。

## 用法

在仓库根目录执行（模块方式）：

```bat
rem PCB 概要 + 网络走线统计
python -m pcb_workbench stats  "C:\path\Fresnel_V2.1_LaserDriver_EVM" --pcb PCB1

rem 某器件焊盘网络
python -m pcb_workbench pads   "C:\path\..." --pcb PCB1 --designator U601

rem 局部渲染：U601 周围 350 mil，只看 Top 层
python -m pcb_workbench render "C:\path\..." --pcb PCB1 ^
       --around U601,350 --layers top --scale 3 --out u601.png

rem 指定矩形区域 x1,y1,x2,y2（mil）+ 多层
python -m pcb_workbench render pcb\PCB1.epcb2 ^
       --region 250,-3300,850,-2700 --layers top,inner1 --out region.png
```

`--pcb` 可给标题（`PCB1`）或文件名（`PCB1.epcb2`）；工程有多个 PCB 时必填。

## 渲染为什么是「意图式」

不是通用 EDA 截图，而是为审阅问题服务：

- **颜色 = 网络**（不是层）：一眼看出 TEC_POS/TEC_NEG/ PVIN/VREF 怎么走、
  和谁靠近；`--layers` 再按层过滤，避免多层叠色误判。
- **圆头线帽 + 关节补全**：逐段 `LINE` 渲染在 45°/T 型关节处会留下缺口；
  现在每段两端补半径 `width/2` 的圆盘，转角连续。
- **2× 超采样 + LANCZOS**：边缘平滑，细线不糊。
- 覆铜以低透明度铺底，走线/焊盘/过孔在其上；位号直接标在器件位置。

## 边界（不能当制造签核）

- 焊盘只取 `defaultPad`（ROUND/RECT），不展开 `specialPad`；
- 覆铜只画 `POUR` 路径，不处理挖孔/孤岛/热焊盘；
- 当前工程无 ARC 铜；若遇到圆弧铜只画直线段（会退化）；
- 不处理丝印/阻焊/装配层；不做 DRC、间距检查、热仿真；
- 坐标 mil，Y 向上；与 SCH 的 0.01 inch/Y 向下语义不同，跨域换算请显式处理。

## 文件

| 文件 | 作用 |
| --- | --- |
| `v4.py` | `.epcb2` 日志解析、器件/焊盘/网络/走线/覆铜数据模型、网络统计 |
| `render.py` | 意图式渲染（网络配色、层过滤、圆头关节、超采样） |
| `cli.py` | `stats` / `pads` / `render` 三个子命令 |

回归：`probes/verify_pcb_workbench.py`（含 45° 转角补全的像素级断言）。
