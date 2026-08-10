# 立创EDA专业版原理图读取工具（lceda_reader）

针对**立创EDA专业版工程格式**（`.eprj2` SQLite 工程）的通用只读解析工具。
不绑定特定工程、器件、位号或网络名，可读取任何符合该格式的工程文件。
支持元件清单、网络连接、引脚级网络表、链路追踪、器件信息、全文搜索、
BOM、Datasheet 等只读查询。**本工具为只读**，不修改任何工程数据。

## 一、使用方法

```bat
rem 建议先设置 UTF-8 输出，避免中文在 GBK 控制台乱码
set PYTHONIOENCODING=utf-8

python lceda_reader.py list                 rem 列出全部板(Schematic)与页(sheet)
python lceda_reader.py boards               rem 列出每页的 @Board Name/@Page Name 标题块
python lceda_reader.py components [页名]     rem 页内元件：设计符/型号/显示名/参数描述
python lceda_reader.py nets <页名>           rem 页内网络连接（stub端点归属元件）
python lceda_reader.py pinmap <页名> [--designator U1]   rem 精确引脚网络表(坐标精确匹配+同网络关联引脚)
python lceda_reader.py pins <页名>           rem 引脚级网络表（designator→网络+符号引脚名匹配）
python lceda_reader.py netlist              rem 跨页网络归并（网络名→页/元件）
python lceda_reader.py netfind <网络名>      rem 全局同网络查询（引脚级，等效"网络高亮"）
python lceda_reader.py trace <设计符> [--no-power] [--depth N]   rem 链路追踪：从器件沿网络BFS跨页展开
python lceda_reader.py find <设计符>         rem Designator 反查（页/板/型号/网络）
python lceda_reader.py search <正则>         rem 跨全部页全文搜索
python lceda_reader.py bom [--board 板名] [--bom-only]   rem 全工程物料清单（按器件uuid归并）
python lceda_reader.py datasheets           rem 从 attributes 表导出 Datasheet URL 清单
python lceda_reader.py attrs <页名>          rem 页全部属性（含标题块@项）
python lceda_reader.py devmap               rem 导出 devices/components 表（uuid->器件）
python lceda_reader.py raw <页名> [-o 文件]  rem 输出页的原始NDJSON（调试用）

python lceda_reader.py --json <命令>         rem 结构化 JSON 输出（供脚本消费）
python lceda_reader.py --eprj <路径> <命令>  rem 指定工程文件（默认搜索当前目录及父目录 *.eprj2）
```

示例（通用形式）：

```
> python lceda_reader.py components <页名>
## <页名> (sch=schematicN)
R1	<型号>.1	<型号>	<参数描述>
U1	<芯片型号>.1	<芯片型号>	<参数描述>

> python lceda_reader.py pins <页名>
U1	<芯片型号>.1	<网络名>	pin[5:<引脚名>]  (d=10.0)

> python lceda_reader.py netlist | findstr <网络名>
<网络名>  <页列表>  <元件列表>

> python lceda_reader.py trace U1 --no-power
[<网络名>] U1 -> R1 -> <下一页元件> ...
```

## 二、文件格式（与官方规范一致）

本工具基于官方《嘉立创EDA文件格式》规范实现，规范文档见 `reference/` 目录
（V3 2025.10.21 版本 md，及 V2.2 版 PDF），在线地址：
https://image.lceda.cn/files/lceda-pro-file-format-v3_2025.10.21.md

`.eprj2` 是 **SQLite 数据库**（不是 zip）。关键表：

| 表 | 用途 |
| --- | --- |
| `schematics` | 板：uuid, name, display_name |
| `documents` | 页：docType=1 原理图页 / 3=PCB页；`dataStr` 为压缩内容 |
| `components` | **符号库**：uuid -> title/display_title/description + dataStr（SYMBOL 定义，含 PIN/NAME/NUMBER） |
| `devices` | **器件库**：uuid -> title/display_title/description（型号/封装/参数描述） |
| `attributes` | 器件属性（key, value, device_uuid）：Datasheet/Manufacturer/Supplier Part/Add into BOM/Symbol 等 |

