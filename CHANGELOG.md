# CHANGELOG

本仓库**唯一**的变更流水。2026-10-28 起统一到本文件：
此前 `docs/变更记录-<日期>.md` 的内容已全部并入（原文保留、标题层级下调一级），
原文件删除；历史仍可在 git 记录中查到。
历史小节保留当时的工程名/位号/结论，仅作追溯；规范描述以最新小节与
`docs/` 专题文档为准。

## 使用约定

1. **追加位置**：直接加到本文件顶部（最新在上），按 `## YYYY-MM-DD` 分节；
   同一天多次提交继续在该节内补充。
2. **每条写清**：改了什么、为什么改、验证结论（跑了哪些回归 / 逐字节对比结果）。
3. **不再新建**按日期的变更记录文件；专项分析放 `docs/` 独立文档，
   本文件只留摘要 + 指向该文档的链接。
4. **索引**：`README.md`、`AGENTS.md`、`docs/开发文档.md` 均指向本文件。

## 2026-10-29

### 修复 / 增强（pinmap / find）

- 修复 `pinmap` 文本重复别名：此前用已拼接的 `net` 串去比对名字列表，
  导致同一网络的两个名字被重复列出；现改为「主名 + 其余名字」。
  示例：`ID_IN, USART2_RX（别名: ID_IN, USART2_RX）`
  → `ID_IN（别名: PD6, USART2_RX）`。
- `pinmap` 默认**跨页**别名：`resolved_nets` / `aliases` 为全局名字集，
  新增 `net_sheets`（该网络出现的页；文本 `[跨页: …]`，超过 4 页折叠计数）。
  示例：`ID_IN（别名: PD6, USART2_RX）[跨页: 内部通信总线, 外部通信接口, 控制器 …]`。
- 新增 `--no-global`（退回只按本页合并，大工程提速）；全局上下文按 db 缓存。
- 主名改用全局"名字出现引脚数"，避免 `AGND/GND` 这类误选。
- **`find` 同步按全局别名分组**：JSON 新增 `net_groups`
  （`{net, aliases?, sheets?}`），原 `nets` 字段保留；文本改为逐条列出
  `主名（别名: …）[跨页: …]`，不再把同一根线拆成多个名字平铺。
  示例：`ID_OUT（别名: PD5, USART2_TX）`。
- 回归：`verify_alias.py` 增加 pinmap 全局/跨页、find 分组与页集合断言。

### 核对记录（netfind 的适用边界）

- 复核结论：对"某引脚所在网络上有没有某电源"这类问题，`netfind` 是充分的；
  它只返回**同一网络**成员，不跨串阻/磁珠/二极管，因此看不到另一端属于
  **设计边界**而非缺陷。链路要看 `pinmap` / `trace`。
- 示例（某真实工程，作证据保留、不作通用规则）：`netfind PD1` 返回
  `U300.PD1 + R307.1`（2 点）、**不含 `+3V3D`**；`+3V3D` 是另一条 57 点网络。
  该结论正确：`PD1 → R307 → LED1 → GND`，确系 MCU 驱动 LED，不是电源指示。
- 旧缺陷（同一网络多个名字不合并）与本类问题无关；完整核对见
  `docs/网络别名未合并导致连通性漏查-2026-10-28.md` §8。

### 文档

- SKILL 新增「常用排查路径（先 search，再精确查询）」，说明 `search`
  的应用场景（只有关键词时先搜，命中 Name 直接给网络）与后续命令选择。

## 2026-10-28

### 修复（网络别名未合并）

- **端口名入域**：端口 `Name` 压在已命名导线上时不再丢弃，改为以 `NET_SEP`
  多值并入 `net_of` / `sheet["nets"]` / `endp`（原为直接 `continue`）。
- **全局别名闭包**：新增 `build_alias_groups()`（并查集），跨页按名字共现合并
  （A≡B、B≡C → 一组）；`resolve_nets_by_domain` 收集域名时按 token 拆分。
- **输出按物理网络聚合**：`nets` / `netlist` 合并为一行，文本标注
  `（别名: …）`，JSON 仅在存在别名时新增 `aliases`；`netfind` 按别名组匹配，
  查任一名字返回整组；`pinmap` 文本标注别名、JSON 追加 `aliases`。
- **主名规则**：`pick_primary_name`（非引脚自动名优先 → 引脚数多者 → 字典序），
  只影响显示与 `net` 字段，不影响查询。判定"引脚自动名"仅认整串
  `[A-Z]{1,3}\d{1,3}`（`PD5`/`PA11`）；`PD6_UART_TX1`/`GPIOA1`/`PD1234` 不算，
  `CS1`/`D1` 会算但仅影响显示；名字全集始终保留在 `aliases`，已有回归用例。
- **报告**：`--json-report` 的 `completeness_scope` 增加 `alias_closure`，
  顶层新增 `alias_groups`。
- **回归**：新增 `probes/verify_alias.py`（纯函数 + 端到端同集合断言）。
  改前后 netlist 逐名字等价性：5 个仓库样例 `TOTAL PROBLEMS: 0`（成员/页集合
  只增不减），行数按物理网络收敛（Piezo 267→175、涡流 79→77、TPS 9→8）；
  smoke2 / verify_all_formats / verify_bus / cross_backend_contract 全 PASS。
- **注意（有意的输出变更）**：`netlist`/`nets` 行数改为按物理网络计，
  不再逐名字重复；依赖"每个名字一行"的脚本改用 `aliases` 或 `netfind`。

### 增强（search / polar）

- **`search` 命中 `Name`/`Global Net Name` 时补充所在网络**：输出该名字的
  别名组与连接点（`--json` 行内新增 `net_hints`）。端口名只是排查入口，
  此前只能看到属性行、不知道该名字连了谁。该补充需一次全工程扫描
  （代价同 `netlist`），仅在确有此类命中时触发。
- **`polar` 增加方向与连通性**：改为两遍扫描（先建全局别名闭包），每个
  极性器件输出 `A→K` 正偏方向、两端网络（含 `net_aliases`）与同网连接点
  （`net_member_count`/`net_members`，超 50 截断标记）；未命名一侧给出
  "同线"对象 `wire_peers`（网络名为空 ≠ 悬空）。同时修正 `.epro2`
  页标题重复显示为 `板::板::页` 的问题。
- 新增 `probes/verify_search_polar.py`（search 提示 + polar 方向/别名/同线）。
- 仍**不做**电气裁决：是否存在多驱动/对顶需结合手册与驱动能力人工判断，
  工具只陈列事实（与 `review` 规则的边界一致）。

### 文档

- 新增 `docs/网络别名未合并导致连通性漏查-2026-10-28.md`：
  记录"同一物理连通域存在多个网络名但未合并"的缺陷（通用描述 + 一个工程示例），
  含源码定位、验证判据与改进建议。
- **更正上一版分析的两处错误**：
  - 端口名丢失点不是 `net_of.get(cid) or Name` 那一行（该行在端口无 `NET`
    属性时能正常取到 `Name`），而是传播分支对"已命名导线"的跳过
    （约 3733 行与 3758 行的 fallback）；
  - 工具并非"没有别名功能"：`pinmap` 的 `resolved_nets` 已实现**同页**别名闭包，
    真实缺口是"已命名导线上的端口名不入域"与"别名不跨页闭包"。
- 明确**别名显示与输出标注为必做项**（`nets`/`netlist`/`netfind`/`pinmap`
  文本标注 + JSON `aliases` 字段），规格见该文档 §4 P0-3。
- 拟新增的审查能力（两脚器件方向/角色检查信息输出）列为**待确认**，
  未纳入实现范围。

### 未决

- `aliases` 字段层级与文本措辞，待与 `resolved_nets` 的既有消费者对齐后定稿。
- 两脚器件（二极管/TVS 等）检查的判定口径与误报边界待定。

## 2026-10-26

### 仓库瘦身：移除两个一次性调试转储（约 78 MB）

- 删除并停止跟踪：
  - `probes/full_decrypted.epru`（60.47 MB）—— Piezo 全工程解密明文 dump
    （2026-08-22，commit 89d1326 引入）；
  - `probes/mem_dump.json`（17.28 MB）—— 全工程内存明文 dump
    （2026-08-22，commit f9490b4 引入）。
- 二者只被 `probes/dbg_*` 一次性排查脚本引用，不参与任何回归/工具运行。
  删除后工作区减少约 78 MB。
- **git 历史未重写**：两个文件仍存在于历史提交中，可按需恢复
  （如 `git show 89d1326:probes/full_decrypted.epru`）；因此本次不改变
  已有 clone 的下载体积。若日后需要彻底减小 clone，再做历史重写
  （需先备份并通知协作者）。
- `.gitignore` 增加两条，防止调试脚本重新生成后被误提交。

### 工具与参考

- 新增正式差分工具 `probes/compare_reader_versions.py`（从 `probes/tmp`
  一次性脚本提炼）：对比两个 reader 版本的 netlist 输出，支持多目录扫描、
  JSON 报告与差异明细；退出码 0=无差异、1=有差异/失败方式不一致、2=参数错误。
- `probes/verify_eprj3_backend.py` 默认参考改为仓库自带
  `probes/data/eprj3_ref/Fresnel_V2.1_LaserDriver_EVM_2026-10-22.epro2`
  （晚于工程最后修改），不传参数运行 ALL PASS（13 页 1875 引脚零差异）。
- 未跟踪的一次性排查脚本 `probes/sch_v21_probe.py` 继续保持不跟踪。

