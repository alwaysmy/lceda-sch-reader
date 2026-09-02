# 总线 BUS/BUSENTRY 格式与工具实现（2026-09-03）

> 遗留问题攻关：TODO.md"BUS/BUSENTRY 总线支持"所需验证样例由本工具团队
> 自建（CDP 驱动官方 API 绘制），格式逆向 + 实现一次完成。
> 样本：`Documents\LCEDA-Pro\projects\CDP探针-临时工程.eprj2` →
> Schematic2::P1 页（总线 D[0:7] + 4 入口 + 4 分支 + 2 电阻 + L 形导线）。

## 一、V3 实测格式（.epro2 / 解密后 epru）

V3 增量日志中总线相关记录为三类分离：

```
{"type":"BUS","ticket":35,"id":"227ce3f91085e074"}||
  {"busEntry":{
     "71b30c7cfc539405":{"order":0,"pointX":450,"pointY":-390,"rotation":90,"zIndex":4},
     "4e575873d7f7e9b5":{"order":1,"pointX":500,"pointY":-390,"rotation":90,"zIndex":6},
     ...},
   "zIndex":1}|

{"type":"LINE","ticket":36,"id":"ca20e8c8b69639df"}||
  {...,"startX":700,"startY":-400,"endX":400,"endY":-400,"lineGroup":"227ce3f91085e074"}|

{"type":"WIRE","ticket":38,"id":"9b498dfd4f024d75"}||{"zIndex":3}|
{"type":"ATTR","ticket":37,"id":"c20ba9ad9a77d04d"}||{"parentId":"227ce3f91085e074",
  "key":"NET","value":"D[0:7]",...}|
```

关键事实（全部实测）：

1. **BUS 记录**：总线组实体；`busEntry` 嵌在 BUS 记录体内（**不是**
   独立 BUSENTRY 行）。每个入口 `{order, pointX, pointY, rotation, zIndex}`，
   同一 ticket 段内全量快照、新 ticket 段整体覆盖（增量合并按既有规则）。
2. **图形几何在 LINE**：`lineGroup` = 归属记录 id。总线 LINE 的
   lineGroup=BUS id；分支导线 LINE 的 lineGroup=各 WIRE id。
   Epro2DB 既有转换已把 LINE 聚合为 WIRE.dots——BUS 的 LINE 也因此
   生成了同 id 的 WIRE 记录（旧版转换因此"看起来像导线"）。
3. **总线组名 = NET 属性**挂在 BUS id 上（如 `D[0:7]`），归属规则与
   普通导线一致。
4. **坐标 Y 取反**：V3 内部 pointY/startY 为负（Y 向上），转换时同既有
   规则 `-((y)-oy)`。
5. **入口几何**：`pointX/pointY` 是**分支导线一侧端点**（导线被自动
   修剪到距总线 10 单位处，`busEntryLength=10`），stub 另一端落在总线
   线上。rotation=90 实测对应"stub 从入口点指向 +Y（文件坐标向下）"。
6. **order**：同组内入口顺序号（0 起），用于组名→具体网络名展开。

## 二、编辑器行为（CDP 活模型实测）

- 用导线工具从总线中段拉线：**自动生成 BusEntry**（netPolymerization 引擎
  `busEntryConnectionTool`），wire 端点自动修剪、NET 自动按组名+order
  展开（如 order 3 → `D3`）。已命名的普通导线接到总线分支也按同名合并。
- API（`sch_PrimitiveWire.create`）建的导线**端点落在总线线上**时不产生
  入口（直连）；落在距总线 10 单位处时同样由引擎补生成入口。
- 引擎生成的 BusEntry 只存在于活模型；**只有用户动作（如画线）触发的
  事务上传才会把 BUS/busEntry 写进文件**（上传走模型命令通道，
  `uploadImpl._handleModelCommand`——内部重构不触发，见 CDP 文档坑 9）。

## 三、工具实现（2026-09-03）

### Epro2DB.sheet_records

- 新增 `BUS` 记录处理：发射合成数组
  `["BUSENTRY", eid, bus_wire_id, order, x, y, rot]`（坐标已按 V2 语义
  减原点+Y 翻转），追加在 TEXT 之后。
- 总线图形仍由其 LINE 聚合为同 id WIRE 记录（NET=组名），无需特判。

### parse_sheet

- 消费 BUSENTRY：入口点命中某分支导线端点时——
  - 分支**无**网络名 → `net_of[wid] = expand_bus_net(组名, order)`
    （推断命名，标进 sheet["nets"]）；
  - 分支有名 → 只记录组归属，**不改名**（总线是编组不是电气连接，
    D0/D1 不因总线互连——这是网络语义，不做域合并）。
- `sheet["buses"] = {bus_id: {"net": 组名, "entries":[{order,eid,point}]}}`。

### expand_bus_net(组名, order)

- 单段 `D[0:7]`：order k → `D_k`（实测）。
- 多段 `A[2:3]B[7:6]`：order 0/1/2/3 → `A2B7/A2B6/A3B7/A3B6`
  （最后一段最快、各段按书写顺序，含降序）——TODO.md 预期语义，
  待真实多段样本复核（触发条件同前）。
- 越界/无段名返回 None（不猜）。

### 验证

- expand_bus_net 单测 11 例 ALL PASS（含越界/纯文本名/降序多段）。
- 合成用例：无名分支 + 入口 order2 → 推断为 D2，PASS。
- 自建总线样本端到端：BUSENTRY×4 + buses 组信息 + 全部网络
  （D0/D1/D2/D3/D[0:7]）解析正确。
- 全盘回归：smoke2 ALL PASS；verify_all_formats 7 工程 PASS +
  跨格式网络集合零差异。

## 四、遗留

- `netfind/trace` 的 pin 级遍历天然支持总线网络（分支有名后与普通
  网络无差别）；总线组归属尚未输出到 netlist 人类可读行（--json 的
  sheet.buses 已含），需要时再加。
- LcedaDB（V2.2 SQLite）与 EproDB 的原生 BUSENTRY 数组记录
  （`["BUSENTRY", id, busGroupId, order, pointX, pointY, rotation, ...]`，
  见编辑器 parseBusEntry 反解）未实现——本机无样本文件，出现真实
  工程时按同一语义接入。
- API 放置的元件无 Designator 属性（EDA 由标注/重编号流程生成），
  `components` 输出会跳过——建议用 UI 编号或手动补属性后使用。
