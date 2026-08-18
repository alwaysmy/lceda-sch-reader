# TODO

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