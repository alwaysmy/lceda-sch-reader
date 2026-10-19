"""回归：pcb_workbench DFM 批处理检查（走线/窄颈/间距/环宽）。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from pcb_workbench.v4 import load_epcb2  # noqa: E402
from pcb_workbench.dfm import check  # noqa: E402

DEFAULT = (r"C:\Users\dell\Documents\LCEDA-Pro\projects"
           r"\Fresnel_V2.1_LaserDriver_EVM\pcb\PCB1.epcb2")
PATH = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LCEDA_PCB1", DEFAULT)
FAILS = []


def check_item(name, cond, detail=""):
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name,
                           ("  -- " + detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


if not os.path.isfile(PATH):
    print("回归 PCB 不存在: %s" % PATH)
    sys.exit(2)
d = load_epcb2(PATH)

loose = check(d, min_track=0.10, min_neck=0.05, min_clearance=0.05,
              min_annular=0.05)
strict = check(d, min_track=0.30, min_neck=0.50, min_clearance=1.0,
               min_annular=0.20)
print("loose:", loose["summary"], " strict:", strict["summary"])

check_item("阈值放宽后 0 项", loose["summary"]["violations"] == 0,
           str(loose["summary"]))
check_item("走线宽度检查能命中 0.15mm 走线",
           strict["summary"]["track"] > 0, str(strict["summary"]))
check_item("间距检查能命中（1.0mm 阈值）",
           strict["summary"]["clearance"] > 0, str(strict["summary"]))
check_item("环宽检查能命中（0.2mm 阈值）",
           strict["summary"]["annular"] > 0, str(strict["summary"]))
check_item("窄颈检查能命中（0.5mm 阈值）",
           strict["summary"]["neck"] > 0, str(strict["summary"]))
check_item("间距结果不含空网络",
           all(r["net_a"] and r["net_b"] for r in strict["clearance"]),
           str(strict["clearance"][:2]))
check_item("返回缓存状态字段", "cache" in strict
           and "cache_may_be_stale" in strict["cache"])
check_item("间距口径已标注", "clearance_scope" in strict,
           str(strict.get("clearance_scope")))

print()
print("ALL: %s" % ("PASS" if not FAILS else "FAIL(%d)" % len(FAILS)))
sys.exit(0 if not FAILS else 1)
