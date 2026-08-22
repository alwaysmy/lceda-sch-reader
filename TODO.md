# TODO

## 新格式 .eprj2（分支版本化，加密）支持（✅ 已完成）

- **2026-08-22 破解完成**：`detect_backend` 自动检测新版格式并调用
  `_decrypt_new_eprj2()` 解密 → 临时 .epro2 → Epro2DB 读取，对用户
  完全透明。算法：AES-128-GCM(key=project_history_<branch>.key,
  iv=history_data.uuid) → gzip 解压 → V3 epru 明文。
  详细逆向过程与算法见 `docs/新版eprj2格式逆向与破解.md`。
- CDP 导出路径（probes/export_newfmt.py）仍保留作为备选方案，
  可获取 INSTANCE 段的母图位号映射（直接解密路径暂不含此数据）。

## PCB 解析（✅ 三后端完成 2026-08-23）

- **已完成**：`pcb_inventory()` 解析 COMPONENT/ATTR/NET/PAD_NET；`pcbsch`
  命令以 COMPONENT 内联 "Unique ID"(ggeN) 为 SCH↔PCB 全局映射键。
  - LcedaDB：documents.docType=3
  - EproDB：ZIP `PCB/<uuid>.epcb`（与 SQLite V2 布局一致）
  - Epro2DB：docType=="PCB" epru → V2 布局转换
  实测涡流 V1.0 主板 PCB1 265 元件一致 263/改名 2；epro Piezo 581 元件
  板级文档 15 个全枚举；跨格式 UID 稳定（epro2 备份 PCB2 与 SQLite 同步）。
- **待做**：PCB 网络拓扑级审查（PCB 网络表 vs SCH 网络表逐 pin 对比，
  需解析 PAD 几何/Footprint 引脚位置，当前仅 PAD_NET 归属清单）。

## 渲染 render（✅ 基础完成 2026-08-23）

- SVG 输出：导线/结点/网络名、符号图形原语(POLY/RECT/CIRCLE/ARC 三点弧)、
  引脚桩+NC 叉、位号/值（FONTSTYLE 字号 + ATTR 显示坐标=EDA 排版）、
  DNP 标记、页文本。配置：render_config.json 自动加载 / --config /
  --no-labels/--no-texts/--pin-numbers。
- **待做**：图纸边框区域裁剪（标题块外留白过大）；NetFlag 符号文字
  （VCC/GND 名在符号 TEXT 里已画但字号小）；多页批量渲染；PDF 出图。

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

- Sheet Symbol(20) 图纸重用、VARIANT/INSTANCE/元件分组：v3 规范概念，
  v2 数组格式文件无对应数据。