---
name: lceda-sch-reader
description: Use when the user asks to read, query, search, extract, or verify content from any 立创EDA/LCEDA professional (EasyEDA Pro) schematic project (.eprj2 files) — component lists, net connections, pin-level netlists, trace links, device values/BOM, board/page names, Datasheet URLs, or hardware pin mapping. Runs the generic read-only tool lceda_reader.py.
---

# LCEDA 专业版原理图读取（lceda_sch_reader）

读取立创EDA专业版工程（`.eprj2`，SQLite 格式）的原理图数据。工具为**通用格式
工具**，不绑定特定工程/器件/位号；只读、仅依赖 Python 标准库，位于
`lceda_reader.py`。

## 汇报规范（重要）

**汇报器件时必须说明所在图与页**，不要只说位号：
- 位号在**同一工程不同板/页可重复**（例：ADDA 板"四路低速DA"页的 U4 是 DAC7562，
  主控板"卧贴USB切换串口"页的 U4 是 CH343P；L1 在单片机板是磁珠、在 ADDA 板是探头滤波）。
- 规范表述：**"Schematic2（ADDA 板）四路低速DA 页 U4（DAC7562）"** 或
  **"Schematic1（单片机板）卧贴USB切换串口 页 U4（CH343P）"**。
- 用 `boards`/`list` 命令确认页归属，用 `components`/`pinmap --json` 拿器件型号。

## 使用步骤

1. 先列出板与页（页名可能跨板重名，注意区分）：

   ```bat
   set PYTHONIOENCODING=utf-8
   python lceda_reader.py list
   python lceda_reader.py boards
   ```

2. 常用查询：

   | 需求 | 命令 |
   | ---- | ---- |
   | 某页元件（设计符/型号/参数） | `lceda_reader.py components "页名"` |
   | 页内文本注释（设计意图/备注） | `lceda_reader.py texts "页名"` |
   | 工程层级树（板→原理图/PCB+游离） | `lceda_reader.py tree` |
   | 某页网络连接 | `lceda_reader.py nets "页名"` |
   | 精确引脚网络表（推荐，含同网络关联引脚） | `lceda_reader.py pinmap "页名" [--designator U1]` |
   | 引脚级网络表（designator→网络+引脚名） | `lceda_reader.py pins "页名"` |
   | 跨页网络归并 | `lceda_reader.py netlist` |
   | 全局同网络查询(引脚级,等效网络高亮) | `lceda_reader.py netfind <网络名>` |
   | 多工程连接器对核对(候选) | `lceda_reader.py link-check` |
   | 多工程链路(经连接器桥跨工程) | `lceda_reader.py trace U1 --link "0:H2<->1:H2"` |
   | 链路追踪（沿网络BFS多跳，跨页） | `lceda_reader.py trace U1 [--no-power] [--depth N]` |
   | Designator 反查（页/板/型号/网络） | `lceda_reader.py find U1` |
   | 跨页搜器件/关键字 | `lceda_reader.py search "正则"` |
   | 全工程 BOM（按板过滤） | `lceda_reader.py bom [--board 板名] [--bom-only]` |
   | Datasheet URL 清单 | `lceda_reader.py datasheets` |
   | 页全部属性（@Board Name 等） | `lceda_reader.py attrs "页名"` |
   | uuid 反查器件 | `lceda_reader.py devmap` |
   | 原始 NDJSON（调试） | `lceda_reader.py raw "页名" [-o 文件]` |
   | 结构化 JSON（供脚本） | `--json` 前缀，如 `lceda_reader.py --json bom` |

## 关键格式事实（勿重新猜测，官方规范为准）

- 格式规范依据官方文档：`reference/`（V3 md + V2.2 PDF），
  在线：https://image.lceda.cn/files/lceda-pro-file-format-v3_2025.10.21.md
- `.eprj2` 是 **SQLite**（不是 zip）；用 `mode=ro` 只读连接，**编辑器开着也能读**。
- `documents.dataStr` = `base64` 前缀 + base64(gzip(NDJSON))，NDJSON 每行一个 JSON 数组。
- 记录类型：`["COMPONENT", id, title, x, y, ...]`、`["ATTR", uuid, comp_id, name, value, ...]`、
  `WIRE`/`TEXT`/`RECT`/`PART`/`PIN` 等；坐标单位 0.01 inch。
- **uuid 双命名空间（互斥）**：`Symbol` uuid → `components` 表（符号定义，含 PIN/NAME/NUMBER 引脚表）；
  `Device` uuid → `devices` 表（型号/描述）。Device→Symbol 用 `attributes` 表 `key='Symbol'` 桥接。
- 网络 = ATTR 记录 name `NET`/`Global Net Name` 挂在 WIRE 上（官方约定导线必须带 NET 属性）；
  页面数据中无 PIN 记录，PIN 只在符号定义（components.dataStr）里。