## 2026-10-19

### 修复：`pinmap` 漏报同器件内引脚互连（按 designator 排除粒度过粗）

#### 现象
`pinmap` 对“同一器件两个引脚被导线/短接直接相连”的引脚输出为
`net` 空、`peers`/`wire_peers` 全空——与真正未接线完全无法区分。审查时
会把这类引脚误判为悬空：

- **ADN8834 数字 PID**：手册要求 `IN2N`–`OUT2` 短接（Chopper 2 作 DAC 缓冲），
  本工程 `LaserDriver EVM::TEC Controller` 页 U601 实际已用一段 20 单位导线
  相连（wire `db847d850c71555c`，端点 (535,300)/(555,300)），但 pinmap 只显示
  `(未命名)`，无任何 peer；
- 堆叠电源/地引脚（U601 `PGNDS#12`/`PGNDS#13`/`EP` 同线）互相不可见；
- 运放跟随器 `-IN↔OUT` 短接（DAC 页 U403、Howland 页 U501）同样被隐藏。

#### 根因
`cmd_pinmap` 计算 peers/wire_peers 时用 `if odes == des: continue` 跳过
**整个 designator**（lceda_reader.py 原 3261/3279 行，初始提交 355d3c2 引入，
无提交说明）。该排除的初衷是避免“本引脚列自己”，但粒度错了：
1. 同器件内两脚相连是真实网络连接，应显示（与跨器件连线同义）；
2. 多单元符号（同页多个 part 共用 Designator、不同 cid，本工程 AD7175 的
   U600、OPA1678 的 U501 都是）之间的互连也会被一并跳过。

#### 修复
改为只排除**本引脚自身**（`op is p`），两条循环（`hit_pt` 同点、`hit_wires`
同导线）同步修改；peer 标签仍为 `位号.引脚名`，JSON 字段与文本格式不变。
`peers` 仍表示同物理坐标（堆叠引脚），`wire_peers` 仍表示同一 WIRE 记录上的
其他端点，二者都新增“同器件”条目。

#### 验证（本机）
- **全页 pinmap 快照对比**（本工程 13 页、977 个器件行）：
  - 新增 peer 标签 **272 条，全部为同 designator**；删除 **0**；
  - `net`/`nets`/`resolved_nets`/`not_connected`/`pin_type`/`net_inferred`
    等语义字段**零变化**；
  - 受影响 43 行，分布：Power Supply 94、Howland 80、MCU 54、TEC Controller 16、
    ADP5071 12、Volt Reference 10、DAC 6（条）。
- **新增回归** `probes/verify_pinmap_self_peers.py`（PASS）：
  U601.IN2N↔OUT2、PGNDS#12/#13/EP 堆叠互连、TMPGD 仍为真悬空、
  U403.-IN↔OUT，**RN500/RN501/RN502 跨 part 串接（8–7、6–5）**，以及
  “任何引脚不得把自己列进 peers / 列表无重复”的过修防护。
  注：RN500/501/502 是 4 电阻阵列（4D03）拆成多个 part（同页同 Designator、
  不同 cid，引脚 1-8/2-7/3-6/4-5），工程把两组画成串接；修复前这两对互相
  不可见，正好作为“多单元符号跨 part 直连”的真实样本（无需另造 fixture）。
- **既有回归** `probes/regress_fresnel_v21.py`（PASS）：43 项断言全过；
  其中“残留 CBB 模板页告警”一条原断言只认旧文案 `CBB 模板页`，现按
  `CBB 模板页` 或 `INSTANCE 引用模板页` 任一命中通过（告警文案在
  fc66699 调整过，属回归脚本滞后，与本次修复无关；已在 HEAD 版本复现该
  FAIL 以确认）。

#### 兼容性 / 边界
- 仅影响 `pinmap` 的 peers/wire_peers 列表（附加信息），不改变网络名解析、
  连通域、trace/netlist 结果；`--json` 结构不变。
- 坐标精确匹配口径未变；无 Symbol/引脚定义失败的器件仍不参与（原有限制）。
- 同点堆叠引脚较多的大符号（如多 PGND 并联）会列出更多 peer，属真实连接，
  属预期行为。

### 顺带修复：portable 测试在 Windows 上 22 例误报（文件句柄未关闭）

- **现象**：`python -m unittest discover -s probes -p test_reader_portable.py`
  31 例中 22 例 ERROR，均为 tearDown 删除临时目录时
  `PermissionError [WinError 32] ... generic.eprj2`；测试断言本身全过。
- **根因 1（夹具）**：`write_fixture` 用 `with sqlite3.connect(...)`——sqlite3
  的 with 只提交、不关闭连接，fixture 文件被锁到 GC 才释放。改为显式
  `conn.close()`（并注明 Windows 删除锁原因）。
- **根因 2（产品入口）**：进程内调用 `main()` 时后端从不关闭；`SystemExit`
  的 traceback 持有 `dbs` 引用，句柄在临时目录清理时仍打开。新增
  `SchemaBackend.close()`（幂等，关闭 cur/conn/zip 并置 None），`main()`
  用 `try/finally` 在返回/`sys.exit`/异常时统一关闭。
- **验证**：portable 31/31 OK；`regress_fresnel_v21`、`verify_all_formats`、
  `cross_backend_contract`、`verify_dnp`、`verify_netgraph`、`verify_rules`、
  `verify_bus` 全 PASS；`--json-report --strict netlist` 仍按本工程既有 CBB
  残留诊断（CBB200→cefa2070d90911b2）退出 3，属预期。

### 已知问题（本次未修）：多单元符号跨 part 同名引脚

- 扫描 6 个示例工程 + 本工程（260 页 / 24,433 个 tag）：仅 Piezo“废案存档”
  页 U36（双运放拆两单元，均有 `IN+`/`IN-`/`OUT`）出现同名 tag；该页两个
  单元的同名引脚**全部悬空**，当前无实际错网。
- **风险**：若同名引脚接在不同网络上，`resolve_nets_by_domain` 按
  `(designator, pin_key)` 合并会互相覆盖，`pinmap.resolved_nets` 与 peer
  tag 会指代不明（`set()` 去重还会少报）。
- **建议**：在 `_collect_pinmap_data` 做页级 key 去重（同页同位号跨 cid
  冲突时补 `#number`）。这属于输出契约变更（`pin` 字段），需单独评估并跑
  全量回归，本次未改。

### 新增：Eprj3DB（V4 文件夹工程）只读后端

- 支持 `--eprj <工程目录>` 或 `<工程>.eprj3`；内容校验要求实际
  `sch/*.esch2` 或 `pcb/*.epcb2`，空 JSON/无结构目录仍按不支持拒绝
  （保持 "不凭扩展名冒充支持" 的门禁契约）。
- 记录模型：V4 行日志 `{type,id,ticket}||{data}|`，同 id 取 ticket 最大；
  docType 为字符串；符号类型沿用 META.docType（2/17/18/19/22/25）。
- **坐标/旋转标定（8 组矩阵）**：`PAGE_Y_SIGN=+1`、`SYM_Y_SIGN=+1`、
  `ROT_NEGATE=False`——V4 页面/符号坐标数值与 `.epro2` 存储值一致，不翻转
  Y、不取反旋转角。三项参数已固化在 `Eprj3DB` 类上，改动必须重跑
  V3↔V4 全页 pinmap 对比。
- 已支持命令：`list/boards/components/texts/nets/pins/pinmap/netlist/
  netfind/trace/find/search/bom/datasheets/docs/tree/render` 等；PCB 仅
  枚举（`sheet_records(doc_type=3)` 提供属性级数据，`pcbsch` 尚不完整）。
- **验证（Fresnel `.eprj3` ↔ `.epro2`）**：
  - 13/13 页；每页元件数、位号集合完全一致；
  - **1875 个引脚 pinmap 逐引脚网络零差异**；文字坐标 6/6 一致；
  - 新增 `probes/verify_eprj3_backend.py` 全 PASS（含空 JSON 拒绝门禁）。
- 已知边界：V4 文件夹缺 CBB 模板时实例按黑盒保留（与原工程一致）；
  PANEL/变体/仿真文档暂不解析；`pcbsch` 的 PCB 布局核对不完整。

### 新增：pcb_workbench（V4 PCB 源码 + 意图式渲染，独立目录）

- **动机**：官方 `lceda_pcb.py extract`（`.epro2` 导出）在本工程报
  `UNSUPPORTED_MULTI_CUTOUT`（MULTI 层矩形挖孔）；V4 `.epcb2` 源码里
  `LINE/VIA/POUR` 自带 `netName`、`PAD_NET` 自带 `padNet`，可直接做
  网络级审阅，无需导出几何/Shapely。
- **功能**：`stats`（网络线宽/长度/过孔/层统计）、`pads`（按位号列焊盘网络）、
  `render`（按网络着色、层过滤、区域渲染，PNG）。
- **渲染是意图式的**（不是通用 EDA 截图）：颜色=网络（审阅关心网络走向与
  邻近关系），`--layers top|bottom|inner1|inner2` 分层过滤；圆头线帽 + 端点
  圆盘补全 45°/T 型关节；2× 超采样 LANCZOS。
- **修复转角缺口**：此前逐段 `LINE` 直绘，斜角/丁字关节外侧留缺口；现在每段
  两端补 `width/2` 圆盘。`probes/verify_pcb_workbench.py` 用合成 45° 折线做
  像素级断言（round 填充、butt 对照留缺口）PASS。
