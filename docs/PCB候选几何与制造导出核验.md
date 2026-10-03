# PCB 候选几何与制造导出核验

## 范围和入口

现有 `lceda_reader.py` 继续负责三后端原理图查询与 `pcbsch` 清单核对。
新增 `lceda_pcb.py` 是独立、可选的 PCB 导出后端，不改旧 SCH JSON、
坐标系或日志重放；没有加入热仿真求解器。

支持一个 `.epro2` ZIP 中恰好一个 `.epru`，或直接传入 UTF-8 `.epru`。
不解包到磁盘，不自动选取多个成员之一，不支持原生 `.eprj3`。
文件与解压后日志默认各限制 256 MiB。

```sh
# 仅标准库；列出活动 PCB
python lceda_pcb.py project.epro2 list
python -m pip install -r requirements-pcb.txt
python lceda_pcb.py project.epro2 extract --pcb PCB_UUID \
  --profile observed-export-v1 --output pcb.json

# 只有显式允许才修复无效多边形；逐项保留修复证据
python lceda_pcb.py project.epro2 extract --pcb PCB_UUID \
  --profile observed-export-v1 --repair-invalid --include-primitives -o pcb-audit.json
```

多 PCB 必须指定 UUID；标题只有完全匹配且唯一时可用。已删除文档和封装
不会作为目标，缺封装不会生成占位铜皮。已有输出路径拒绝覆盖，包括原工程。

## 重放策略

SCH 后端保留既有 `(段序,ticket)` 规则。新 PCB 后端提供：

- `auto` 默认分别计算两套最终状态，仅在两者一致、各自无同逻辑时钟冲突时接受
- `segment-ticket` 后段优先，同段按 ticket，用于已确认的旧日志约定
- `ticket-client` 全局 ticket 大者优先，同 ticket 取 client 字典序小者；
  仅在核实导出方言后显式选择

`--replay-policy` 放在 `list/extract` 前，不能从后缀推断规则。
空载荷/空字符串/null 是原子删除；`DELETE_DOC.isDelete` 必须是布尔值并允许
恢复。保留输入 SHA-256、段版本、获胜记录 line/segment/ticket/client、删除
状态来源。DOCHEAD 不作为普通原子判优。歧义不会改变旧 SCH 行为。

## observed-export-v1 是实测方言，不是全 V3 兼容声明

旧公开规范与较新编辑器导出存在字段/单位差异，因此 profile 必须显式选择。
不能按 CANVAS 的显示单位缩放。当前有导出及实现证据的约定为：

- PCB/封装坐标和物理厚度：mil × 0.0254 → mm
- POURED.pourFill 缓存坐标：0.01 inch × 0.254 → mm
- 底面器件：先局部镜像 Y，再逆时针旋转，再平移
- RECT pad 圆角是短边一半的百分比；R 路径第七项是长度半径
- POLYGON pad 已在封装局部定位，不重复应用 padAngle/center
- ROUND 孔直径取 height；孔旋转 → 偏移 → padAngle → pad centre
- 实心覆铜制造包络包含 owner.fineness/2 的圆角边界扩张
- 铜层 FILL CIRCLE 的制造直径为 `2*radius + width`
- SOLID MULTI FILL 圆为 NPTH 材料去除，直径 `2*radius`，不加显示线宽
- PROHIBIT REGION 只保存为约束元数据，不从最终缓存铜再减一次，也不当成板孔

目前拒绝特殊分层焊盘、非圆 ELLIPSE、旧式 POLY pad、负片 PLANE、盲埋/
规则跨度过孔、封装内过孔、非零封装原点、未知铜图元、开放铜 POLY、非实心
覆铜、未经核实的槽区/REGION、多板分区、活动拼版和未知几何覆盖。
这些失败边界不能写成“已完全支持”。

## XY 几何和物理堆叠分开

铜层来自活动 LAYER 类型，外层由 TOP/BOTTOM 身份确定，不硬编码四层。
完整堆叠需要每一铜层的正厚度、物理顺序，以及相邻铜层间的正厚度分隔。
不从材料标签猜热导率，标签与层角色明显冲突时保留不完整状态。

XY 可提取而堆叠不全时，`copper_order`、`total_thickness_mm` 和不确定的
`z_depth_mm` 为 null；`active_copper_layers` 按数字 ID 排列，仅是集合序列化，
不是物理顺序。不补 1.6 mm，不虚构 FR-4 参数。NORMAL 贯穿孔可覆盖全部
活动铜层，但不推断盲孔跨度。

`--require-stackup` 在堆叠不完整时失败；`--strict` 在已观察的几何/网归属/
堆叠缺口时退出 3。退出 0 仍不表示制造正确、全项目完整或电气签核。

## IR、孔和缓存

