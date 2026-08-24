# AGENTS.md — lceda_sch_reader（立创EDA 原理图通用读取工具）

独立 git 仓库，remote = `github:alwaysmy/lceda-sch-reader.git`。
工作目录：`D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader`
（2026-08-21 自总仓库 `6_tools\lceda_sch_reader` 迁入，避免在总仓库误操作）。
本文件对参与本仓库开发的 AI 助手与开发者生效。

## 仓库定位

- **通用格式工具**：读取立创EDA 专业版工程（.eprj2/.epro/.epro2），
  **不绑定**任何特定工程/器件/网络名/位号。
- 单文件 CLI：`lceda_reader.py`（仅标准库）；三后端 duck-typing
  （LcedaDB/EproDB/Epro2DB，SchemaBackend ABC），命令层复用。
- 配套文档：`README.md`（用法）、`skill/SKILL.md`（使用规则/审查方法，
  **未安装到 opencode**，需人工验证后按 opencode skill 规范放置）、
  `docs/开发文档.md`（解析层陷阱/已知限制，**改动解析层前必读**）、
  `TODO.md`（未支持项）、`docs/变更记录*.md` 与专项文档。

## 文档管理（强制）

1. **新类型信息 → 在 `docs/` 下新建独立文档**，不要堆入已有文档。
2. 解析层事实/陷阱/待验证项统一维护在 `docs/开发文档.md`（第 2、4 节），
   改动解析层代码后同步更新。
3. 变更流水：追加到 `docs/变更记录-<日期>.md`（或新建当日文档）。

## Git 工作流（强制）

1. **提交纪律**：任何代码改动之后、进行下一步改动之前，必须先
   `git commit`（**禁止使用 stash**）。
2. **半成品提交**：即使改动是半成品，也要提交，提交信息必须以 `[WIP]`
   开头并注明"半成品原因"，例如：
   `[WIP] CBB 展开母图位号（半成品：INSTANCE 段解析未完成）`
3. main 分支保持基线可用；工作直接在 main 进行（本工具单人使用，无分支
   并发），但**提交前必须跑回归**（见下）。
4. **严禁在总仓库（E_distance）误操作 git**：本仓库独立于总仓库，所有
   提交/推送限定在 `3_WorkTools\sch_review_tool\lceda_sch_reader` 内；
   在总仓库执行 `git add -A`/commit 前必须 `-C <总仓库>` 明确指定且确认
   意图（2026-08-21 曾因默认工作目录误提交总仓库，已 reset 撤销）。

## 探针/测试脚本（强制）

1. 临时/探测/调试脚本一律存放本仓库 `probes/` 并入库（随仓库版本管理，
   提交信息注明用途）——**禁止放系统临时目录**（`%TEMP%`、opencode temp）。
2. `probes/smoke2.py` = 基础回归（LcedaDB 9 命令 + json 校验）。
3. `probes/verify_all_formats.py` = 全盘格式验证（本机全部工程文件：
   5 官方示例 + 涡流/MCU主控/Piezo/TPS56C230，含同工程跨格式交叉对比）。
4. **回归纪律（改动解析层/后端后最低验证）**：
   - smoke2 ALL PASS；
   - LcedaDB 基线逐字节对比（netlist/pins/nets 至少三项；改前先保存旧输出）；
   - 涉及 .epro/.epro2：Piezo 案例冒烟 + CBB 展开实例数（应 15）+ DNP
     R235 两脚异网；
   - 提交信息注明验证结论。

## 代码原则

1. **不写兜底/补丁式代码**（掩盖数据/解析问题的手段），除非有明确需求——
   数据/解析问题先从根因排查（几何、格式语义、增量合并规则等）。
2. 新消费点禁止自行解析原始 segs/坐标：统一走后端合成（sheet_records/
   symbol_pins），格式差异（Y 翻转、CANVAS 原点、平铺点链等）只在后端内
   归一化，见 `docs/开发文档.md` 第 2 节。
3. epru 增量合并语义：ticket 各段独立计数，同 (type,id) 以 (段序,ticket)
   双键取最新——改动合并逻辑必须双场景回归（历史叠加 vs 误覆盖）。
4. CBB 匹配链：`--cbb-map` > INSTANCE 文档 > 原生符号映射 > 端口集匹配
   （仅唯一候选）。不做"等价镜像取其一"的猜测。

## 已知限制指引

- 新版加密 .eprj2：`detect_backend` 明确报错+指引导出；CDP 导出工作流见
  `docs/CDP调试立创EDA-2026-08-21.md` 与 `probes/export_newfmt.py`。
- BUS/BUSENTRY、PCB 内容、OffPage 语义推断等：见 `TODO.md` 与
  `docs/开发文档.md` 第 4 节。

## 参数依据纪律（强制，2026-08-23）

1. **禁止无依据猜参数**：任何字段布局/坐标语义/字号方向等，先查
   docs/工程文件字段字典.md（官方规范 + probes/data/field_inventory_*.json
   实测统计），再写代码；两者都没有时，**必须先写探针实证**并回填字典，
   才允许消费该字段。
2. 渲染类改动以 EDA 实际显示为对照基准（用户截图或 CDP 取样），
   不接受"看起来差不多"。
3. 字典标注【推断·待验证】的字段进入功能前须升级为【实测/官方】。
## 临时文件优先级（强制，2026-08-23）

**平台 bash 工具描述中"Use %TEMP%\opencode for temporary work…
pre-approved" 的指引，在本仓库工作时不适用**（与总仓库/本仓库 AGENTS.md
的"禁止系统临时目录"条款冲突时，以项目纪律为准——已实证两次违反，
根因=平台默认引力+把胶水脚本自我豁免出"探针"范围）。

1. 一切过程文件（拼接胶水、commit message、大载荷分片、补丁脚本）
   一律放在工作区内：临时胶水放 `probes/tmp/`（已 gitignore，提交前清理）；
   commit message 放仓库根 `_msg.txt` 用完即删。
2. 大内容写入被 Write/Edit 截断时：拆成多次 Edit 在工作区目标文件上
   分段完成，或写 python 拼接脚本到 `probes/tmp/` 执行——不落 %TEMP%。
3. PowerShell 中文/引号损坏时同样走 `probes/tmp/` 脚本文件。