- **实测（PCB1）**：423 元件 / 1367 焊盘 / 2892 走线 / 1276 过孔 /
  59 覆铜 / 270 网络；U601 pad1/2 同网络（IN2N–OUT2）、pad20 无网络。
- **边界**：焊盘只取 defaultPad、覆铜只取 POUR 路径；无圆弧铜/挖孔/丝印/
  阻焊/DRC/热仿真，不能作为制造签核。

### 精确几何模式 + 分层视图（pcb_workbench）

- **`--exact`**：用 Shapely 做每层/每网络铜的布尔并集——覆铜取 `POURED`
  实铜缓存（含 clearance/热焊盘/挖孔，按 owner `fineness` 半宽描边）；
  焊盘支持 RECT(圆角百分比)/OVAL/ELLIPSE/POLYGON、padOffset/relativeAngle；
  过孔与 THT 圆孔/槽孔挖除；`POURED` 的 ARC 段按 `--arc-tol` 弦高采样。
  默认仍是快速审阅模式（POUR 边框 + defaultPad 近似），两者并存。
- **`layers` 子命令**：逐铜层渲染 Top/Bottom/Inner1/Inner2 + 合成图，
  并输出每层精确面积（mm²）。缓存复用后本工程 4 层 + 合成约 9s。
- **精度边界（已在 README 写明）**：
  1. `POURED` 是上次覆铜快照；若之后有铜编辑，不重算铺铜。工具用
     `max_cache_ticket vs max_copper_ticket` 告警——本工程实测
     **214379 < 216391，提示缓存可能落后，最终铜需在 LCEDA 重新覆铜**；
  2. ARC 为采样（默认 0.05 mil），非解析弧；
  3. `specialPad` 未支持（本工程 0 个），按 defaultPad 并告警；
  4. MULTI 机械挖孔不参与铜布尔；无 DRC/热/制造签核。
- **实测（Fresnel PCB1）**：Top 6338.228、Bottom 7174.654、
  Inner1 13933.261、Inner2 1559.754 mm²；Inner1 GND 平面覆盖率 95.4%
  （板框 109.2 × 133.5 mm）。U601 pad1 精确面积 288.6 mil²，与
  26.18×11.02 mil 理论值一致。
- **回归**：`probes/verify_pcb_workbench.py` 增加精确几何/覆盖率/pad 面积/
  缓存状态断言，全 PASS；45° 转角像素断言保持 PASS。

### 渲染精度说明（回答“审阅级 vs 精确级”）

- 之前的“审阅级”指：覆铜只画 `POUR` 边框（无 clearance/热焊盘）、焊盘只取
  `defaultPad`、不挖孔、不处理 ARC/POLYGON、不做布尔并集、内层不画 THT
  焊盘——形状是示意，不是铜。
- 现在 `--exact` 已把这些换成记录/缓存级几何：形状与挖孔来自
  `POURED`/焊盘/孔记录，面积可计算；剩下的不确定性是**缓存新鲜度**
  （无法替代官方铺铜引擎）与 ARC 离散化，而不是“截图级近似”。

### DFM 批处理检查（第一版，pcb_workbench dfm）

- 现状澄清：此前**没有**铜皮最窄处/间距/环宽批处理；只有原理图电气规则
  （lceda_rules）、PCB 候选几何、Gerber/钻孔对拍。本次新增 `dfm` 子命令。
- 检查项：
  - `track`：走线宽度（记录值，精确）；
  - `neck`：覆铜窄颈/热焊盘辐条/孤立窄铜（矢量腐蚀拓扑，最小宽度估计）；
  - `clearance`：同层不同命名网络间距（Shapely 距离；铺铜缓存落后时只用
    走线/焊盘/过孔，避免缓存造成的假重叠，并标注口径）；
  - `annular`：过孔/THT(ROUND) 环宽（记录值；跳过 NPTH/无网络机械孔）。
- 实测（PCB1，默认阈值 0.20/0.20/0.15/0.10 mm）：track=6（0.15mm
  TIM3/DAC3 等）、neck=6（0.0987–0.1513mm，含缓存快照）、clearance=0
  （命名网络，仅走线/焊盘/过孔口径）、annular=6（0.0975mm 略低于 0.10）。
- 边界：无阻焊/孔到铜/孔间距/板边间距；neck 为腐蚀拓扑近似（平滑渐变
  颈缩可能低估）；clearance 不含无网络铜；受 POURED 缓存新鲜度影响；
  不是制造签核。
- 回归：新增 `probes/verify_pcb_dfm.py`（松/严阈值、空网络过滤、缓存字段），
  全 PASS。

### PDN 2.5D FDM + 热力图（pcb_workbench pdn）

- **落地目标**：不是只写 runbook，而是从 `.epcb2` 实铜几何直接算电压、
  电流密度、功率和温度，并输出可看的 PNG 热力图。
- **模型**：每层铜栅格化成 4 邻域电阻网格（`G=σ·t`）；过孔按镀铜桶电阻
  连接相邻层；源焊盘 Dirichlet 电压、汇焊盘注入总电流；稀疏 `A·V=b`。
  只保留源/汇所在连通铜分量，孤立岛丢弃并计数，避免奇异矩阵。
- **热**：铜/FR4 等效面导热 + 上下表面对流；导热计入全板铜（不只选中
  网络），热源只计选中网络的 `I²R`（含过孔）；简化为 2D，不含 TIM/风道/
  辐射/3D 过孔。
- **输出**：逐层 `voltage/current`、`voltage_all`、`current_all`、`thermal`、
  `summary.json`；深灰为其他网络铜上下文，`SRC`/`SINK` 标焊盘中心；
  电流色标默认 99.5% 分位裁剪（标题保留真实最大值）。
- **校验**：单层直导线 FDM 与 `R=ρL/(wt)` 误差 **0.5%**。Fresnel：
  - `TEC_NEG`（U602.2→U900.14，0.5A，0.05mm）：IR drop 27.35mV，
    R=54.7mΩ，P=13.7mW，2D 热最高 25.88°C；0.1mm 网格 IR drop 25.35mV
    （约 8% 网格差）。
  - `+3V5_TEC`（L214.2→L602.2，0.5A，0.05mm）：IR drop 16.16mV，
    R=32.3mΩ，P=8.1mW；电流主要走 Inner2，Top 层只有局部连接，
    因此 `voltage_all` 才是完整路径视图。
- **边界**：薄铜片 FDM + 过孔桶电阻；无焊锡/连接器接触电阻/3D 铜厚；
  热为简化 2D；`POURED` 缓存可能落后（本板 214379 < 216391）；最大
  电流密度对网格敏感，只用于 hotspot 定位。**设计预检，不是制造/热签核**。
- **回归**：新增 `probes/verify_pdn_solver.py`（解析直导线 + 实板
  TEC_NEG smoke），PASS；示例 spec 在 `pcb_workbench/specs/`。

### 封装热模型 + 旧 2D 热图撤下（pcb_workbench thermal）

- **撤下旧热图**：`pdn_*_thermal.png` 是 2D 等效铜损温升，不是器件
  结温/整板温度；已从公开结果删除，`pdn` 只保留电压/电流密度。
- **实际叠层**：`v4.py` 新增 `LAYER_PHYS` 解析与 `PCBDesign.stackup()`；
  本板实测 7 层、总 **1.586 mm**：Top 1.378 mil / 7628 8.283 /
  Inner1 0.598 / 1.1 mm core / Inner2 0.598 / 7628 / Bottom 1.378。
- **新 `thermal` 子命令**：3D 分层有限体积板模型（每层独立横向导热、
  层间垂向导热、过孔铜柱、上下对流/辐射/板边）+ 器件封装紧凑热网络
  （`three_node`: θjb/θjc/θca；`two_node`: θjb/θja）。
- **严格门禁**：缺 `LAYER_PHYS`/`BOARD_OUTLINE`、环境/对流、器件
  `power_w`、`source`、`data_quality`、或 θ 参数时**拒绝运行，不出图**。
  模板 `specs/thermal_fresnel.template.json` 保留已确认的 θJC/DCR，
  其余留空；本板器件功耗/封装热阻/U900 模块热路径未齐，因此**没有
  Fresnel 器件温度结论**。
- **验证**：`probes/verify_thermal_model.py` 验证实际 7 层/4 铜叠层、
  模板被拒绝、合成 U601 网络能量平衡（qin=qout、Tj>Tc>Tboard>Tamb）；
  `verify_pcb_workbench` / `verify_pdn_solver` 保持 PASS。
- **边界**：封装是紧凑热阻，不是封装内部 3D 场；没有 TIM/焊锡/连接器/
  风道；板边/铜面积分数是网格近似；不能替代实测或签核。

## 2026-10-16

### 合并 PR #2：V3 解析修复（Floyd-Fish）→ 合并提交 de1fe98

- 合入两处修复（`08f8068`）：
  1. **孤儿 LINE 过滤**：删除导线/总线时导出包不再保留 WIRE/BUS 记录，
     但 append-only 的 .epru 仍留有 LINE（lineGroup=已删对象 id）；按
     lineGroup 无条件聚合会把这些几何复活成"幽灵导线"并凭空造出短路。
     现只接受被 WIRE/BUS 声明过的组（BUS 一并计入；仅当该文档确实使用
     WIRE/BUS 声明机制时才过滤，避免误伤 PCB 文档）。
  2. **NetPort 端口名认 `Name` 属性**（此前只认 `Global Net Name`）：
     仅对 symbol_type 18/19 实例生效；其 stub 线无 NET 时端口名不再丢失，
     跨页同名归并恢复。