**uuid 双命名空间（互斥，交集为 0）**：
- 页面 ATTR 的 `Symbol` uuid → `components` 表（符号定义）
- 页面 ATTR 的 `Device` uuid → `devices` 表（器件型号/描述）
- 桥接：`Device uuid → attributes 表 key='Symbol' 的 value` 可得该器件的符号 uuid

### dataStr 解码链

```
dataStr = "base64" 前缀 + base64(gzip(NDJSON 文本))
解码后每行一个 JSON 数组（数组式记录格式）：
  ["DOCTYPE","SCH","1.1"] / ["DOCTYPE","SYMBOL","1.1"]
  ["COMPONENT", id, title, x, y, rot, mirror, {}, flags]
  ["ATTR", attr_uuid, comp_id, attr_name, value, ...]
  ["WIRE", id, [[x1,y1,x2,y2],...], style, flags]
  ["PART", title, {"BBOX": [xmin, y1, xmax, y2]}]   （符号页；y 可能倒序，需归一化）
  ["PIN", id, ...x, y, len, rot...]                   （符号页；引脚端点坐标）
```

- 元件：`COMPONENT` 记录（title 形如 `<型号>.1`）+ 挂在其上的 `ATTR`
  记录（`Designator`、`Symbol`/`Device` uuid、`Name` 等）。
- 网络：`ATTR` 记录 name 为 `NET`（局部）或 `Global Net Name`（全局），值即网络名，
  挂在 **WIRE** 上（官方约定：导线必须带 NET 属性）；无名 WIRE 保留为 net=None stub。
- 引脚定义：`components.dataStr`（DOCTYPE=SYMBOL）中 `PIN` 记录 + NAME/NUMBER ATTR。
- 页标题块：comp_id=`e1` 上的 ATTR，如 `@Board Name`、`@Schematic Name`、
  `@Page Name`、`Version`。
- 器件真值（如阻值/容值/型号描述）：在 `devices.description`，经 Device uuid 查表；
  `--json` 时 `value` 字段已结构化解析。
- 坐标单位：0.01 inch（官方约定）。

### 兼容备份格式（.epro2 / .epru）

`.epro2` 备份文件为 zip 容器：内含 `*.epru`（**不压缩**的 `DOCHEAD||body`
key-value 式记录序列，文档间以 `|\n` 分隔，docType 含 FOOTPRINT/SYMBOL/DEVICE/
BOARD/SCH/SCH_PAGE/PCB/CONFIG）+ `IMAGE/*.webp` 位图。此为官方 V3 key-value
式日志格式（与 .eprj2 内的数组式记录不同，但语义一致）。

## 三、网络查询方法（配对/链路/跨页）

**1. 找某器件连接到哪里（单点）**
```
python lceda_reader.py find U1        # 反查：页/板/型号 + 全部网络名
python lceda_reader.py find U1 --json # 结构化输出
```

**2. 查某网络连了哪些器件（配对，跨页归并）**
```
python lceda_reader.py netlist | findstr <网络名>
```
配对规则：同名网络（`NET`/`Global Net Name`）即同一电气网络，跨页自动归并；
端口（netport）与电源符号（GND/VCC 等）的 Name 也计入网络。

**3. 链路追踪（从器件出发沿网络 BFS 多跳展开）**
```
python lceda_reader.py trace U1 --no-power
```
- `--no-power` 跳过电源/地网络（GND/AGND/VCC/3.3V/5V/±15V/VBUS 等常规命名），
  避免爆炸式展开（若工程电源网络命名特殊，可省略该参数）
- `--depth N` 限制跳数（一跳 = 经过一个网络）
- **trace 基于 pinmap 连通域精确方案**（与 pinmap 同源）：经串阻/磁珠间接连接的
  引脚链路完整（如 U18 的 SCLK/MOSI/CS 全部可达），短接符（SHORTxxx）作为
  跨网络桥出现在链路中（如 H_RESET 经 SHORT 接 RST）。

