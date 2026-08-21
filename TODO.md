# TODO

## 新格式 .eprj2（分支版本化，加密）支持（已破解导出路径）

- **现状（2026-08-21）**：新版立创EDA .eprj2 的 `history_data` 为加密 blob
  （熵 8.00，排除 raw-deflate/zlib/gzip；主进程 app.js 无解密代码，解密在
  渲染层 pro-ui 混淆包内）——**静态解析不可行**。工具打开此类文件会明确
  报错并指引导出。
- **已实现的破解导出路径（probes/export_newfmt.py）**：经 CDP
  （`lceda-pro.exe --remote-debugging-port=9222 <工程>`）进入编辑器渲染层，
  利用内存中的解密后文档：`SCH.docMemoryManager.getOrInitDoc(uuid)` 加载 →
  `consistencyImpl.getSourceCode()` 取**明文 epru**（与 .epro2 文本格式
  一致）；SYMBOL 同理；DEVICE 用 componentCache.device[k].deviceResult 合成
  META；BOARD/SCH/PCB 层级从 .eprj2 明文 `project_structures.structure`
  合成；INSTANCE 段从 instanceAttrMgr.savedData 合成。打包为标准 .epro2
  （`<名>_export.epro2`），**全工具可用**（Piezo 实测：73 页+224 符号+
  213 器件，netlist 267 网、CBB 15 实例展开、tree 层级完整）。
- **标准工作流**：新版 .eprj2 → 打开 LCEDA（半离线即可）→ 运行
  export_newfmt.py → 用导出的 _export.epro2 分析。
- **遗留**：导出依赖编辑器内存缓存（componentCache），未打开过的符号子集
  可能缺失（实测 224/226 已覆盖）；INSTANCE 段来自 instanceAttrMgr
  （仅记录改名成员）。

## BUS / BUSENTRY 总线支持（未实施）

- **状态**：暂不做。等用户提供一个用到总线的工程例子后再实施。
- **背景**：规范（`reference/lceda-pro-file-format-v3_2025.10.21.md`）定义
  BUS（总线，网络名如 `A[1:5]`）+ BUSENTRY（总线接入标识，`busGroupId`
  顺序编号 + `order` 分支展开）。当前工程（涡流传感器 V1.0）未用总线，
  工具对总线网络名展开与分支映射（BUSENTRY 顺序编号 → 具体网络，如
  `A[2:3]B[7:6]` 0/1/2/3 顺序 → A2B7/A2B6/A3B7/A3B6）不支持：
  - 总线网络名（`A[1:5]`）不会被解析为具体网络；
  - BUSENTRY 接入的 WIRE 网络归属（总线分支 → 单线网络）缺失；
  - 影响：含总线的工程网络解析会漏网络/断链。
- **实施方案（预期）**：
  1. `parse_sheet` 解析 BUS 记录（dots + NET 属性）与 BUSENTRY（pointX/Y、
     rotation、busGroupId、order）；
  2. 按规范语义展开总线网络：BUS 网络名含 `[m:n]` 段时，BUSENTRY 的
     `busGroupId`/`order` 组合（多段总线是笛卡尔积）映射到具体网络名
     （如 `A[2:3]B[7:6]` + busGroupId 0..3 → A2B7/A2B6/A3B7/A3B6）；
  3. BUSENTRY 端点接入的 WIRE 端点赋该具体网络名，进入既有连通域解析。
- **触发条件**：用户提供一个含总线的工程文件（.eprj2）作为验证样例。

## 其他未支持（记录，暂不做）

- PCB 文档（docType=3）解析：NET/PAD/VIA/CONNECT——工具定位为原理图
  读取工具，无 PCB 命令。
- Sheet Symbol(20) 图纸重用、VARIANT/INSTANCE/元件分组：v3 规范概念，
  v2 数组格式文件无对应数据。