- **冲突解决**：原 PR 的 `_cbb_dom` None 守卫与远端 2026-10-01 实现重叠，
  保留远端更完善版（`_record_cbb_issue` + 一次性告警），不重复实现。
- **合并前复核**（本机全量，2026-10-05；合并树 de1fe98 与复核分支逐字节
  一致）：
  - 四套回归 PASS：smoke2 / verify_all_formats / verify_bus /
    cross_backend_contract（合并后在 main 复跑仍全 PASS）；
  - 本机 55 个工程文件 netlist 双比对：48 个逐字节一致、5 个变化（均
    Piezo 家族、均含孤儿几何）、**0 个网络删除、0 个新增失败**；
  - 变化逐项与同工程 `.epro` 对拍（EproDB 不受本 PR 影响，作地面真值）：
    VCC/VEE 网络名恢复（0→40 成员）、FBADC_SPI_* 跨页归并修正
    （U3/SHORT/PORT 并入基础网络）、GND/VCC_3V3 成员补齐（C281/R242、
    去耦电容与 CBB 成员）、压电电源工程 CU_12V_RC 与 PGND0 的幽灵短接
    被正确拆开（10 个去耦电容回到各自真实网络）。
- **远端复查**（2026-10-16）：reader/ops 均无新提交、无新 PR、无 issue；
  原生 `.eprj3` 仍未支持（README 与测试明确标注，本次未涉及）。

## 2026-10-03

- 新增独立、显式 opt-in 的 EPRO2/EPRU PCB 候选几何入口，不改旧 SCH API
- 自动检测两套日志重放结果是否一致，保留删除/恢复/冲突/来源；多 PCB 不猜选
- 动态铜层、毫米制几何、底面/焊盘/过孔/NPTH/约束、可空的声明物理堆叠
- 只接受活动 owner 的覆铜缓存，缺失/显式过旧/未知变体失败，绝不拿 POUR 边界补铜
- 显式修复才允许无效多边形，并记录每项修复，保持候选与不完整状态
- 补上圆形 MULTI FILL 非金属化材料去除及铜圆 FILL 的线宽制造语义
- 独立 Gerber/Excellon 比较器、JSON Schema、纯合成回归和 Python 3.10/3.12 CI
- 原工程及真实制造文件始终在仓库外；公开报告不得含私有网络/设计标识

验证数量及仍未覆盖的路径以最终 PR 检查记录为准。新原生 UI 导出如遇权限/
环境阻断不得说成完成；旧制造证据、离线提取、合成测试要分别说明。

### Gerber 区域解码补充

- 可选制造比较器显式解码满足精确条件的全直线 cut-in，记录独立的
  `contour_decodings`，避免把合法带孔轮廓一概计为修复
- 拒绝未闭合、嵌套和未结束区域，防止下层解析器补线或丢弃几何
- 新增合成正反例；保留 candidate / partial / manufacturing_verified 的原边界
- 范围和格式依据见 [Gerber 区域轮廓边界](docs/Gerber区域轮廓边界-2026-10-03.md)

### 原理图镜像旋转顺序修复

- 引脚实例变换改为先旋转、再水平镜像、最后平移；修复镜像90°/270°时的
  空网或错误位置匹配，主坐标和V3第二候选保持同一处理
- 新增三种工程格式、八种直角/镜像组合、第二候选与错误位置诱饵的合成回归
- 不改原始坐标归一化、网络匹配容差、渲染符号覆盖或PCB几何
- 依据和限制见 [原理图镜像与旋转的组合顺序](docs/原理图镜像旋转顺序-2026-10-03.md)

## 2026-10-01

### 合入前复核补充（2026-10-03）

- 文档索引先解析 JSON header，再按 type 处理 DOCHEAD/META/DELETE_DOC。
  移除固定前缀长度扫描，避免 ticket/id 在前或空白/转义键导致漏掉删除状态。
- 新增键顺序、空白及 JSON 转义的纯合成回归，不改变既有段序/ticket 判优。

### 可移植旧格式回归与 CBB INSTANCE 引用完整性

- 新增 `probes/test_reader_portable.py`，用纯虚构字段、坐标和连接生成
  SQLite `.eprj2`、V2 `.epro`、V3 `.epro2`，检查内容识别、元件/引脚
  连通性、CLI 缺页退出码及输入文件读取前后哈希；不依赖仓库外工程。
- 新增 CBB 失效 INSTANCE 最小回归：目标缺失但原生映射有效、目标缺失且
  无有效替代、有效 INSTANCE 的优先级与位号覆盖、直接读取缺失模板。
- 修复失效 INSTANCE 目标导致 `netlist`/`review` 等路径把 None 传给
  `_collect_pinmap_data` 而崩溃的问题。失效引用和未使用的成员位号覆盖
  显式告警，后续仅使用既有映射规则；无有效模板时不虚构内部连接。
- 未改变旧格式的日志合并、坐标转换或有效 INSTANCE 覆盖优先级；不包含
  原生 `.eprj3` 支持。读取 epro2 不等于通过 V4 原生工程兼容验收。
- 测试命令：`python -m unittest discover -s probes -p test_reader_portable.py -v`。
  原 `smoke2.py` / `verify_all_formats.py` 仍需要各自的外部工程样本，
  可移植回归不能替代这些真实工程检查；缺样本不能报告为通过。
- 新增向后兼容的 `--json-report`：查询数据与 CBB 覆盖诊断分开输出，
  失效 INSTANCE 即使找到其它原生模板，也明确 `complete:false`。
  `complete` 范围限定为本查询已观察的错误/CBB 引用覆盖，不是全工程或电气
  验证。`--strict` 在正常查询存在覆盖缺口时退出 3；默认 `--json` 不变。

私有工程及诊断输出不入库；可复现回归只使用上述合成样例。

### 缺失引脚编号的文本输出

- 修复 `pinmap` 文本模式对未标注 Pin Number 的引脚格式化 None 而崩溃。
  显示 `?` 明确表示编号未知；JSON 仍保留 `null`，不猜引脚号。
- 补充合成回归，同时检查文本可显示及 JSON 未改变未知值语义。

### V3 引脚属性的顺序无关关联

- 修复 `Epro2DB.symbol_pins` 在 ATTR 先于 PIN 出现时丢失引脚名称、编号、
  类型的问题。增量日志中更新后的 PIN 胜出位置可能在原 ATTR 后面；
  现在独立收集属性后按 parentId 关联，不更改日志胜出规则或坐标转换。
- 添加两种虚构日志回归：直接 ATTR→PIN，以及 PIN→ATTR→更新后的 PIN。
  检查真实属性保留、更新后的几何胜出，不用猜测编号填补解析丢失。
- 显式 `Pin Number:null` 保持未知值，不再经 str(None) 变成伪编号字符串。
  无编号 CBB 端口仍按名称识别，JSON 输出 null，文本显示 `?`。

### V3 文档删除与恢复

- 处理规范定义的 `DELETE_DOC` 显式布尔状态：活动索引排除最终删除的文档，
  `isDelete:false` 可恢复原有内容；原始日志保持不变。
- 判优沿用后端既有 `(段序,ticket)`，不借此改变旧 V3 增量语义。
  增加同段 ticket 乱序、跨段恢复/删除及已删除页不参与查询的合成测试。

### 同页显式网络别名闭包

- 当有效短接产生 A/B 别名后，同页远处单独绘制的 A 网络也应获得 B。
  在已有物理域的显式名称集合上做传递闭包，保留原线名和物理域 ID。
- `pinmap` 的 `resolved_nets` 单独给出解析别名；原 `net/nets` 字段含义
  不变，`--no-domain` 不产生该派生字段。没有推断协议或跨页/跨板连接。
- 合成回归覆盖 A/B/C 传递，以及有源件、NC、DNP、不同行页隔离负例。

## 2026-09-30

### 修复：三个阻断/污染 netlist 的解析层缺陷（来源工程 Fresnel_V2.1_LaserDriver_EVM.epro2）

用户工程实测暴露，均已修根因并加回归 `probes/regress_fresnel_v21.py`（ALL PASS）。

#### 0. 概览：三个缺陷的关系

前两个是**硬故障**（命令直接崩 / 网络名丢失），第三个是**软故障**——命令能跑完，
但结果里混进了 EDA 中并不存在的几何，**凭空造出短路**。第三个尤其危险：它不会报错，
只会给出一个看起来很像真的错误结论（本次实际导致把 MCU 的 I2C2_SDA/SCL、
SPI1_MISO/MOSI 误判为"被短接"）。

#### 1. `_cbb_dom`：模板页解析失败时崩溃（`TypeError: 'NoneType' object is not subscriptable`）

- **现象**：`netlist` 直接抛异常退出，`trace`/`find` 同样受影响（共用
  `resolve_nets_by_domain` → `_expand_cbb` → `_cbb_dom`）。
- **根因**：`.epro2` 的 INSTANCE 文档保留**已删除 CBB 实例**的映射。本工程
  TEC Controller 页（uuid `73ea7bd65aa016ad`）残留 cid `3851a5f68fce21f1`
  → `src = b1958471d75069f5`，该 uuid 在本工程里只剩
  `IMAGE/b1958471d75069f5.webp`，**没有对应原理图页**。`_cbb_dom` 里
  `t_sheet = parse_sheet(...)` 返回 None 后直接传给 `_collect_pinmap_data`，
  后者第一句就是 `for n in sheet["nets"]`。