**4. 跨原理图主动查找**
- `netlist`/`trace` 本身跨全部页归并；`find` 会列出元件所在的所有页
- 页归属以 `schematics` 表 uuid 为准；注意同名页在不同板可能存在

**5. 连接器语义与跨板归并（重要边界）**
- **同名网络 ≠ 必然物理相连**：立创EDA 中网络是工程级全局命名空间，但**不强制校验
  连接器两侧网络名一致**。同名网络自动归并（netlist/trace 现状）在"两侧恰好同名"
  时正确，但**不能作为物理连接的证明**。
- **连接器对需人工/LLM 确认**：两板对插的连接器（如单片机板 H1 排针 ↔ ADDA 板
  H1 排母）由硬件设计决定，文件内无此信息；且同板可能有多个同型号连接器
  （当前工程两板各有 H1/H2/H3），仅靠位号无法确定哪个与哪个插。
- **对插连接器 pin 数可不同**（如 2×20 对 2×18 部分使用），网络名也未必逐 pin
  对应——核对时以物理对插关系为准，不能假设 pin 序号对齐。
- **跨板链路输出应带标记**：若工具自动输出跨板连接（按同名网络归并），应标记
  "经连接器同名网络假设相连，需校验两侧连接器对应关系"，避免 agent 误当作
  已验证事实。

## 四、注意事项（通用坑）

1. **工程文件可能被立创EDA编辑器占用**：SQLite 直连会报 "database is locked"，
   工具已用 `file:...?mode=ro` 只读 URI 连接，编辑器开着也能读。
2. **控制台乱码**：Windows GBK 控制台打印 UTF-8 中文会乱码，加 `set PYTHONIOENCODING=utf-8`，
   或将输出重定向到文件后用 UTF-8 查看。
3. **页名可能重名**：`components`/`nets`/`pins`/`attrs` 会列出全部同名页，
   按 `boards` 命令的输出区分。
4. **标题块属性可能有复制残留**：某页 @Board Name 可能与实际 schematic 不符，
   归属以 `schematics` 表 uuid 为准；部分页标题块全空（@Board Name 为空），
   BOM `--board` 过滤按 schematic 名兜底。
5. **废弃页**：工程中可能有废弃的板/页（如标题块为空或只有标题的页），
   提取 BOM 时注意排除。
6. **网络归属全部基于连通域精确方案**（pins/nets/netlist/trace/find/pinmap 同源）：
   实例坐标 + PIN 相对坐标 + 旋转/镜像 → 引脚绝对坐标 → 精确匹配 WIRE 端点网络名。
   经串阻/磁珠/短接符间接连接的引脚链路完整，无几何近似的遗漏或噪声。
7. **`pinmap` 输出 peers/wire_peers**：对网络名为空的引脚输出 `peers`（同物理连接点
   引脚）与 `wire_peers`（同导线记录的其他器件引脚），用于识别串阻/耦合电容/
   晶体管链路，如：`LED1.A <- R8.1`、`LED1.K [wire: BUZZER1.2,D2.+,Q1.D]`。
8. **`pinmap` 的连通域网络名推断**（默认开启，`--no-domain` 关闭）：基于走线
   拓扑——同 WIRE 记录端点相接 = 同一物理网络；0Ω 跳线（按型号含 0000 识别，
   不依赖位号前缀）两脚直连合并；两脚无源器件（串阻/磁珠）作为网络名传播桥，
   **仅从"直接命名的引脚"单向传播到"未命名引脚"**（避免经上拉电阻把信号名
   污染到 GND 域、避免多桥竞争噪声）。推断结果标记 `net_inferred=true`。
   已实测 U4/U3/U26/U27/U18/U2 全部正确（U4.MOSI→LOW_DA_MOSI、U27.CS→H_DA_CS、
   U26.SCLK→H_AD_SCLK、U18.SCLK→TEMP_IN_SCLK 等）。
   **修复记录**：早期启发式递归会遍历多引脚芯片全部引脚造成噪声（U4.MOSI 曾
   混入 LOW_DA_CLR/LDAC）；走线连通域方案初期曾因"双向桥传播"经上拉电阻
   （如 R63）把信号名串到相邻网络（U27.CS 曾误报 H_DA_MOSI），改为单向
   命名脚→未命名脚传播后全部修正。
