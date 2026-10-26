"""回归：.eprj3（V4 文件夹工程）后端。

用法：
    set PYTHONIOENCODING=utf-8
    python probes\\verify_eprj3_backend.py [<工程目录或 .eprj3>] [<参考 .epro2>]

工程路径也可用 LCEDA_EPRJ3 / LCEDA_EPRO2 指定。参考 .epro2 存在时，额外做
逐页、逐引脚网络对比（V3/V4 应对齐；不一致即判失败）。参考默认用仓库自带的
probes/data/eprj3_ref/Fresnel_V2.1_LaserDriver_EVM_2026-10-22.epro2（导出于
工程最后修改之后）；换工程时用参数或环境变量覆盖。

覆盖点（2026-10-19 新增 Eprj3DB）：
  1. 格式路由：目录 / .eprj3 索引文件都能识别为 Eprj3DB；
  2. 页/组件/位号计数与参考导出一致（13 页；TEC 83 组件 / 41 位号）；
  3. 坐标/旋转标定：TEC 页 U601 的 pinmap 与 .epro2 一致（含 IN2N–OUT2
     短接、PGNDS/EP 堆叠、TMPGD 悬空），文字坐标保持原值（不翻转）；
  4. 可选：全部页面的 pinmap 逐引脚网络对比（0 差异）。
"""
import io
import json
import os
import sys
from contextlib import redirect_stdout
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import lceda_reader as L  # noqa: E402

DEFAULT_V4 = (r"C:\Users\dell\Documents\LCEDA-Pro\projects"
              r"\Fresnel_V2.1_LaserDriver_EVM")
DEFAULT_EPRO2 = os.path.join(
    HERE, "data", "eprj3_ref",
    "Fresnel_V2.1_LaserDriver_EVM_2026-10-22.epro2")
V4 = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LCEDA_EPRJ3", DEFAULT_V4)
REF = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("LCEDA_EPRO2",
                                                          DEFAULT_EPRO2)

FAILS = []


def check(name, cond, detail=""):
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name,
                           ("  -- " + detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def rows(db, page, board):
    args = SimpleNamespace(page=page, schematic=board, designator=None,
                           json=True, no_domain=False)
    out = io.StringIO()
    with redirect_stdout(out):
        L.cmd_pinmap(db, args)
    return json.loads(out.getvalue())


def keymap(rs):
    return {(r["designator"], str(p["number"]), str(p["pin"])): p["net"] or ""
            for r in rs for p in r["pins"]}


if not os.path.exists(V4):
    print("回归工程不存在: %s（可用 LCEDA_EPRJ3 覆盖）" % V4)
    sys.exit(2)
cls = L.detect_backend(V4)
check("格式路由 -> Eprj3DB", cls is L.Eprj3DB, repr(cls))
db = cls(V4)
print("工程: %s" % db.root)

pages = db.sheets(1)
check("页数 = 13", len(pages) == 13, "实际 %d" % len(pages))
check("页标题含板名", all("::" in p[1] for p in pages))
check("工程名完整（含点号）",
      db.project_name() == db.root.name, db.project_name())

tec = L.resolve_page(db, "TEC Controller", "LaserDriver EVM")
sheet = L.parse_sheet(db, tec)
des = {c.get("designator") for c in sheet["components"] if c.get("designator")}
check("TEC 页组件数 = 83", len(sheet["components"]) == 83,
      str(len(sheet["components"])))
check("TEC 页位号数 = 41", len(des) == 41, str(len(des)))

r601 = next((r for r in rows(db, "TEC Controller", "LaserDriver EVM")
             if r["designator"] == "U601"), None)
check("U601 存在且有 25 个引脚", r601 is not None and len(r601["pins"]) == 25,
      str(len(r601["pins"]) if r601 else None))
pm = {p["pin"]: p for p in r601["pins"]} if r601 else {}
check("U601.IN2N 短接到 OUT2",
      "U601.OUT2" in pm.get("IN2N", {}).get("wire_peers", []),
      str(pm.get("IN2N")))
check("U601.PGNDS#12/13/EP 堆叠互连",
      {"U601.PGNDS#13", "U601.EP"} <= set(pm.get("PGNDS#12", {}).get("wire_peers", [])),
      str(pm.get("PGNDS#12")))
check("U601.TMPGD 悬空", not pm.get("TMPGD", {}).get("peers")
      and not pm.get("TMPGD", {}).get("wire_peers"), str(pm.get("TMPGD")))
check("U601.PVINS/PVINL 同网络",
      pm.get("PVINS", {}).get("net") == pm.get("PVINL", {}).get("net"),
      "%r/%r" % (pm.get("PVINS", {}).get("net"),
                 pm.get("PVINL", {}).get("net")))

texts = {t["text"]: (round(t["x"], 1), round(t["y"], 1))
         for t in sheet["texts"]}
check("文字坐标不翻转（395,545）",
      texts.get("Clock Synchronization via EN") == (395.0, 545.0),
      str(texts.get("Clock Synchronization via EN")))

if os.path.isfile(REF):
    print("\n参考导出: %s" % REF)
    db3 = L.detect_backend(REF)(REF)
    total = diff = 0
    for _u, title, sch, _dt in pages:
        board, page = title.split("::", 1)
        m3 = keymap(rows(db3, page, board))
        m4 = keymap(rows(db, page, board))
        common = set(m3) & set(m4)
        total += len(common)
        diff += sum(1 for k in common if m3[k] != m4[k])
        if set(m3) != set(m4):
            diff += abs(len(set(m3) - set(m4))) + abs(len(set(m4) - set(m3)))
    check("全页 pinmap 与 .epro2 零差异（%d 引脚）" % total, diff == 0,
          "差异 %d" % diff)
else:
    print("\n跳过 .epro2 对比（参考文件不存在: %s）" % REF)

print()
print("ALL: %s" % ("PASS" if not FAILS else "FAIL(%d)" % len(FAILS)))
sys.exit(0 if not FAILS else 1)