- **修复**：`_cbb_dom` 在调用 `_collect_pinmap_data` **之前**判 None，
  记一次性告警（`_WARN_ONCE`）并缓存空域——与既有 `t_pinc is None` 分支同语义，
  不是兜底掩盖：模板页确实不存在，展开本就不可能。
- **同类风险**：`cbb_instances()` 里还有 6 条 `src` 指向 `6b548a5703589e65`
  / `0cc43f977cf25370` / `ee248e296c52039d` / `b1958471d75069f5` 等无效 uuid
  的残留映射；只要母图上对应实例被删掉就不会被走到，故只在告警路径暴露。

#### 2. `port_nets`：`Name` 型 NetPort 端口名被丢弃，网络退回立创自动名

- **现象**：MCU 页 5 个网络的**功能名**在 netlist/pinmap 里消失，变成
  `PA8`/`PA9`/`PA10`/`PD2`/`PB3`（立创按连接引脚自动生成的名字），
  跨页同名归并随之失效。
- **根因**：端口名有两个存放位。`Global Net Name`（NetFlag/电源符号，
  Symbol `f2ed2056778822ba`/`4a0c5c88c3f967d1`，pin 名 `Pin1`）已被识别；
  但 **NetPort 符号**（Symbol `a029f22680921aa0`/`ed17ac3692b0f0b6`，
  pin 名 `BI`）把端口名写在 **`Name`** 属性里，而它的 stub 线**没有 NET 属性**，
  于是 `_collect_pinmap_data` 的 `port_nets` 拿不到名字。
- **影响范围**（本工程实测）：
  - `I2C2_SDA` / `I2C2_SCL` → 退化成 `PA8` / `PA9`
  - `EEPROM_WP` → `PA10`；`ADC_CS` → `PD2`；`ADC_SYNC` → `PB3`
  - 连带 `ADC_CS`/`ADC_SYNC`/`SPI3_SCLK`/`SPI3_MISO`/`SPI3_MOSI` 的
    **MCU ↔ TEC Controller 跨页归并全部失效**（AD7175-2 24bit ADC 总线）
- **修复**：`port_nets` 改为遍历 `port_cids`，取
  `net_of(cid) or sheet.components[cid].attrs["Name"]`。
  `Global Net Name` 优先级不变；只有 18/19 类端口实例参与，普通器件不受影响。
- **注意**：`parse_sheet` 早就用 `a.get("Name")` 给**元件自身**的 `net` 兜底，
  这次只是把同一事实补进 `port_nets`（连通域命名路径），两条路径口径统一。

#### 3. 已删除导线的孤儿 `LINE` 被复活成"幽灵导线"（凭空造出短路）

- **现象**：命令正常跑完，但连通域里出现 **EDA 中并不存在**的导线。
  本工程 MCU 页表现为 `PA8↔PA9`（即 `I2C2_SDA` 与 `I2C2_SCL` 合并）与
  `PA6↔PA7`（`SPI1_MISO` 与 `SPI1_MOSI` 合并）——按此结论会判成"设计错误、
  I2C 与 SPI1 全废"，而**用户确认并未短接**，官方导出 PDF 里也没有这两段线。
- **根因**：`_iter_doc_lines` 已处理**墓碑**编码（最新记录 body 为空 `|||`），
  但 LCEDA 删除导线还有**第二种编码**：导出包里该对象的 `WIRE` 记录
  **整体消失**（连墓碑都不留），而 append-only 的 `.epru` 仍保留它的
  `LINE` 记录（`lineGroup` = 已删对象 id）。`Epro2DB.sheet_records` 按
  `lineGroup` 无条件 `setdefault` 聚合，于是孤儿几何被重新组装成导线。
- **规模**（`probes/scan_epro2_orphans.py`，本机 74 个 `.epro2`）：
  30792 个 `WIRE` id / 36971 个 `lineGroup`，其中 **6179 个（16.7%）是孤儿**，
  共 11999 段几何。分布极不均匀：V4.0/V4.1 单通道扫描台、电容前置放大器等
  早期导出为 0，反复删改的 MMC-110 高达 323 个。
- **修复**：在 `_iter_doc_lines`（与墓碑过滤同层，**不是**在 `sheet_records`）
  先收集"声明集" = 本文件所有 `WIRE`/`BUS` 记录的 id，`LINE` 只允许并入
  被声明过的组；`BUS` 一并计入（总线图形 LINE 的 `lineGroup` 就是 `bus_id`，
  删总线时同样丢 `BUS` 记录）。孤儿数 >0 时按文档打一次性提示。
  - 放在 `_iter_doc_lines` 而非 `sheet_records`：该函数是**所有** V3 消费点的
    上游（SCH 与 PCB 两条路径都走它），修在这里才不会漏掉 PCB 侧。
  - 护栏 `if declared`：仅当该文档确实使用 WIRE/BUS 声明机制时才过滤，
    避免误伤本就不写 `WIRE` 记录的 PCB 文档。
- **影响面（跨工程回归，旧版 = git HEAD vs 新版）**：

  | 工程 | 网络数 | 仅旧有 | 仅新有 | 成员变化 |
  | --- | --- | --- | --- | --- |
  | Fresnel_V2.1_LaserDriver_EVM | 94 → 94 | 0 | 0 | 6（I2C2_SDA/SCL、PA8/PA9、CURR_OUTPUT、DAC_VREF_5V） |
  | MMC-110-MultiFields | 123 → 123 | 0 | 0 | 4（+3V3D、GND、PE10、PE11） |
  | 单通道扫描台从机_REV4.2 | 365 → 365 | 0 | 0 | 0 |
  | V4.1 单通道扫描台从机 | 407 → 407 | 0 | 0 | 0 |
  | MMC-100 | 114 → 114 | 0 | 0 | 2（+3V3D、GND） |

  **没有任何工程增删网络**——该修复只拆掉假归并，不会破坏真实连通性。
  MMC-110 的 `PE10`/`PE11` 原本被幽灵线并进 `+3V3D`/`GND`，属同一类
  "幽灵线短路电源"的错误，修复后消失。
- **几何级验收**：修复后本工程 MCU 页导线段与官方导出 PDF 的绿色线段
  **逐段一致（343 段 vs 343 段，零差异）**；修复前多出 17 段，全部落在
  孤儿组集合内。

### 回归

```bat
set PYTHONIOENCODING=utf-8
python probes\regress_fresnel_v21.py
python probes\scan_epro2_orphans.py <工程.epro2>
```

`regress_fresnel_v21.py` 覆盖：全页解析不崩溃、残留模板页一次性告警、
5 个功能网络名存在、5 条 MCU↔TEC 跨页归并、5 个自动名网络仍各自独立
（防止修过头把自动名吞掉）、**PA8/PA9 与 PA6/PA7 各自独立成域**、
**有意短接 PB4↔SPI3_MISO 仍合并**（反向断言）、MCU 页孤儿几何组为 0。

仓库自带的 `probes/smoke2.py` 依赖作者本机样例工程（`examples\涡流传感器.eprj2` 等），
克隆环境无该目录，**本次未能执行**；上面两个脚本即为此工程的可移植替代，
路径可用 `LCEDA_FRESNEL` 环境变量覆盖。

## 2026-09-08

回归脚本改吃仓库自带 `examples/`（无外部绝对路径，换机可用）。解析层零改动。

### 一、回归脚本 examples 化

#### 背景

`probes/smoke2.py` 与 `probes/verify_all_formats.py` 硬编码本机外部绝对路径
（`D:\WorkDesigns\2_WorkProjects\E_distance\…`、`C:\Users\dell\Documents\…`、
`C:\Users\dell\Downloads\…`），换机即废；`examples/` 下 6 个样本无人消费。

#### 实证（改前基线）

- `examples/涡流传感器.eprj2` 与外部同名文件 SHA256 一致
 （`85779CB5…9A786D`）；`examples/MCU主控…eprj2` 与外部文件 SHA256 一致
  （`F19F357F…4389434E`）。
- 9 项 smoke 查询（bom/netlist/find/pins/datasheets/components/search/nets）
  外部 vs examples 输出逐字节相同（行数 925/1669/30/197/506/4454/4/10/6）。

#### 变更

- `probes/smoke2.py`：默认工程改为 `../examples/涡流传感器.eprj2`
  （相对脚本路径解析，不依赖 cwd）；`LCEDA_EPRJ` 环境变量可覆盖；
  工程缺失时明确报错退出 1；测试项与覆盖不变；`sys.exit` 透出 PASS/FAIL。
- `probes/verify_all_formats.py`：FILES 改为 examples 下 6 文件（全部期望 ok）；
  网络集合拆分同时按 `NET_SEP(U+241F)` 与逗号切分（此前仅逗号会把 CBB 别名串
  误当单网名）；交叉对比改为 Piezo 同工程三格式（元件数必须一致才 PASS，
  板/页/网差异仅 WARN）；新增 Piezo `.epro` CBB 展开实例数回归项（应 15）。

#### 验证结论

- `smoke2.py`：ALL PASS（9 项，行数与改前基线一致）。
- `verify_all_formats.py`：ALL PASS。涡流 6板17页736元件79网、MCU 1板3页
  288元件87网（与 README 声称一致）；Piezo 三格式元件数一致 3575；
  CBB 展开 15 实例/454 引用；R235 DNP 两脚异网（人工核对，见下）。