- 页归属以 `schematics` 表 uuid 为准；标题块 `@Board Name` 可能有复制残留或为空。
- 器件真值（如阻值/容值/描述）在 `devices.description`；`--json` 时 `value` 字段已结构化解析。
- 引脚级网络归属（pins/nets/netlist/trace/find/pinmap）**全部基于连通域精确方案**
  （实例坐标+PIN坐标+旋转/镜像 → 绝对坐标 → 精确匹配 WIRE 端点网络名），
  不再是几何近似。经串阻/磁珠/短接符间接连接的引脚链路完整。
- **`pinmap` 输出 symbol_type 与 pin_type**：元件 `symbol_type`（2=Part/18=电源/
  19=NetPort/22=Short 短接符/21=NoneElec）用于区分真实器件与框图/电源符号；
  引脚 `pin_type`（Undefined/IN/OUT/BI/Power）用于信号方向。**注意**：V2.2 数组
  格式无官方 V3 的 electric 字段，pin_type 从符号 "Pin Type" ATTR 读取——多数
  芯片符号未标注该属性（实测为 Undefined），**不可依赖它判断信号方向**。
- **`.epro`（V2 ZIP 导出）与 `.epro2`（V3 ZIP 导出）均直接支持**：`--eprj`
  显式或自动探测。EproDB/Epro2DB 后端把格式差异归一化（V3：Y 向上坐标取反、
  CANVAS 原点、COMPONENT.partId 即符号内 PART 名、符号类型=META.docType
  （17=CBB/18=电源/19=NetPort/22=Short/25=OffPage）、引脚名键
  Pin Name/Pin Number），命令用法与 .eprj2 完全一致。`.epro2` 的 .epru 为
  增量日志（同 uuid 多段按 ticket 合并）。
- **CBB（复用块，symbol_type=17）已支持展开**：黑盒实例位号 CBBn。匹配
  优先级（前三为**唯一精确映射，单文件即可，无需 --cbb-map**）：
  `--cbb-map` 显式指定 > **V3 INSTANCE 文档**（.epro2：uuid 编码
  母图页+实例cid→模板页，并含成员母图位号）> 后端原生符号映射
  （.epro `symbols[uuid].title`=板名，即立创EDA 导入还原机制；.epro2
  SYMBOL META docType=17；同目录 .eprj2 的 structure.blockSymbols 亦可）>
  端口名集合匹配（仅兜底；**只接受唯一候选**，多候选告警跳过——副本页
  内容可能不同，不做等价假设）。**单文件即可精确展开，不要求组合文件**。
  展开后 netlist/trace/netfind/nets/pins 出现 `CBBn.成员位号` 条目，
  **母图位号优先**（INSTANCE_ATTR 记录的改名成员），未改名成员沿用模板
  位号（与立创EDA 行为一致）；net 为"内部网络,父网络"并集——链路分析可
  贯通 CBB 内部。注意：`pinmap` 仍是黑盒视图；`find` 不索引展开位号
  （查内部器件直接查模板页）；CBB 模板页在导出文件中作为独立"板"列出。
  **新版 .eprj2（documents 表空、内容加密 history_data）已支持自动解密
  读取**——detect_backend 检测后自动走 AES-128-GCM 解密→临时 .epro2→
  Epro2DB，对用户完全透明。算法详见 docs/新版eprj2格式逆向与破解.md。
- **新版加密 .eprj2 的 CDP 导出备选方案**：当自动解密不完整（如需获取
  INSTANCE 母图位号映射）时，可用 `probes/export_newfmt.py` 通过 CDP 从
  运行中的 LCEDA 内存提取解密后文档，打包为更完整的 .epro2。
  前提：`lceda-pro.exe --remote-debugging-port=9222 <工程.eprj2>` 已启动。
  用法：`python export_newfmt.py <工程.eprj2路径>` → 自动生成 `<名>_export.epro2`。
- **dom 网络多值分隔**：内部使用 UNICODE 分隔符（U+241F）规避网络名含
  逗号的歧义；输出兼容——`pinmap.pins[].net` 为逗号显示，精确列表见
  `nets` 数组字段；历史逗号拼接值自动兼容。
- **DNP（未贴装）标志已纳入链路分析**：实例属性 `Add into BOM=no` 或
  `Convert to PCB=no` 视为 DNP——**0Ω 跳线/短接符两脚不再合并网络**（物理
  未贴装），pinmap 输出 `dnp:true` + 文本 `[DNP]` 标记。审查时注意：
  - DNP 0R 两侧网络各自独立是**预期行为**，不是断链 bug；
  - 非 DNP 的 0R 才是跨网络桥；
  - "不上BOM"的测试点等非桥器件不影响连通性。
