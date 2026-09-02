# TODO

> 审查工具整体设计方向见 `docs/审查工具设计启发.md`
> （九条原则 + 板关联三级置信度 + 配置分层 + openlceda 愿景 +
> 审查点清单 + 架构约束，2026-08-24 复盘沉淀）。

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

## 渲染 render（✅ 基础完成 2026-08-23，含 Y 向上修正）

- SVG 输出：导线/结点/网络名、符号图形原语(POLY/RECT/CIRCLE/ARC 三点弧/
  **符号内 TEXT**)、引脚桩+NC 叉、位号/值/@标题块（FONTSTYLE 字号 +
  ATTR 显示坐标 + 模板覆盖机制=EDA 排版）、DNP 标记、页文本。
  **文件坐标系 Y 向上**（渲染统一翻转，实证：标题栏右下）。
  配置：render_config.json / --config / --no-labels/--no-texts/
  --pin-numbers。多格式冒烟 7/7 PASS（eprj2/epro/epro2）。
- **待做**：Epro2DB.symbol_records（V3 符号图形转换，当前 V3 页器件退化为
  占位框）；图纸边框区域裁剪；多页批量渲染；PDF 出图；
  PIN a[3] 电气特性回退 symbol_pins.pin_type。

## BUS / BUSENTRY 总线支持（✅ Epro2DB 完成 2026-09-03）

- **2026-09-03 完成**：验证样例不再依赖用户提供——用 CDP 驱动官方 API
  自建总线工程（D[0:7] + 4 入口 + 分支 + 电阻），格式逆向后实现：
  - Epro2DB：BUS 记录（busEntry 嵌在记录体内）→ 合成 BUSENTRY 数组；
  - parse_sheet：入口点命中分支导线端点时，无名分支按 order 展开组名
    推断命名（expand_bus_net），有名分支只记录组归属（总线是编组，
    不做域合并）；
  - sheet["buses"] 输出总线组信息；raw 命令可见 BUSENTRY 行。
  格式细节与验证结论见 `docs/总线BUS-BUSENTRY格式与实现-2026-09-03.md`。
- **待做**：多段组名（A[2:3]B[7:6] 顺序语义）真实样本复核；
  netlist 人类可读行的组归属标注；LcedaDB/EproDB 原生 BUSENTRY 数组
  （出现真实样本时接入，语义同 Epro2DB 路径）。

## 其他未支持（记录，暂不做）

- PANEL/拼版（立创EDA 面板设计功能，structure.panels / project.json
  panels 键）：**不属于原理图审查范围，暂不处理**；openlceda 或 PCB
  级审查时可能用上（2026-08-24 用户标记）。
- Sheet Symbol(20) 图纸重用、VARIANT/INSTANCE/元件分组：v3 规范概念，
  v2 数组格式文件无对应数据。