- 已知 WARN（非 FAIL，待查）：epro2 页 75 vs epro/eprj2 页 73
 （多 2 孤儿旧 CBB 页，`list` 显示 `sch=?`）；板数 11 vs 16；
 网络集合三方共同 263、两两共同 265/265/263（有 4 网仅两方共有）。

### 二、退出码/解密残留（同日第二批）

- 未找到页统一 `sys.exit(2)`：此前 `cmd_pinmap/texts/nets/pins/attrs/raw`
  仅打印后 `return`（rc=0，脚本误判成功），`render` 用 exit(1)。
  现 16 处全部 exit(2)；1 保留给格式/用法错误。约定记此，不碰 README
  （他人有未提交修改，避免交织）。
- 解密残留清理：`_decrypt_new_eprj2` 的 `mkdtemp` 目录进程退出时
  `atexit.register(shutil.rmtree, ignore_errors=True)` 删除（Epro2DB 在进程内
  读 zip，退出时删安全）。实测 Piezo 解密后路径已不存在。
- ops（独立仓库，见其提交）：`list_targets` 连接失败转 `CdpError` 中文指引；
  `main` 顶层捕获 `CdpError` 打印后 exit 1，终结 raw traceback。

#### 验证结论

- `smoke2.py`：ALL PASS。
- LcedaDB 基线逐字节一致：netlist/pins/nets（涡流）+ pinmap R235（Piezo .epro）。
- `verify_all_formats.py`：ALL PASS（CBB 15/454；WARN 同上节）。
- ops：`status` 无客户端时一行中文错误 + rc=1（活客户端回归因无运行实例未做）。

### 三、输出契约：eprj 统一 int + --json 歧义页 exit 2（同日第三批）

- `eprj` 统一 int：多工程 `--json netfind` 数据行曾用 `"eprj": "#0"` 字符串，
  与顶层 `projects` 信封（int）及 `find/trace`（int）不一致，脚本按 int
  join 会断。现两处 `f"#{di}"` 改为 `di`；文本模式 `[工程#0 …]` 顺带变为
  `[工程0 …]`，与 `工程0 = 路径` 映射行一致。
- `--json` 歧义页 exit 2：`resolve_page` 新增 `strict` 参数，7 个命令调用点
  传 `args.json`。文本模式保持“警告 + 取第一个”；`--json` 下重名且无
  `--schematic` 时报错列候选并 exit 2（JSON 消费者看不到 stderr 告警，
  不可静默取第一个）。CBB 内部调用保持非严格。`components` 为全页遍历，
  本无歧义问题，不动。
- 同类遗留（未动）：`未找到网络` 仍 bare return（rc=0），与本次“2=查询无命中”
  约定同类，待定。

#### 验证结论

- 基线：改前已存多工程 netfind/find（JSON+文本）与歧义页（JSON+文本+stderr）。
- `find` 输出逐字节一致（本来就是 int）；文本歧义页输出一致；
  netfind JSON 差异仅 `eprj` 类型（行内无 `"#` 残留）；文本 tag 为 `工程N`。
- `smoke2.py` + `verify_all_formats.py`：ALL PASS。
- 行为抽查：`--json pins 对外连接` → 报错 + rc=2 且无 JSON 输出；
  `--json pins 对外连接 --schematic schematic2` → 正常；
  文本 `pins 对外连接` → 警告 + 取第一个 + rc=0（保持）。

### 四、查无类统一 exit 2（同日第四批）

- 根因：`main()` 不看返回值，各命令“查无”路径顺手写 `return`（rc=0），
  只有未找到页用 exit。真机核对：`netfind GNDD`（手误）rc=0 且 `--json`
  下还是纯文本；`link-check` 在不相关工程对上都有输出（含 0/4 候选），
  故其空分支是近死代码（退化输入），归 2 合理；另观察到 0 一致候选也列出，
  噪声问题另议（可加一致率阈值，本次不动）。
- 改动（5 处 `return`→`sys.exit(2)`，输出文字不变）：
  trace 单/多工程起点位号不存在、find 查无位号、netfind 查无网络、
  link-check 无候选。合法空结果（无文本注释、无 Datasheet）保持 rc=0，
  判据：消息说“未找到”→ 2，报合法空状态 → 0。

#### 验证结论

- 5 条错误路径输出与改前逐字节一致（仅退出码 0→2）；link-check 空分支
  真机无法触发（近死代码），仅代码审查确认。
- `smoke2.py` + `verify_all_formats.py`：ALL PASS。

### 五、第六项开工：重复 hierarchy 定义（同日第五批）

- 基类 `SchemaBackend` 内两个 `@abstractmethod hierarchy`（均为无实现桩，
  第二个静默覆盖第一个），删第二个，保留文档更全的第一个。
  现状：基类 1 个抽象 + 3 个子类实现。
- ops（独立仓库，见其提交）：`sch-replace` 先删后搜库 → 改为先搜库
  （无结果/`--pick` 越界直接退出，不删原器件）再删后放；
  `place` 返回 None 的残留风险仍在（需活客户端回归确认），下次补。

#### 验证结论

- `tree` 输出正常；`smoke2.py` + `verify_all_formats.py`：ALL PASS。
- ops：语法通过；R1 新顺序仅代码审查确认（活客户端回归待运行实例）。

### 六、C项：V3 引脚 tip 方向纠正（同日第六批）

- 实证（Piezo_Driver.eprj2，探针见本次 probes/tmp，已清理）：
  双候选引脚 7271 个，root/tip 异网冲突 4907 个，其中 4900 个是
  “root 命中命名网络、tip 落空”，反向仅 7 个。
  几何根因：V3 PIN 记录坐标是引脚**外端点**（导线端点与 PIN 重合，
  如 U1.GND1 root=(280,790) 正中 GND 导线端点；体 bbox 边内 10=1×len），
  tip 公式实为体侧 joint 候选；且竖直引脚用了 `-sin`，77 个竖直引脚
  joint 上边仅 1 个，改 `+sin`（与渲染引脚桩同约定）后 47 上边。
  子代理“旋转/镜像顺序相反”的说法被证伪：90° 倍数下 pinmap 与渲染
  双公式在两工程 12933 个测试向量上零分歧；非 90° 旋转器件数为 0，
  系潜在问题，保持告警即可。
- 改动：`tip_loc` 的 `-sin`→`+sin` + 注释更新语义（PIN=外端点，
  tip=体侧 joint 候选）。水平引脚 sin=0 不受影响。

#### 验证结论

- PowerBoard::P1 的 pinmap  diff 仅 1 行：C64.1 与 PORTe1247.Pin1 的关系
  由“同点 `<-`”变为“同导线 `[wire:]`”——旧 `-sin` tip 恰好落在 C64 根点上
  造成的伪同点，新结果几何真实；网络与 peers 不变。
- `nets`/`netlist`（Piezo 全工程）逐字节一致；`smoke2.py` +
  `verify_all_formats.py`：ALL PASS。

### 七、A项第一批：高危吞错加告警（同日第七批）

- 范围：40 个 except 块全审计。合法保留：`search` 正则错、`main` 打开失败、
  渲染单字段回退（尽力而为输出）、配置缺失降级。
- 改动（只加 stderr 一次性告警，行为不变）：decompress base64 失败、
  device_map 失败（0Ω桥接降级）、polar Datasheet 清单失败、
  polar 单页连通域失败（带页名）、pcbsch hierarchy 失败。
  沿用 `_WARN_ONCE` 惯用法，不新增基础设施。
- 待下一批：NDJSON 坏行计数（6 处 sheet/symbol 解析循环）、CBB 映射跳过、
  NET/PAD_NET 解析失败、decrypt 缺段跳过。

#### 验证结论

- 干净工程（涡流 polar + 双套件）无新增告警，ALL PASS。
- 负向触发：坏 base64 输入告警一次、返回空串（与旧行为一致）。

### 八、A项第二批：坏行计数告警（同日第八批）

- 先核对：6 处 NDJSON 循环形状一致；真机 61735 行中坏行 0、空行 1——
  计数器必须跳过空行，否则误报。V3 NET 丢记录 / PAD_NET 降级保留的不对称、
  CBB 同目录扫描静默跳过、decrypt 空 blob/缺密钥跳过，逐处确认。
- 改动（行为不变，只加告警）：新增 `_warn_bad_rows(tag, ident, n)`；
  6 处循环空行跳过 + 非空坏行计数（按页/符号 warn-once）；
  V3 NET/PAD_NET id 解析失败告警（NET 丢记录、PAD_NET 降级）；
  CBB 扫描单文件跳过（带文件名）+ 目录失败；
  decrypt 空 blob/缺密钥改计数汇总一次（防刷屏）。
- render 图元级跳过（3 处）保留：渲染是尽力而为输出且已有 `无图形退化`
  汇总计数，单元件噪声不值得加。

#### 验证结论

- `_warn_bad_rows` 单元：n=0 无声、n=2 报一次。
- 干净工程（Piezo 解密无跳过、涡流 netlist）无新增告警；
  `smoke2.py` + `verify_all_formats.py`：ALL PASS。

### 九、F项：NC 变体值兜底 + 未贴装语义（同日第九批）

- **核实**（六工程探针）：0Ω/SHORT 全为 2 脚、两脚都命中导线 234/234、
  单脚命中被跳过 = 0；器件级 DNP（attrs 表）24 个全为 MARK 机械件，
  不含 0Ω/SHORT。故原 F 描述的“窄条件漏判”实测零影响。