- **NO_CONNECT（X 不连接）**：文件内为 ATTR `NO_CONNECT=yes`，挂在
  `实例id+引脚id` 复合编号上（如 `e130e198` = 实例 e130 + PIN e198）。
  `pins`/`pinmap` 输出 `[X]`（json `not_connected:true`）标记，且**不参与**
  网络解析。审查时须确认每个 NC 是否真的不需要（见"器件联通审查方法"）。
- **框图页（系统框图/电源框图）**：pinmap 对框图页返回空（预期——框图器件是
  NoneElec 图形符号无 PIN）。**做架构分析或交叉核对时用 `components 系统框图`/
  `components 电源框图` 读取顶层架构**（块/电源拓扑），并与 pinmap 实际连接
  交叉核对——框图与原理图连接矛盾说明框图过时或原理图有误。
- **网络配对规则**：同名网络即同一电气网络，跨页自动归并（netlist/trace 已跨全工程）；
  连接器（H1/H2 等板间排针）是跨板桥。`trace` 用 `--no-power` 跳过 GND/VCC/3.3V 等
  常规电源网络避免爆炸展开，`--depth` 限跳数。短接符（SHORTxxx）是跨网络桥：
  两脚所在域合并（如 H_RESET 经 SHORT 接 RST），netlist 中两个网络都含该节点。
- **连接器跨板归并的边界（必须校验，勿当事实）**：同名网络自动归并只在"连接器
  两侧恰好同名"时正确——立创EDA **不强制校验**连接器两侧网络名一致，同名网络
  ≠ 必然物理相连；不同名也可能相连。对插连接器由硬件设计决定（文件内无此信息），
  且同板可能多个同型号连接器（当前工程两板各有 H1/H2/H3），**仅靠位号无法确定
  哪个与哪个插**；对插 pin 数也可不同。**跨板链路应标记"经同名网络假设相连，
  需校验连接器对应关系"**；无连接时提示检索两侧可对插连接器（同型号/同 pin 数
  候选），由 LLM 主动核对确认。
- **位号前缀不可作为功能依据**：工具不假设位号前缀（R/C/U/L 等），一切以器件型号/
  描述为准（如 0Ω 跳线按型号含 0000 识别，电阻也可能标为 U 或别的位号）。**不要根据
  位号前缀判断器件类型**，用 `components` 的 device 字段。
- 同号位器件跨板重复：汇报必须带"哪个板哪个页"（见上文汇报规范）。
- **工程名 vs 文件名**：.epro2/新版 .eprj2 含用户命名工程名（tree 首行
  双显示"工程: X（文件: Y）"，json hierarchy 含 project_title）；旧版
  .eprj2 与 .epro 无内部工程名（projects.name 为立创默认名），以文件名为准。
- **页内文本注释是审查对象**：`texts "页名"` 导出设计者手写注释（如
  "OE接VCC或者悬空使能"、"与测温有关"）——常含关键设计意图、调试结论、
  未落图约束。审查原理图时先读 texts 再分析连接，避免误判"多余/缺失"。
  **但注释内容不一定正确**：可能过时（改版后未更新）、与实现不符、或本
  身是错误推测——**注释的正确性必须对照器件数据手册与电路实际用途核实**
  （例：注释说"输出悬空"但手册要求该脚接默认电平，或实测引脚已连线）。
  发现注释与手册/实测矛盾时，在审查结论中明确标注"注释存疑，需与设计者
  确认"，不得当作已核实事实引用。
- `.epro2` 是 zip（内含 `project2.json` + `.epru` V3 增量日志 + IMAGE 缩略图），
  与 `.eprj2`/`.epro` 语义一致但写法不同（详见 Epro2DB 后端）。三格式
  （.eprj2/.epro/.epro2）均已支持，单文件即可完整读取。

## 多工程使用（关联工程分析）

`--eprj` 可多次指定（如主控板工程 ↔ ADDA 板工程）：

1. **netfind 多工程**：分工程输出，标注 `工程#N`，**不跨工程合并网络名**
   （跨工程同名网络是独立命名空间）。
2. **link-check**：列出两工程间"网络名逐 pin 一致"的连接器对候选。
   **注意**：多个同型号连接器（如两 H1/H2 都 40/40 一致）会全部列出，
   需人工判断实际对插——连接器物理关系是设计知识，工具只能给候选。
3. **trace 跨工程**：必须 `--link "0:H2<->1:H2"` 显式声明连接器对；
   **仅同名网络经桥导通**（连接器引脚对齐语义）。未指定 --link 时只在
   本工程内展开（跨工程不自动匹配）。