Schema 为 `schemas/pcb-ir-v1.schema.json`，输出单位统一 mm。XY 保留原 PCB
坐标（X 右/Y 上）；Z 为入板深度，未声称这个组合为右手坐标系。

- `components/pads/vias` 是选中 PCB 的实例；pad 包围盒不是封装实体
- `holes` 保留所有独立孔的形状、镀层、来源与贯穿端点
- `plated_through_holes` 仅含 PTH pad，不重复 vias；`nonplated_through_holes`
  包含 NPTH pad 和已验证圆形材料去除。制造检查必须同时覆盖 PTH 和 NPTH
- `geometry` 自包含板轮廓、扣孔基材、孔并集及各铜层并集；铜已扣贯穿孔并
  裁剪到板轮廓。原语 ID/层/net/来源始终保留，`--include-primitives` 附其多边形
- 缺 PAD_NET 保留 null；显式空字符串表示未分配网络，不把两者混为一谈
- orphan POURED 不参与铜；活动 POUR 缺缓存、缓存显式早于 owner 时失败。
  不拿 POUR 边界代替最终铜，ticket 新也不证明缓存有效
- 默认拒绝无效多边形。显式修复后记录面积变化/非面残留并保持
  `geometry_complete:false`，等待拓扑检查和制造导出比较

`status:candidate`、`manufacturing_verified:false`、`net_connectivity_verified:false`
始终保留。`coverage.complete` 仅指支持范围内的选中 PCB。实际功耗、封装热
接触、镀铜厚度、热材料参数、风道和外壳等仍未知，不能直接宣称热仿真成立。

## 独立制造比较

`scripts/pcb_compare_exports.py` 依赖 `requirements-pcb-validation.txt`。
核心读取/几何支持 Python 3.10+；制造比较器的 gerbonara 1.6.3 明确要求
Python 3.12+，CI 分别验证这两个环境范围，不自动降级到未核验的解析器版本。
它不负责打开编辑器、重新覆铜或导出，不带厂商安装包/激活文件/私有原生代码。

先确认是同一 PCB 和版本的官方导出，再明确传入层映射、导出单位、原点平移、
离散容差和接受阈值。工具不自动对齐，保留板外铜差异，不裁掉误差来促成通过。
报告统计对称差/交集/覆盖率，并绑定 IR、导出、参数和验证器版本的哈希。
哈希只能标识文件，不能证明同板同版本或官方来源。

```sh
python -m pip install -r requirements-pcb-validation.txt
python scripts/pcb_compare_exports.py --help
# 示例阈值仅演示语法，必须按导出精度和检查目的自行确定
python scripts/pcb_compare_exports.py --ir pcb.json \
  --copper 1=top.gbr --copper 2=bottom.gbr \
  --drill plated-through=pth.drl --drill nonplated-through=npth.drl \
  --gerber-units mm --drill-units mm --offset-x-mm 0 --offset-y-mm 0 \
  --tolerance-mm 0.0002 --max-xor-area-mm2 0.01 --max-xor-fraction 0.0001 \
  --min-overlap-fraction 0.99 --out comparison.json
```

如果 PTH_Through 已含 vias，不能再叠加 Via 子集；还要 NPTH_Through。
“PTH/过孔匹配”不能推出“全部孔匹配”。比较只检查几何覆盖，不证明
加工操作次数或实际镀层。部分层/孔角色、IR 本身不完整时始终为 partial；
comparison complete 仅表示比较覆盖，不是制造签核，也不会修改 IR 为已验证。

官方 Gerber 可能用回折桥接表达带孔区域，也可能出现极小的端点交叉。
默认严格拒绝无效/非面几何；只有显式 `--repair-invalid` 才进行有记录的修复，
并且比较始终保持 partial。修复报告会记录来源、前后哈希、面积/拓扑变化及
丢弃的非面残留，完整报告可能很大，不能把它当作未修复数据的通过证明。
钻孔比较也受圆弧离散精度影响：先与 IR 中记录的曲线容差一致，并检查实体
中心、直径/槽形的一一对应；不通过放宽接受阈值来掩盖缺孔或错误孔径。

## 测试与隐私

```sh
python -m unittest discover -s probes -p test_reader_portable.py -v
python -m unittest discover -s probes -p test_pcb_replay.py -v
python -m pip install -r requirements-pcb-test.txt
python -m unittest discover -s probes -p 'test_pcb*.py' -v
python probes/verify_sch_compatibility.py --baseline /baseline/lceda_reader.py \
  --synthetic --input /private/export.epro2 --output /private/sch-regression.json
```

公开测试全部程序生成、纯虚构；用户原工程、真实制造文件、私有网名和原始
诊断不入库。私有回归只输出匿名数量和哈希。旧 `smoke2.py` /
`verify_all_formats.py` 需要各自指定样本；缺失不能由合成测试冒充通过。