9. 个别器件无 Symbol 属性（只有 Device）时靠 attributes 表桥接；
   若桥接失败则该器件引脚无法参与连通域分析。
10. **--json 输出为完整结构化数据**：`nets` 的 points 为所有 stub 端点坐标，
    `bom` 含 value 结构化字段、boards/sheets 归并；`pinmap --json` 的 pins 含
    net/peers/wire_peers 字段，可直接供脚本/agent 判断电路拓扑。
11. **Short Symbol（短接符，symbolType=22）**：官方规范定义其两脚属于同一网络
    （跨网络短接）。工程实例（如"对外连接"页 SHORTe679 连接 H_RESET 与 RST）已
    作为 0Ω 跳线同等处理（两脚域合并），netlist 中两个网络都含该桥节点。
12. **symbol_type / pin_type 已输出**：pinmap --json 的元件含 `symbol_type`
    （2=Part/18=电源/19=NetPort/22=Short/21=NoneElec 等），引脚含 `pin_type`
    （Undefined/IN/OUT/BI/Power）。**注意**：V2.2 数组格式的 PIN 记录**无官方 V3
    的 electric 字段**，pin_type 从符号 "Pin Type" ATTR 读取——多数芯片符号未标注
    该属性（实测为 Undefined），**不可依赖它判断信号方向**。
13. **框图页（系统框图/电源框图）**：pinmap 对框图页返回空（预期——框图器件是
    NoneElec 图形符号，无 PIN）。做架构分析或交叉核对时用 `components 系统框图`/
    `components 电源框图` 读取顶层架构，并与 pinmap 实际连接交叉核对——框图与
    原理图连接矛盾说明框图过时或原理图有误。
14. **位号前缀不可作为功能依据**：工具不假设位号前缀（R/C/U/L 等），0Ω 跳线按
    器件型号（含 0000）识别，器件类型一律查 `components.device` 字段。工程中
    可能出现非标准位号（如电阻标为 U），也可能同号位器件跨板重复——**汇报器件时
    必须说明所在板与页**（如"ADDA 板四路低速DA 页 U4（DAC7562）"）。

## 五、格式规范来源与逆向过程记录

- 官方格式规范文档（`reference/` 目录）：V3 版 md（2025.10.21）与 V2.2 版 PDF。
  在线获取：
  - V3: https://image.lceda.cn/files/lceda-pro-file-format-v3_2025.10.21.md
  - V2.2 zip: https://image.lceda.cn/files/lceda-pro-file-format-v2.2_2022.12.15.zip
- 本工具逆向过程记录（早期失败尝试与修正）见 `archive_探查脚本/` 与下表。
  注意：**以官方规范为准**，archive 仅保留历史，不作为格式依据。

### 历史逆向错误核对（教训记录）

| # | 错误 | 现象 | 正确做法 |
| --- | --- | --- | --- |
| 1 | 误以为 dataStr 是纯 JSON | 直接 `json.loads(ds)` 全部报 "parse error" | dataStr 是 base64+gzip，解码后是 **NDJSON**（每行一个数组），必须按行解析 |
| 2 | 误以为解压后是单个 JSON 树 | 递归 walk 找 `component` 键，几乎一无所获 | 行式记录：`COMPONENT`/`ATTR`/`WIRE`… 是**数组**不是对象 |
| 3 | 按 "Value" 属性取元件值 | 取 `ATTR name=Value`，全部 None | 页数据中无 Value；真值在 `devices.description`（Device uuid 查表） |
| 4 | 误以为有 PIN/NET/PORT 记录类型 | 过滤 `a[0] in ("PIN","NET","PORT")` 无输出 | 页面网络是 `ATTR` name=`NET`/`Global Net Name` 挂在 WIRE 上；PIN 记录只在符号定义里 |
| 5 | 认为 .eprj2 是 zip | 打开失败（被编辑器占用+格式不对） | 是 SQLite；且用 `mode=ro` 绕过占用锁 |
| 6 | 脚本内硬编码中文绝对路径 | 路径经 GBK/UTF-8 转换易乱码、换机即失效 | 工具自动查找，支持 `--eprj` 指定 |
| 7 | 页归属只看 @Board Name | 标题块残留导致归属误判 | 以 `schematics` 表 uuid 归属为准 |
| 8 | 器件 uuid 只查 devices 表 | 部分 Symbol uuid 查不到 | **双命名空间**：Symbol→components、Device→devices（互斥）；Device→Symbol 用 attributes 表桥接 |
| 9 | attributes 表列名误以为 name | 按 name 查询报错 | schema 为 `key/value/device_uuid` |
| 10 | 网络归属误以为单对单 | 一个网络连多个元件 | 多对多：网络所有端点分别归属最近元件 |
| 11 | BBOX 顺序误以为 xmin,ymin,xmax,ymax | 解析出 min>max | 顺序为 [xmin, y1, xmax, y2]，y 可能倒序，需归一化 |

