---
name: lceda-sch-reader
description: Use when the user asks to read, query, search, extract, or verify content from any 立创EDA/LCEDA professional (EasyEDA Pro) schematic project (.eprj2 files) — component lists, net connections, pin-level netlists, trace links, device values/BOM, board/page names, Datasheet URLs, or hardware pin mapping. Runs the generic read-only tool 6_tools/lceda_sch_reader/lceda_reader.py.
---

# LCEDA 专业版原理图读取（lceda_sch_reader）

读取立创EDA专业版工程（`.eprj2`，SQLite 格式）的原理图数据。工具为**通用格式
工具**，不绑定特定工程/器件/位号；只读、仅依赖 Python 标准库，位于
`6_tools/lceda_sch_reader/lceda_reader.py`。

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
   python 6_tools\lceda_sch_reader\lceda_reader.py list
   python 6_tools\lceda_sch_reader\lceda_reader.py boards
   ```

2. 常用查询：

   | 需求 | 命令 |
   | ---- | ---- |
   | 某页元件（设计符/型号/参数） | `lceda_reader.py components "页名"` |
   | 某页网络连接 | `lceda_reader.py nets "页名"` |
   | 精确引脚网络表（推荐，含同网络关联引脚） | `lceda_reader.py pinmap "页名" [--designator U1]` |
   | 引脚级网络表（designator→网络+引脚名） | `lceda_reader.py pins "页名"` |
   | 跨页网络归并 | `lceda_reader.py netlist` |
   | 全局同网络查询(引脚级,等效网络高亮) | `lceda_reader.py netfind <网络名>` |
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

- 格式规范依据官方文档：`6_tools/lceda_sch_reader/reference/`（V3 md + V2.2 PDF），
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
- `.epro2` 备份是 zip（内含 `.epru`，V3 key-value 式 `DOCHEAD||body` **增量日志**，
  同 type+id 多条记录按 ticket/client 最终一致性合并），与 `.eprj2` 内数组式
  全量快照语义一致但写法不同。**当前工具仅支持 .eprj2（V2.2）**；V3 后端方案
  已记录在 README（单工具双后端，按扩展名自动判断），暂未实现——备份文件
  仅作历史归档，读取主工程请用 .eprj2。

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
   - 电源符号（NetPort/Power，symbol_type=18）网络名来自其 Name 属性，
     不参与连通域推断
   - 跨板电源（如 +5V 从单片机板经连接器到 ADDA）需先确认连接器对插关系

## 输出与编码

- Windows 控制台中文乱码时加 `set PYTHONIOENCODING=utf-8`，或重定向到文件后按 UTF-8 查看。
- 详细用法与历史错误核对见 `6_tools/lceda_sch_reader/README.md`。