- **语义澄清**（用户确认）：`Add into BOM=no`（不上件）与
  `Convert to PCB=no`（PCB 无封装）都表示物理不存在，都判 DNP；
  手焊等后续流程不在本工具范围。不区分两类标志。
- **改动**：新增 `_is_nc_marked()`（独立 NC token：`NC_`/`_NC`/`NC_10pF`/
  `0Ω_NC_2`，分隔符界定，不误伤 `NCU1`/`RNC`）与 `_is_unpopulated()`
  （DNP 标志 ∨ NC 变体值）。parse_sheet 记 `nc_marked`；**NC 变体但无
  DNP 标志**时 stderr 告警（带位号/值）并仍按不上件处理——防 0Ω 漏设
  DNP 时被误当物理直连合并两侧网络。桥接/`pinmap.dnp`/两脚桥表统一
  改用 `_is_unpopulated`。
- **顺带修 bug**：`collect_two_pin_bridges` 原用循环泄漏变量 `c`
  （末次循环残留），改用 `comp` 局部变量。
- 真阳性样例：Piezo C6 值 `NC_10pF` 无 DNP 标志 → 告警并排除（设计者
  用 NC 前缀标注不贴的 10pF）。

#### 验证结论

- 单元：`_is_nc_marked` 15 例正反全对；`_is_unpopulated` 组合正确。
- 基线逐字节一致（涡流 netlist/pins、Piezo R235 pinmap）；
  `smoke2.py` + `verify_all_formats.py`：ALL PASS。

### 十、D项：删除 T 型落线段（死分支）（同日第十批）

- **核实**：`sheet["nets"]` 的 points 是 WIRE 折线**所有顶点**（一根 WIRE
  可含多段，如 e645 共 9 段 10 点），非"导线末端"、非网格点。
  引脚命中点度分布：38 个度=1（自由端）+ 1 个度=2（拐点），**全为顶点**。
  EDA 连线时在连接处把导线断成顶点，不会让引脚落在段中段。
- **死分支**：`on_segment` 的 `abs(cross) <= 0.75`（T 型落线）在
  涡流/Piezo.eprj2/Piezo.epro 命中 **0 次**；跨 WIRE T 型连接亦 0。
  且 `0.75` 是叉积（面积量纲），换算垂距随段长漂移（段长 25→0.03、
  160→0.0047），语义不固定。按"不写无依据兜底"原则删除。
- **改动**：删 `seglist` 构建、`on_segment`、引脚/tip 的 T 型分支；
  注释改为"精确顶点匹配（实测 100% 为折线顶点）"。逻辑等价（该分支
  从未触发），代码更诚实。

#### 验证结论

- 全 6 工程 `--json netlist`+`pins` 输出与改前**逐字节一致**。
- `smoke2.py` + `verify_all_formats.py`：ALL PASS。

### 十一、H项：多段总线 order 实证 + 取整统一（同日第十一批）

- **样本缺口**：全机器 41 工程仅 1 个单段总线样本（`B[0:3]`），多段为 0。
- **自建样本**：CDP（官方 API `sch_PrimitiveBus.create` + UI 画线触发
  引擎命名）建多段总线 `A[2:3]B[7:6]` + 4 分支，实测引擎自动命名：
  order 0→A2B7 / 1→A2B6 / 2→A3B7 / 3→A3B6，与 `expand_bus_net`
  **完全一致**——确认"末段变化最快、各段按书写顺序"。样本存
  `examples/CDP探针-多段总线.eprj2`，回归加入 `probes/verify_bus.py [4]`。
- **修复（潜在 bug）**：`parse_sheet` bus_entries 块原入口点 `round(.,1)`
  而导线端点不 round，坐标含小数时入口命中不到导线端点 → 总线不展开。
  已统一为 round 1 位（与 `norm_pt` 同口径）。

#### 验证结论

- `probes/verify_bus.py`：ALL PASS（含新 [4] 多段样本）。
- `smoke2.py` + `verify_all_formats.py`：ALL PASS。

### 十二、B项 P3：契约文档化 + 跨后端护栏（同日第十二批）

- 仅做 P3（P1 坐标统一 / P2 `_norm_segs` 下沉留待批准）。
- `docs/开发文档.md` 新增 §2.4 后端接口契约表（a[2]/坐标/OffPage/
  symbol_records/CBB 映射/Y 方向六维差异 + 未统一项与计划）。
- `probes/cross_backend_contract.py`：新增跨格式一致性护栏——同设计
  多格式（Piezo epro↔epro2）元件总数一致 + 共同页位号集一致；
  并把"V3 symbol_records 不可用"从 FAIL 降为 INFO（已知待办非违规）。

#### 验证结论

- `cross_backend_contract.py`：ALL PASS（含新跨格式断言；epro↔epro2
  元件 3575=3575、73 共同页位号集零差异）。
- 其余基线（smoke2/verify_all）未受影响（未改解析层）。

### 十三、更正：游离原理图"无法清理"结论证伪（2026-09-12）

- **原结论**（§开发文档"工程结构铁律"）：RPC 建 Schematic 产生游离，
  `delData` 删除不级联，"幽灵原理图堆积无法清理"。
- **证伪**（2026-09-06 ops 侧活客户端实证 + 本次 reader tree 复核）：
  删除通道此前用错。**读通道** `/PrjDB/schematic/getAllKVDatas` 有效，
  **写通道** `/PrjDB/schematic/delData`（及各种参数形态、批量事务包裹、
  `/pro-mgr/project/updateData/*`）确为**空操作**；但
  `/pro-mgr/api/schematic/delete [{docType:2, project_uuid, uuid}]`
  **实测有效**——一个 v3 工程内 6 个游离原理图全部删除成功，
  `getAllKVDatas` 立即反映只剩 Schematic1。图页更新/删除走
  `/pro-mgr/api/document/update|delete`（docType=1）。
- **另一层原因**：即便内存删除成功，**旧格式 .eprj2（V2.2 SQLite，
  documents 表有行）编辑后 save 不落盘**（ops 2026-09-10 独立实证；
  reader tree 复核显示磁盘 structure 不变）。新格式（加密、
  documents 表空）可正常落盘。因此"游离能否真正清除"取决于工程格式。
- **文档修正**：`docs/开发文档.md`「工程结构铁律」段已改为上述两条
  （可清理 + 旧格式不落盘），删除"无法清理"表述。
- **实务建议**：旧格式工程的结构性损坏（悬挂引用 board uuid + 僵尸
  文档）不要就地修，**新建新格式工程重建**（本次已按此产出
  STM32-DAQ-v4）。
- **验证**：`tree` 输出正常；`smoke2.py` + `verify_all_formats.py` +
  `cross_backend_contract.py` 三套 ALL PASS（本次只动文档，解析层零改）。

### 十四、B项 P1：坐标口径统一（2026-09-16）

- **改动**：`LcedaDB.symbol_pins` 补减符号原点 `HEAD.originX/originY`
  （与 EproDB/Epro2DB 口径统一）；契约写入 `SchemaBackend.symbol_records/
  symbol_pins` docstring——**symbol_pins 返回已扣除 origin 的实例相对
  坐标**（连通域用），**symbol_records 保留原始坐标**（渲染器自扣）。
- **依据**：实测 .eprj2 符号均含 origin 字段但值恒为 0（涡流 116/116），
  而 .epro 有非零 origin（如 (-30,30)/(60,80)），不减会偏 30~80 单位。
  本改动对现有 .eprj2 零行为变化、消除潜在错位。
- **验证**：全 6 工程 `--json netlist`+`pins` 与改前**逐字节一致**；
  `smoke2.py` + `verify_all_formats.py` + `verify_bus.py` +
  `cross_backend_contract.py` 四套 ALL PASS。

### 十五、B项 P2：`_norm_segs` 下沉（2026-09-16）

- **改动**：新增 `_canon_segs()`（**后端用**规范化器：嵌套段原样 / .epro
  平铺点链相邻点成段 / 兼容顶层直链；不合格元素计数+告警）；
  `EproDB.sheet_records` 在读取 WIRE 时调用它，输出与 LcedaDB/Epro2DB
  一致的**嵌套段**；共享层 `_norm_segs` 退化为**只解包**（非 4 数元素
  计数+一次性告警），不再含跨格式分支。
- **意义**：消除"格式差异泄漏到共享层"，符合 AGENTS 代码原则 2；
  新消费点可直接消费 segs。
- **验证**：本机**全部 54 个工程文件**（含 5 官方示例、涡流/信号板/MCU/
  Piezo 系列/STM32-DAQ 系列、Downloads）逐文件对比——
  内容摘要（comps/symbol_pins/nets/records/连通域）+ `--json netlist`
  双比对：**PASS 50 / FAIL 0 / SKIP 4**（双方均不可读）；
  `smoke2.py` + `verify_all_formats.py` + `verify_bus.py` +
  `cross_backend_contract.py` 四套 ALL PASS。

## 2026-08-18

本文档完整记录 2026-08-18 对 `lceda_sch_reader` 工具仓库的 7 次变更
（提交 `1aae209` ~ `670fdce`），覆盖：输出来源标识、同名页解析修复、
多工程顶层项目名映射、格式规范支持补强、skill 审查规则、TODO 记录。

### 变更总览

