"""总线 BUS/BUSENTRY 支持回归（2026-09-03）。

覆盖三层：
1. expand_bus_net 纯函数（单段/多段/降序/越界/非总线名）；
2. parse_sheet 合成用例：入口点命中的无名分支按 order 推断命名，
   有名分支不改名，sheet["buses"] 组信息完整；
3. 真实样本（若存在）：CDP 自建总线工程（见
   docs/总线BUS-BUSENTRY格式与实现-2026-09-03.md），解密后校验
   BUSENTRY 行与网络集合。

用法: python probes/verify_bus.py [--eprj <含总线的工程路径>]
"""
import io
import json
import os
import sys

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import lceda_reader as lr

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"  OK  {name}")
    else:
        FAILS.append(name)
        print(f"  FAIL {name} {detail}")


def test_expand():
    print("[1] expand_bus_net")
    cases = [
        ("D[0:7]", 0, "D0"), ("D[0:7]", 3, "D3"), ("D[0:7]", 7, "D7"),
        ("D[0:7]", 8, None),
        ("A[2:3]B[7:6]", 0, "A2B7"), ("A[2:3]B[7:6]", 1, "A2B6"),
        ("A[2:3]B[7:6]", 2, "A3B7"), ("A[2:3]B[7:6]", 3, "A3B6"),
        ("DATA[0:15]", 15, "DATA15"),
        ("PLAIN", 0, None), ("", 0, None),
    ]
    for name, order, want in cases:
        got = lr.expand_bus_net(name, order)
        check(f"{name}[{order}] == {want!r}", got == want, f"got {got!r}")


class FakeDB:
    def __init__(self, recs):
        self.recs = recs

    def sheet_records(self, key):
        return self.recs


def test_parse_sheet():
    print("[2] parse_sheet 合成用例")
    db = FakeDB([
        ["COMPONENT", "e1", "TB", 0, 0, 0, 0, {}, 0],
        ["WIRE", "bus1", [[400.0, 400.0, 700.0, 400.0]]],
        ["ATTR", "a1", "bus1", "NET", "D[0:7]"],
        # 无名分支（入口 order2）→ 推断 D2
        ["WIRE", "br2", [[550.0, 350.0, 550.0, 390.0]]],
        ["BUSENTRY", "e_2", "bus1", 2, 550.0, 390.0, 90],
        # 有名分支（入口 order3，NET=D9 显式名）→ 不改名、仅组归属
        ["WIRE", "br3", [[600.0, 350.0, 600.0, 390.0]]],
        ["ATTR", "a3", "br3", "NET", "D9"],
        ["BUSENTRY", "e_3", "bus1", 3, 600.0, 390.0, 90],
    ])
    sheet = lr.parse_sheet(db, "p1")
    nets = {n["net"] for n in sheet["nets"] if n["net"]}
    check("无名分支推断为 D2", "D2" in nets, f"nets={nets}")
    check("有名分支保持 D9", "D9" in nets and "D3" not in nets,
          f"nets={nets}")
    buses = sheet.get("buses") or {}
    check("buses 组信息", buses.get("bus1", {}).get("net") == "D[0:7]"
          and len(buses.get("bus1", {}).get("entries", [])) == 2,
          f"buses={buses}")


def test_real(path):
    print("[3] 真实总线样本")
    out = lr._decrypt_new_eprj2(path)
    db = lr.Epro2DB(out)
    # 找含 BUSENTRY 的页
    hit = None
    for uuid, title, _sch, _dt in db.sheets():
        recs = db.sheet_records(uuid) or []
        if any(isinstance(r, list) and r[:1] == ["BUSENTRY"] for r in recs):
            hit = uuid
            sheet = lr.parse_sheet(db, uuid)
            break
    if hit is None:
        check("样本含 BUSENTRY 页", False, "未找到（先跑 CDP 建总线样本）")
        return
    n_entries = sum(len(b["entries"]) for b in sheet["buses"].values())
    check(f"BUSENTRY 解析（{len(sheet['buses'])} 组 / {n_entries} 入口）",
          n_entries > 0)
    named = {n["net"] for n in sheet["nets"] if n["net"]}
    check("总线组名在 nets 中",
          any(b["net"] in named for b in sheet["buses"].values()),
          f"nets={sorted(named)[:8]}")


def main():
    test_expand()
    test_parse_sheet()
    path = None
    args = sys.argv[1:]
    if "--eprj" in args:
        path = args[args.index("--eprj") + 1]
    else:
        default = (r"C:\Users\dell\Documents\LCEDA-Pro\projects"
                   r"\CDP探针-临时工程.eprj2")
        path = default if os.path.exists(default) else None
    if path:
        test_real(path)
    else:
        print("[3] 真实样本：未提供 --eprj，跳过")
    print("=" * 50)
    print("ALL PASS" if not FAILS else f"FAILED: {FAILS}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