## 六、与归档脚本的对应关系

`archive_探查脚本/` 中为此工具开发前的临时探查脚本，功能均已并入本工具：

| 归档脚本 | 功能 | 工具命令 |
| --- | --- | --- |
| sch_inspect.py / sch_schema.py | 列表/建表语句 | `--eprj` 内部 + `devmap` |
| sch_list.py | 板与页清单 | `list` |
| sch_boards.py | 页 @Board/@Page 属性 | `boards` |
| sch_bom.py / sch_attrs2.py | 页内元件+属性 | `components` |
| sch_findchip.py / sch_kw.py | 器件搜索 | `search` |
| sch_devmap.py / sch_devres.py | uuid->器件解析 | `devmap` / `components` / `bom` |
| sch_magic.py / sch_raw.py | 格式探测（gzip 魔数） | `raw`（已内置解码链） |
| sch_pins.py / sch_u18.py | 网络/ATTR 探索 | `nets` / `pins` / `attrs` |
| sch_attrs.py / sch_decompr.py / sch_parse.py | 早期失败尝试 | 已被 `components`/`raw` 取代 |

## 七、开发说明

- 仅依赖 Python 标准库（sqlite3/json/base64/gzip/re/argparse），Python 3.8+ 可用。
- 只读设计：所有连接使用 `mode=ro` URI，不会写工程文件。
- 若立创EDA升级格式（dataStr 压缩链变化），`decompress()` 中的 gzip 回退分支
  可扩展（参考 archive 中 sch_magic.py 的 zlib 探测思路）。
- 引脚网络归属（pins/nets/netlist/trace/find/pinmap）统一基于**连通域精确方案**
  （实例坐标+PIN坐标+旋转/镜像 → 绝对坐标 → WIRE 端点精确匹配），非几何近似。
- **V2.2 / V3 格式兼容（方案记录，暂未实现）**：
  - 差异：V2.2（.eprj2）= SQLite + 数组式 NDJSON 全量快照；V3（.epro2/.epru）=
    ZIP + `DOCHEAD||body` 对象式**增量日志**（同一 type+id 多条记录按 ticket 大者
    保留、client 小者保留的最终一致性合并）。
  - 方案：单一工具 + 后端抽象（backend）——输入 .eprj2 用 SQLite 后端、.epro2/
    .epru 用 V3 后端，按文件扩展名/魔数自动判断，命令层复用（连通域/引脚匹配/
    网络推断与格式无关）。
  - 优先级：当前 .epro2 仅为历史备份（主工程是 .eprj2），无实际读取需求，搁置；
    需实现时从"V3 读取+list+components"起步，pinmap 连通域逻辑直接复用。
- **pin_type 为尽力而为**：依赖符号是否标注 "Pin Type" ATTR（实测多数芯片为
  Undefined），不作为判断信号方向的依据，也不为其增加复杂度。
- 官方 API Skill 项目（可在线调试/扩展立创EDA）：https://github.com/easyeda/easyeda-api-skill
