"""回归：.eprj3 空 body 墓碑与 DELETE_DOC。

官方规则：删除一条原子数据 = 再写一行、body 为空；删除文档 =
DELETE_DOC{isDelete:true}。这里用最小合成工程验证四个曾经的缺口：
  1. PIN 墓碑不再生成 (0,0) 幽灵引脚；
  2. WIRE 墓碑不再声明导线组，孤儿 LINE 不会复活；
  3. COMPONENT 墓碑不再生成幽灵元件；
  4. DELETE_DOC 的文档不出现在 sheets() 中。

合成工程写在 probes/tmp/ 下（gitignore，不进入仓库），运行结束清理。
用法：python probes/verify_eprj3_tombstone.py
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import lceda_reader as L  # noqa: E402

TMP = os.path.join(HERE, "tmp", "eprj3_tombstone_fixture")
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
    h = json.dumps(head, separators=(",", ":"))
    if body is None:                 # 官方墓碑：head + || + |
        return h + "|||\n"
    return h + "||" + json.dumps(body, ensure_ascii=False,
                                 separators=(",", ":")) + "|\n"


def build():
    shutil.rmtree(TMP, ignore_errors=True)
    d = os.path.join(TMP, "sch", "Board")
    os.makedirs(d)
    path = os.path.join(d, "P1.esch2")
    rows = []
    # SYMBOL：PART + PIN pin1，随后 pin1 被空 body 删除。
    rows.append(line("DOCHEAD", {"docType": "SYMBOL", "uuid": "sym1",
                                 "client": "0000000000000001",
                                 "updateTime": 1, "version": "1"}, 1))
    rows.append(line("META", {"title": "T", "docType": 2,
                              "attributes": {}}, 2, "META"))
    rows.append(line("CANVAS", {"originX": 0, "originY": 0}, 1, "CANVAS"))
    rows.append(line("PART", {"BBOX": [-10, -10, 10, 10], "title": "p1"},
                     3, "p1"))
    rows.append(line("PIN", {"partId": "p1", "x": 0, "y": 0,
                             "length": 10, "rotation": 0}, 4, "pin1"))
    rows.append(line("ATTR", {"key": "Pin Name", "value": "A",
                              "parentId": "pin1"}, 5, "a1"))
    rows.append(line("PIN", None, 6, "pin1"))       # 墓碑

    # SCH_PAGE：正常 R1；R2 随后被删除；WIRE w1 被删除但 LINE l1 仍存活。
    rows.append(line("DOCHEAD", {"docType": "SCH_PAGE", "uuid": "page1",
                                 "client": "0000000000000001",
                                 "updateTime": 2, "version": "2"}, 1))
    rows.append(line("META", {"title": "P1", "docType": 1}, 2, "META"))
    rows.append(line("CANVAS", {"originX": 0, "originY": 0}, 1, "CANVAS"))
    rows.append(line("COMPONENT", {"partId": "p1", "x": 10, "y": 10,
                                   "rotation": 0, "isMirror": False,
                                   "attrs": {}}, 3, "c1"))
    rows.append(line("ATTR", {"key": "Designator", "value": "R1",
                              "parentId": "c1"}, 4, "a-r1"))
    rows.append(line("ATTR", {"key": "Symbol", "value": "sym1",
                              "parentId": "c1"}, 5, "a-sym1"))
    rows.append(line("COMPONENT", {"partId": "p1", "x": 20, "y": 20,
                                   "rotation": 0, "isMirror": False,
                                   "attrs": {}}, 6, "c2"))
    rows.append(line("ATTR", {"key": "Designator", "value": "R2",
                              "parentId": "c2"}, 7, "a-r2"))
    rows.append(line("COMPONENT", None, 8, "c2"))   # 墓碑
    rows.append(line("WIRE", {}, 9, "w1"))
    rows.append(line("LINE", {"lineGroup": "w1", "startX": 10, "startY": 10,
                              "endX": 20, "endY": 10}, 10, "l1"))
    rows.append(line("WIRE", None, 11, "w1"))       # 墓碑，LINE 仍存活

    # 被整文档删除的页：不应出现在 sheets()。
    rows.append(line("DOCHEAD", {"docType": "SCH_PAGE", "uuid": "del1",
                                 "client": "0000000000000001",
                                 "updateTime": 3, "version": "3"}, 1))
    rows.append(line("META", {"title": "Deleted", "docType": 1}, 2, "META"))
    rows.append(line("DELETE_DOC", {"isDelete": True}, 3))

    # 先删后撤销：更高 ticket 的 isDelete=false 应让文档保留。
    rows.append(line("DOCHEAD", {"docType": "SCH_PAGE", "uuid": "revive1",
                                 "client": "0000000000000001",
                                 "updateTime": 4, "version": "4"}, 1))
    rows.append(line("META", {"title": "Revived", "docType": 1}, 2, "META"))
    rows.append(line("DELETE_DOC", {"isDelete": True}, 3))
    rows.append(line("DELETE_DOC", {"isDelete": False}, 4))

    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.writelines(rows)


def main():
    build()
    try:
        db = L.Eprj3DB(TMP)
        sp = db.symbol_pins("sym1")
        check("PIN 墓碑不生成幽灵引脚", sp["pins"] == [], str(sp["pins"]))
        check("已删元件 R2 不出现",
              [c.get("designator") for c in
               (L.parse_sheet(db, "page1") or {}).get("components", [])] == ["R1"])
        recs = db.sheet_records("page1") or []
        check("WIRE 墓碑不复活孤儿 LINE",
              not any(r[0] == "WIRE" for r in recs), str(recs))
        titles = [r[1] for r in db.sheets()]
        check("DELETE_DOC 文档不出现在 sheets()",
              not any("Deleted" in t for t in titles), str(titles))
        check("DELETE_DOC isDelete=false 可撤销",
              any("Revived" in t for t in titles), str(titles))
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print()
    print("ALL: %s" % ("PASS" if not FAILS else "FAIL(%d)" % len(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