| 提交 | 类别 | 内容 |
| --- | --- | --- |
| `1aae209` | feat | 输出来源报告：list/boards 带工程文件路径；多工程非 json 打印 `工程N=路径` 映射 |
| `fcc5d7c` | fix | 同名页按 document uuid 精确读取（此前 display_title 非唯一导致永远命中第一页） |
| `c8f966a` | feat | 多工程 json 顶层 `{"projects", "rows"}` 项目名/文件映射；修复 find/search 多工程崩溃 |
| `f602522` | docs | 本文档首版（前三次变更详情） |
| `e4de429` | feat | 规范补强：NO_CONNECT(X) 引脚标记 + NetFlag(18)/NetPort(19) 参与 pinmap |
| `7386054` | docs | skill 增加 NO_CONNECT 审查规则（[X] 必须确认是否真的需要 NC）；更新 NetFlag/NetPort 已支持说明 |
| `670fdce` | docs | TODO.md：BUS/BUSENTRY 总线暂不做（等用户提供样例），记录 PCB/变体等其他未支持项 |

---

### 一、输出来源报告（1aae209）

#### 背景

多工程分析时无法从输出分辨数据来自哪个工程文件。

#### 变更

- `list` 输出标题附工程文件路径；
- `boards` 每行前缀 `[文件名]`；
- 多工程（非 json）先打印 `工程N = 完整路径` 映射（`main()` 中实现，
  支持 netfind/link-check/trace/find/search）。

---

### 二、同名页解析修复（fcc5d7c）

> 详见 `docs/同名页解析修复说明.md`（含发现经过、根因、验证与遗留事项）。

#### 背景

对比新旧版工程时，`schematic1` 与 `schematic1_2` 的 `激励输出和AD采集` 页
输出完全相同，一度误判为"重复图"。实为工具 bug：两页为库内独立记录，
但 `sheet_text`/`sheet_records` 按 `display_title` 查询（非唯一），永远命中第一条。

#### 根因

1. `LcedaDB.sheet_text`/`sheet_records`：`WHERE docType=? AND display_title=?`
   → 同名页取第一条；
2. `resolve_page`：返回 title 字符串而非唯一键，`--schematic` 过滤形同虚设；
3. 遍历型命令：`db.sheets()` 已给出 `(uuid, title, sch, dt)`，却用 title 取页。

#### 修复

- **LcedaDB**：`sheet_text`/`sheet_records` uuid 优先、display_title 回退
  （向后兼容旧调用）；
- **EproDB**：`_build_page_index` 增加 `page.uuid -> (sch_uuid, page_id)` 索引；
  新增缺失的 `sheet_text()`；`sheet_records` 复用；
- **resolve_page**：返回 document uuid；匹配兼容 EproDB `板名::页名` 复合标题
  （`title == page_name or title.endswith("::" + page_name)`）；
- **命令层**：pinmap/nets/pins/attrs/raw/boards/components/netlist/find/
  netfind/trace/_trace_multi/_conn_pairs/search/bom 全部改用 uuid 读页；
- `cmd_components --sheet` 过滤兼容复合标题。

#### 验证

- `pinmap 激励输出和AD采集 --schematic schematic1` = 116 元件，
  `--schematic schematic1_2` = 109 元件，内容不同；
- smoke2 全回归 ALL PASS。

---

### 三、多工程顶层项目名映射（c8f966a）

#### 背景

工程文件内 `projects.name` 为立创EDA默认名（`New Project_2026-03-10_09-50-33`，
复制改名后新旧工程相同），无实际意义；可读项目名只能依赖**文件名**。

#### 变更

- 两后端新增 `project_name()`：返回 `Path(path).stem`（文件名去扩展名）；
- 多工程 json 顶层统一结构：

  ```json
  {
    "projects": [
      {"eprj": 0, "project": "涡流传感器-V1.0-2026.04.01",
       "file": "C:/.../涡流传感器-V1.0-2026.04.01.eprj2"},
      {"eprj": 1, "project": "涡流传感器", "file": "C:/.../涡流传感器.eprj2"}
    ],
    "rows": [ ... 命令结果，行内 eprj 字段与 projects 索引对应 ... ]
  }
  ```

  涉及命令：netfind / trace / link-check / find / search；
- **单工程 json 保持原数组结构**（向后兼容，smoke2 及既有消费方不受影响）；
- 非 json 多工程维持 `工程N = 完整路径` 头；
- **顺带修复**：`cmd_find`/`cmd_search` 此前多工程传 dbs 列表直接崩溃
  （`list` 无 `sheets()` 属性），现改为按工程循环并给每条记录加 `eprj` 索引。

#### 验证

- smoke2 全回归 ALL PASS；
- 单工程 find/search/netfind json 均为数组；
- 多工程 5 命令顶层均为 `{"projects", "rows"}`，projects 正确输出项目名与路径。

---

### 四、格式规范支持补强：NO_CONNECT + NetFlag/NetPort（e4de429）

依据 `reference/lceda-pro-file-format-v3_2025.10.21.md` 对照检查，
补两个未支持项（该工程实测：NO_CONNECT 139 处、NetFlag/NetPort 实例 610 处）。

#### NO_CONNECT（X 不连接标记）

- **背景**：`NO_CONNECT` ATTR 挂在 `compId+pinId` 复合编号（如 `e130e198` =
  实例 e130 + 符号内 PIN e198），此前工具忽略——"悬空引脚"审计会把显式
  NO_CONNECT 误报为漏接。
- **修复**：
  - `parse_sheet` 收集 `sheet["no_connect"]` 集合；
  - `_collect_pinmap_data` 用 `compId + pinId` 匹配标记引脚
    （`plist` 项加 `no_connect` 字段）；
  - `resolve_nets_by_domain` 跳过 NO_CONNECT 引脚（防容差 2 兜底误连
    相邻走线）；
  - `pinmap` 输出 `not_connected` 字段 + 非 json 行尾 `[X]`；
    `pins` 单独列出 NO_CONNECT 引脚（net 恒为空）。

#### NetFlag(18)/NetPort(19) 网络命名符号

- **背景**：此前 `_collect_pinmap_data` 白名单只含 17(CBB)/22(Short)，
  NetFlag/NetPort 实例被跳过。本工程网络名由 WIRE 的 NET 承载（Global
  Net Name 冗余），无实际影响；但其他工程若 wire 无 NET 仅靠端口命名会漏。
- **修复**：
  - `_synth_designator` 为 18/19 合成 `PORT{cid}` 位号；
  - 白名单加 18/19，引脚参与连通域；
  - 端口命名：Global Net Name 挂在实例 cid 上，若其引脚命中端点无
    网络名，以端口名补充（补进 `sheet["nets"]`，pinmap/连通域同时生效）。

#### 验证

- smoke2 全回归 ALL PASS；
- `pins` 输出 `U10 VOUTA [X] NO_CONNECT` 等标记正确；
- `pinmap` 输出 PORTe363（+3.3V NetFlag）`Pin1 -> +3.3V`，端口网络名正确；
- 全工程统计：PORT 实例 610、NO_CONNECT 引脚 95（其余分布在各页）。

---

### 五、skill 审查规则（7386054）

`skill/SKILL.md` 更新：

- **NO_CONNECT 审查规则**（"器件联通审查方法"章节）：`pins`/`pinmap`
  输出中 `[X]`/`not_connected:true` 的引脚是设计者显式标"不连接"，不能直接
  当正常忽略——NC 可能掩盖设计问题：
  - 芯片未用功能脚标 X：核对手册该引脚是否需接默认电平（上拉/下拉/去耦），
    确认"真不需要"才放行；
  - 疑似"应该接却标 X"（电源/地/复位/使能/基准输入被标 NC）：必须向用户
    报告并提示确认，不得自行判定合理；
  - 审查结论中列出全部 NC 引脚清单（器件.引脚）及理由，供用户复核。
- **关键格式事实**：补 NO_CONNECT 文件格式条目（`实例id+引脚id` 复合编号、
  不参与网络解析）；
- **修正过时描述**：NetPort(18)/NetFlag(19) 已支持参与连通域 + Global Net
  Name 端口命名（输出 `PORTxxx` 合成元件），替换原"不参与连通域推断"。

---

### 六、TODO 记录（670fdce）

新增 `TODO.md`：

- **BUS/BUSENTRY 总线支持**（暂不做）：等用户提供总线工程样例后再实施。
  已记录：规范语义（BUS 网络名 `A[1:5]`、BUSENTRY `busGroupId`/`order`
  笛卡尔积分支展开）、当前缺口、预期 3 步实施方案、触发条件。
- **其他未支持**（记录）：PCB 文档（docType=3，工具定位为原理图读取）、
  Sheet Symbol(20)/VARIANT/INSTANCE/元件分组（v2 数组格式无对应数据）。

---

### 七、兼容性与回归

- 单工程所有命令行为与 json 结构不变；
- 多工程 json 结构变化仅影响 netfind/trace/link-check/find/search 五个命令
  （均属多工程专用场景，无历史单工程消费方）；
- 每次代码变更后 smoke2 全项 PASS。

### 相关文档

- `docs/同名页解析修复说明.md` — 同名页 bug 发现经过与修复详情
- 本 CHANGELOG 的 2026-08-18 节 — 本文档（原 `docs/变更记录-2026-08-18.md`）
- `TODO.md` — 未支持项记录（BUS/PCB/变体）
- `README.md` — 多工程章节输出来源标识说明
- `skill/SKILL.md` — 使用规则（含 NO_CONNECT 审查规则）

