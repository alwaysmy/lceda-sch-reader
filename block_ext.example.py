"""块识别 / 公式扩展示例（可选，工具目录放置为 `block_ext.py` 即生效）。

## 用法

把本文件复制/改名为 `block_ext.py` 放到 lceda_sch_reader 工具目录，
`review` 命令启动时会自动 `load_extensions()` 加载。

扩展项在**模块顶层**调用注册函数即可；`source` 由加载器自动标为 `ext:`。

## 契约

识别器：``fn(nb) -> Block | None``

- `nb` 是 `lceda_blocks._NB`（邻域视图），可用方法：
  - `nb.net("OUT"|"IN+"|"IN-"|"V+"|"V-")` → 引脚所在网络键
  - `nb.series_branches(net)` → `[(des, pin, Part, other_net)]`（该网上两脚件）
  - `nb.parts_on(net)` → `[(des, pin, Part)]`
  - `nb.caps_on(net)` / `nb.resistors_on(net)`
  - `nb.g` 是 NetGraph（`net_name` / `net_pins` / `pin_net` / `walk`）
- 返回 `Block(kind, nb.des, nb.g, nb.chan, confidence)`；填 `members` /
  `nets` / `params` / `evidence`。
- **只认高置信度时返回 confidence="high"**；判据不充分请返回 None
  （交给其它识别器或第 2 层网表）——宁可漏报，不可错报。

公式：``fn(block) -> dict``（可算则返回参数；否则 `{}`）

- 从 `block.params` 取值；返回如 `{"fc_hz": ..., "q": ...}`。

## 注意

- `verified` 请如实填写：`VERIFIED_REAL`（真实工程验证）/ 
  `VERIFIED_SYNTH`（仅合成样本）/ `VERIFIED_STUB`（未验证）。
  输出与文档会据此打「未验证」标记——**不要为了好看谎报**。
- 新能力加完请补 `probes/verify_layers.py` 的用例并跑回归。
"""

# 在真实使用时取消下面注释（本示例文件本身不被加载，仅作示范）：
#
# import lceda_blocks as BL
#
#
# def _rec_my_topology(nb):
#     """示例：识别某自定义拓扑，返回 Block 或 None。"""
#     out_net = nb.net("OUT")
#     inn = nb.net("IN-")
#     if not (out_net and inn):
#         return None
#     # ... 你的结构判据（务必只在充分时给 high）...
#     return None
#
#
# def _fml_my_topology(block):
#     """示例：为上面的拓扑写闭式解。"""
#     pr = block.params
#     if not pr.get("r1"):
#         return {}
#     return {"gain": 1.0 / pr["r1"]}
#
#
# BL.register_recognizer("my_topology", _rec_my_topology,
#                        priority=40, verified=BL.VERIFIED_STUB,
#                        note="自定义拓扑（未验证）")
# BL.register_formula("my_topology", _fml_my_topology,
#                     verified=BL.VERIFIED_STUB)


if __name__ == "__main__":
    print(__doc__)
