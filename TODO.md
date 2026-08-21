# TODO

## 新格式 .eprj2（分支版本化，加密）支持（未实施）

- **状态**：暂不做。2026-08-21 发现新版立创EDA 保存的 .eprj2 采用新存储格式：
  `documents`/`schematics` 等主表为空，内容在 `history_data`（base64 + 加密，
  香农熵 8.00 bits/byte，已排除 raw-deflate/zlib/gzip），工程树在
  `project_structures.structure`（明文 JSON：boards/schematics/sheets/pcbs/
  blockSymbols）。branches/projects 行含 branch_uuid。
- **影响**：detect_backend 已识别并**明确报错 + 指引导出 .epro/.epro2**
  （不再静默空结果）。
- **可读部分**：structure 明文——已用于 CBB 块符号映射。
- **逆向侦察结论（2026-08-21）**：LCEDA 安装目录
  `C:\Program Files\lceda-pro\resources\app`（Electron，非 asar 打包）；
  主进程 app.js 含 history_data 建表语句但**无解密代码**；加密/解密逻辑在
  渲染层 `assets/pro-ui/<版本>/js/ui.js`（17MB webpack 混淆包）中，静态
  分析成本高。**可行路径 = CDP 动态分析**：以
  `--remote-debugging-port=9222` 启动立创EDA → CDP 连接后 hook
  WebCrypto(subtle.decrypt)/自定义解密函数或直接读取编辑器内存中的文档
  JSON。需要现场配合（打开目标工程），作为独立任务规划。
- **触发条件**：用户需要直接读新版 .eprj2 且接受 CDP 动态方案时启动；
  当前以"导出 .epro/.epro2"为标准工作流替代。

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