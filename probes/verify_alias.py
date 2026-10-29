# -*- coding: utf-8 -*-
"""网络别名回归（AGENTS.md 测试规则：脚本入 probes/）。

覆盖两件事：
1. 纯函数：别名闭包的传递性、主名选择、文本后缀；
2. 端到端：同一物理网络的多个名字，netfind 必须返回**同一组**连接点，
   且 netlist 里只占**一行**（不再拆成互不包含的多行）。

默认工程 = 仓库 ../examples/涡流传感器.eprj2（含 +3.3V/D3V3、H_RESET/RST 两组别名），
可用环境变量 LCEDA_EPRJ 覆盖。
"""
import io
import json
import os
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import lceda_reader as lr

env = os.environ.get("LCEDA_EPRJ")
DEFAULT = os.path.normpath(os.path.join(ROOT, "..", "examples", "涡流传感器.eprj2"))
EPRJ = env or DEFAULT

ok = True


def check(cond, msg):
    global ok
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        ok = False


print("[1] 别名闭包 / 主名 / 后缀")
root_of, groups = lr.build_alias_groups(["A" + lr.NET_SEP + "B", "B" + lr.NET_SEP + "C"])
all_names = set().union(*groups.values())
check(all_names == {"A", "B", "C"}, f"传递闭包 A-B, B-C -> {sorted(all_names)}")
check(len({root_of[n] for n in ("A", "B", "C")}) == 1, "三个名字同属一组")
root2, _g2 = lr.build_alias_groups(["X", "Y"])
check(root2["X"] != root2["Y"], "无共现的名字不合并")
check(lr.pick_primary_name(["PD5", "USART2_TX"]) == "USART2_TX",
      "非引脚自动名优先")
check(lr.pick_primary_name(["GND", "AGND"], {"GND": 100, "AGND": 2}) == "GND",
      "同名条件下引脚多者优先")
check(lr.alias_suffix(["ID_OUT", "USART2_TX"], "ID_OUT") == "（别名: USART2_TX）",
      "别名后缀只列其它名字")
check(lr.alias_suffix(["ID_OUT"], "ID_OUT") == "", "无别名时无后缀")

# 引脚自动名判定边界：只认"整串 = 1~3 字母 + 1~3 数字"
check(lr._is_pin_like_name("PD6") is True, "PD6 -> 引脚自动名")
check(lr._is_pin_like_name("PA11") is True, "PA11 -> 引脚自动名")
check(lr._is_pin_like_name("PD6_UART_TX1") is False,
      "PD6_UART_TX1 带后缀 -> 不是引脚自动名")
check(lr._is_pin_like_name("PD1234") is False, "PD1234 四位数字 -> 不是引脚自动名")
check(lr._is_pin_like_name("GPIOA1") is False, "GPIOA1 四字母 -> 不是引脚自动名")
check(lr.pick_primary_name(["PD6", "PD6_UART_TX1"]) == "PD6_UART_TX1",
      "PD6_UART_TX1 优先于 PD6 作显示主名")
check(lr.pick_primary_name(["CS1", "SPI_CS"]) == "SPI_CS",
      "CS1 形似引脚名 -> 显示时让位于 SPI_CS（仅显示，不影响查询）")
_roots3, _groups3 = lr.build_alias_groups(["PD6" + lr.NET_SEP + "PD6_UART_TX1"])
check(set(list(_groups3.values())[0]) == {"PD6", "PD6_UART_TX1"},
      "主名选择不丢名字（别名组保留全部）")

print("[2] 端到端：同一网络的多个名字 -> 同一组连接点 / 单行")
if not os.path.isfile(EPRJ):
    print(f"  工程不存在: {EPRJ}（可用 LCEDA_EPRJ 覆盖）")
    print("ALL: FAIL")
    sys.exit(1)
print(f"  工程: {EPRJ}")
res = lr.detect_backend(EPRJ)
db = res(EPRJ) if res != "DECRYPT_NEW" else lr.Epro2DB(lr._decrypt_new_eprj2(EPRJ))

# 从 netlist 视角找出至少一组别名
rows = []
for uuid, title, sch, dt in db.sheets():
    if dt != 1:
        continue
    sh = lr.parse_sheet(db, uuid)
    if not sh:
        continue
    pinc = lr._collect_pinmap_data(db, sh, uuid)
    if not pinc:
        continue
    cp, ws, pw, ep = pinc
    dom = lr.resolve_nets_by_domain(db, sh, cp, ws, pw, ep)
    for (des, pin), net in dom.items():
        rows.append((title, des, pin, net))
root_of, groups = lr.build_alias_groups(n for _t, _d, _p, n in rows)
multi = [names for names in groups.values() if len(names) > 1]
check(bool(multi), f"工程里存在别名组（{len(multi)} 组）")

if multi:
    names = sorted(multi[0])
    sets = {}
    for n in names:
        r, got = lr._netfind_one(db, n)
        sets[n] = {(x["sheet"], x["designator"], str(x["pin"])) for x in r}
        check(sorted(set(got)) == names,
              f"netfind {n} 报出整组名字 {names}")
    base = sets[names[0]]
    check(all(v == base for v in sets.values()),
          f"各别名返回同一组连接点（{len(base)} 个）")
    check(len(base) > 0, "该组连接点非空")

    # netlist 单行：按别名组聚合后，同一组不应出现在两行
    grouped = {}
    for title, des, pin, net in rows:
        key = tuple(sorted({t for t in lr.net_tokens(net)}))
        grouped.setdefault(key, set()).add((title, des, pin))
    reps = [k for k in grouped if len(k) > 1]
    check(len(reps) == len({root_of.get(k[0], k[0]) for k in reps}),
          "多个名字的域合并为同一聚合键（无重复行）")

print("[3] pinmap：全局别名 + 跨页标注")
if multi:
    names = sorted(multi[0])
    rows_nf, _names = lr._netfind_one(db, names[0])
    pages = sorted({r["sheet"] for r in rows_nf})
    if rows_nf:
        pins = []
        for tgt in rows_nf:
            proc = subprocess.run(
                [sys.executable, os.path.join(ROOT, "lceda_reader.py"),
                 "--eprj", EPRJ, "--json", "pinmap", tgt["sheet"],
                 "--designator", tgt["designator"],
                 "--schematic", tgt["schematic"]],
                capture_output=True, text=True, encoding="utf-8",
                env=dict(os.environ, PYTHONIOENCODING="utf-8",
                         PYTHONUTF8="1"),
                cwd=ROOT)
            try:
                cand = json.loads(proc.stdout)[0]["pins"]
            except (ValueError, IndexError, KeyError):
                continue
            hit = [p for p in cand
                   if p.get("aliases") and set(p["aliases"]) >= set(names)]
            if hit:
                pins = hit
                break
        check(bool(pins), f"pinmap 引脚带全组别名 {names}")
        if pins:
            check(set(pins[0].get("net_sheets") or []) == set(pages),
                  f"pinmap 跨页标注与 netfind 页集合一致（{len(pages)} 页）")
            check(len(pins[0]["aliases"]) > 1, "aliases 为多名字")
            check(bool(pins[0].get("resolved_nets")), "resolved_nets 非空")

db.close()
print("ALL: " + ("PASS" if ok else "FAIL"))
sys.exit(0 if ok else 1)