```bat
python lceda_reader.py --eprj A.eprj2 --eprj B.eprj2 netfind <网络名>
python lceda_reader.py --eprj A.eprj2 --eprj B.eprj2 link-check
python lceda_reader.py --eprj A.eprj2 --eprj B.eprj2 trace U1 --link "0:H2<->1:H2"
```

多工程支持：netfind/link-check/trace/find/search；其余命令单工程运行。

## 器件联通审查方法（LLM 引导，非脚本自动化）

对指定器件做连通性/外围电路审查（如芯片电源去耦、基准输出负载、输入链拓扑），
**不要指望单一命令完成**——按以下步骤组合 pinmap/trace/netlist 原语：

1. **直接连接**：`pinmap <页> --schematic <板> --designator <器件> --json`
   - 每个引脚：`net`（网络名，`*`=推断）、`peers`（同物理连接点引脚）、
     `wire_peers`（同导线记录其他器件引脚）
2. **识别连接器件类型**：`components <页>` 查 peers/wire_peers 中器件的 device 字段
   （电阻/电容/磁珠/运放/隔离器/短接符…）
3. **按类型扩展**：
   - 两脚无源器件（阻/容/磁珠）→ **递归 `pinmap` 该器件另一端引脚**，获取其
     另一侧网络（如 U26.IN0→C56/R47→C56.1=AGND、R47.2→下一级）；若另一端
     网络名为空，继续沿 wire_peers 跳转（串阻/耦合链逐级展开）
   - 运放/隔离器等有源器件 → 检查输入侧与输出侧分别连接的网络，识别反馈/
     隔离边界
   - 短接符（SHORTxxx）→ 两脚同网络，跨网络桥（如 H_RESET↔RST）
   - 磁珠 → 电源域隔离点（如 VREF2.5V→L1→+3V3A）
4. **跨网络可达性**：`trace <器件> --no-power --depth N` 验证多跳连通；
   注意 trace 只沿**有网络名**的边跳——串联器件的空网络名侧需靠 Step 3 递归补全
5. **负载完整性**：`netlist` 查目标网络全部成员（如 VREF2.5V 应含所有基准输入器件）

**审查原则**：
- 网络名为空的引脚 ≠ NC——可能是串联链的中间点，需沿 wire_peers 跳转确认
- **NO_CONNECT（`[X]` 标记）必须逐一确认是否真的需要 NC**：
  `pins`/`pinmap` 输出中 `[X]`/`not_connected:true` 的引脚是设计者显式标"不连接"
  （文件内 `NO_CONNECT` ATTR），**不能直接当正常忽略**——NC 可能掩盖设计问题：
  - 芯片未用功能脚标 X：应核对数据手册该引脚是否需接默认电平（上拉/下拉/
    去耦），确认"真不需要"才放行；
  - 疑似"应该接却标 X"（如电源/地引脚、复位、使能、基准输入被标 NC）：
    **必须向用户报告并提示确认**，不要自行判定合理；
  - 审查结论中列出全部 NC 引脚清单（器件.引脚）及理由，供用户复核。
- 连接器（H1/H2 等）是板间桥，跨板审查需先确认两侧对插关系（见连接器边界说明）
- 结论必须带"哪个板哪个页哪个器件"，同号位器件跨板重复

## PDN（电源分配网络）审查方法

电源网络审查 = 追踪电源从源头到各负载 + 核对去耦：

1. **列出电源网络**：`netlist` 过滤 GND/AGND/+5V/+3.3V/D3V3/+3V3A/+15V/-15V/VBUS
2. **追踪源与分支**：`trace <电源器件> --no-power`（如 LDO U5、基准 U28），
   观察磁珠（L1-L5）隔离的各电源域
3. **逐芯片核对去耦**：对每个有 VCC/VDD/AVDD 引脚的芯片执行
   `pinmap --designator <芯片>`，检查其电源引脚 wire_peers 中是否含去耦电容
   （100nF/1µF/10µF）
4. **模拟/数字分离**：AGND vs GND、+3V3A vs +3.3V 是否按设计分离；
   磁珠/0Ω 是域间桥
5. **PDN 审查的已知限制**：
   - 去耦电容可能挂在电源网络其他位置而非紧邻芯片引脚（wire_peers 只显示
     同导线记录，跨网络电容需 netlist 该电源网络核对）
   - 电源符号（NetPort/Power，symbol_type=18）与 NetFlag(19) 已参与连通域，
     网络名以 Global Net Name 端口命名补充（工具输出中显示为 `PORTxxx` 合成
     元件）；但跨板电源（如 +5V 从单片机板经连接器到 ADDA）仍**不自动跨板**
     归并，需先确认连接器对插关系

## 输出与编码

- Windows 控制台中文乱码时加 `set PYTHONIOENCODING=utf-8`，或重定向到文件后按 UTF-8 查看。
- 详细用法与历史错误核对见 `README.md`。
