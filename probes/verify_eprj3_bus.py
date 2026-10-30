"""回归：.eprj3 BUS / BUSENTRY 合成样本。

官方 V4 与 V3 同语义：BUS.busEntry 是嵌在 BUS body 里的入口表，
bus id 同时是总线 LINE 的 lineGroup，ATTR NET（如 BUS[0:5]）命名总线。
本回归用最小合成页验证 Eprj3DB 至少能把这些记录转成统一模型：
  1. sheet_records 产出总线 WIRE 和 BUSENTRY；
  2. parse_sheet 建立 buses，并把入口处无名分支线展开成 BUS0。

没有真实 BUS 工程样本，故用合成记录覆盖格式路径；拿到客户端导出的
真实 BUS 页后应再用真实工程替换/补充本回归。
用法：python probes/verify_eprj3_bus.py
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import lceda_reader as L  # noqa: E402

TMP = os.path.join(HERE, "tmp", "eprj3_bus_fixture")
FAILS = []


def check(name, cond, detail=""):
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name,
                           ("  -- " + detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def line(typ, body, ticket, rid=None):
    head = {"type": typ, "ticket": ticket}
    if rid is not None:
        head["id"] = rid
    return (json.dumps(head, separators=(",", ":")) + "||" +
            json.dumps(body, separators=(",", ":")) + "|\n")


def build():
    shutil.rmtree(TMP, ignore_errors=True)
    d = os.path.join(TMP, "sch", "Board")
    os.makedirs(d)
    rows = [
        line("DOCHEAD", {"docType": "SCH_PAGE", "uuid": "page1",
                         "client": "0000000000000001",
                         "updateTime": 1, "version": "1"}, 1),
        line("META", {"title": "P1", "docType": 1}, 2, "META"),
        line("CANVAS", {"originX": 0, "originY": 0}, 1, "CANVAS"),
        line("BUS", {"busEntry": {"e1": {"order": 0, "pointX": 10,
                                         "pointY": 0, "rotation": 0}}},
             3, "b1"),
        line("LINE", {"lineGroup": "b1", "startX": 0, "startY": 0,
                      "endX": 20, "endY": 0}, 4, "l1"),
        line("ATTR", {"key": "NET", "value": "BUS[0:5]",
                      "parentId": "b1"}, 5, "a1"),
        line("WIRE", {}, 6, "w1"),
        line("LINE", {"lineGroup": "w1", "startX": 10, "startY": 0,
                      "endX": 10, "endY": 10}, 7, "l2"),
    ]
    with open(os.path.join(d, "P1.esch2"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.writelines(rows)


def main():
    build()
    try:
        db = L.Eprj3DB(TMP)
        recs = db.sheet_records("page1") or []
        wire = next((r for r in recs if r[0] == "WIRE" and r[1] == "b1"), None)
        be = next((r for r in recs if r[0] == "BUSENTRY"), None)
        check("sheet_records 产出总线 WIRE", wire is not None and wire[2],
              str(wire))
        check("sheet_records 产出 BUSENTRY", be is not None, str(be))
        sh = L.parse_sheet(db, "page1") or {}
        check("parse_sheet 建立 buses",
              (sh.get("buses") or {}).get("b1", {}).get("net") == "BUS[0:5]",
              str(sh.get("buses")))
        check("入口分支线展开为 BUS0",
              any(n.get("net") == "BUS0" for n in sh.get("nets") or []),
              str(sh.get("nets")))
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print()
    print("ALL: %s" % ("PASS" if not FAILS else "FAIL(%d)" % len(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
