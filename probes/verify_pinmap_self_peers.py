"""回归：pinmap 必须列出“同器件内”的引脚互连（2026-10-19 修复）。

背景：`cmd_pinmap` 计算 peers/wire_peers 时原先用 `if odes == des: continue`
按 **designator 整个器件** 排除，导致同器件两脚短接被显示成“悬空”（net 为空、
peers/wire_peers 也为空，与真的没接线无法区分）：
  - ADN8834 数字 PID 按手册要求 IN2N–OUT2 短接（本工程 TEC Controller 页 U601）；
  - 堆叠的 PGND/EP 引脚（U601 #12/#13/EP 由同一段导线相连）；
  - 运放跟随器的 -IN↔OUT 直连（DAC 页 U403、Howland Current Source 页 U501）。

修复：只排除**本引脚自身**（`op is p`），不再按 designator 排除。副作用是
多单元符号（同页多个 part 共用 Designator、不同 cid）之间的互连也可见，
这正是期望行为（此前同样被隐藏）。

断言：
  1. U601.IN2N ↔ U601.OUT2 互相出现在 wire_peers；
  2. U601.PGNDS#12 / PGNDS#13 / EP 三脚互相列出；
  3. U601.TMPGD 真悬空（peers 与 wire_peers 都为空）——防止“修过头”
     把本引脚自身列进 peers；
  4. U403.-IN ↔ U403.OUT 互相列出（另一类符号：运放跟随器直连）；
  5. 全页扫描：任何引脚都不得把自身列进 peers/wire_peers，peer 列表无重复。

用法：
    set PYTHONIOENCODING=utf-8
    python probes\\verify_pinmap_self_peers.py [工程路径]
工程路径也可用环境变量 LCEDA_FRESNEL 指定；默认同 regress_fresnel_v21.py。
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

DEFAULT = (r"D:\Projects\01-激光干涉仪\06-激光干涉仪V2.1\02-硬件工程"
           r"\Fresnel_V2.1_LaserDriver_EVM.epro2")
PATH = (sys.argv[1] if len(sys.argv) > 1
        else os.environ.get("LCEDA_FRESNEL", DEFAULT))
BOARD = "LaserDriver EVM"

FAILS = []


def check(name, cond, detail=""):
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name,
                           ("  -- " + detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def pinmap_rows(db, page):
    args = SimpleNamespace(page=page, schematic=BOARD, designator=None,
                           json=True, no_domain=False)
    buf = io.StringIO()
    with redirect_stdout(buf):
        L.cmd_pinmap(db, args)
    return json.loads(buf.getvalue())


def find_pin(rows, des, pin):
    for row in rows:
        if row["designator"] != des:
            continue
        for p in row["pins"]:
            if p["pin"] == pin:
                return p
    return None


def mutual(rows, des, a, b):
    pa, pb = find_pin(rows, des, a), find_pin(rows, des, b)
    if not pa or not pb:
        return False, "缺引脚（%s/%s）" % (a, b)
    ta, tb = "%s.%s" % (des, b), "%s.%s" % (des, a)
    got_a = ta in (pa["peers"] + pa["wire_peers"])
    got_b = tb in (pb["peers"] + pb["wire_peers"])
    return (got_a and got_b,
            "%s peers=%s wire=%s / %s peers=%s wire=%s"
            % (a, pa["peers"], pa["wire_peers"],
               b, pb["peers"], pb["wire_peers"]))


if not os.path.isfile(PATH):
    print("回归工程不存在: %s（可用 LCEDA_FRESNEL 环境变量覆盖）" % PATH)
    sys.exit(2)

print("工程: %s" % PATH)
db = L.detect_backend(PATH)(PATH)

# --- 1~3) TEC Controller 页：同器件短接、堆叠电源脚、真悬空 -----------------
tec = pinmap_rows(db, "TEC Controller")

ok, detail = mutual(tec, "U601", "IN2N", "OUT2")
check("U601.IN2N ↔ U601.OUT2（数字 PID 缓冲短接）", ok, detail)

p12 = find_pin(tec, "U601", "PGNDS#12")
p13 = find_pin(tec, "U601", "PGNDS#13")
pep = find_pin(tec, "U601", "EP")
tags12 = set((p12 or {}).get("peers", []) + (p12 or {}).get("wire_peers", []))
tags13 = set((p13 or {}).get("peers", []) + (p13 or {}).get("wire_peers", []))
tagsep = set((pep or {}).get("peers", []) + (pep or {}).get("wire_peers", []))
check("U601 PGNDS#12/#13/EP 堆叠互连",
      {"U601.PGNDS#13", "U601.EP"} <= tags12
      and {"U601.PGNDS#12", "U601.EP"} <= tags13
      and {"U601.PGNDS#12", "U601.PGNDS#13"} <= tagsep,
      "12=%s 13=%s EP=%s" % (sorted(tags12), sorted(tags13), sorted(tagsep)))

tmp = find_pin(tec, "U601", "TMPGD")
check("U601.TMPGD 保持真悬空（不列自身）",
      tmp is not None and not tmp["peers"] and not tmp["wire_peers"],
      "TMPGD=%r" % (tmp,))

# --- 4) DAC 页：运放跟随器 -IN ↔ OUT 直连 ----------------------------------
dac = pinmap_rows(db, "DAC")
ok, detail = mutual(dac, "U403", "-IN", "OUT")
check("U403.-IN ↔ U403.OUT（跟随器直连）", ok, detail)

# --- 5) 全页自检：不列自身、列表无重复 -------------------------------------
bad_self, bad_dup = [], []
for page in ("TEC Controller", "DAC"):
    rows = tec if page == "TEC Controller" else dac
    for row in rows:
        des = row["designator"]
        for p in row["pins"]:
            mine = "%s.%s" % (des, p["pin"])
            for field in ("peers", "wire_peers"):
                vals = p.get(field) or []
                if mine in vals:
                    bad_self.append("%s.%s[%s]" % (des, p["pin"], field))
                if len(vals) != len(set(vals)):
                    bad_dup.append("%s.%s[%s]" % (des, p["pin"], field))
check("无引脚把自己列进 peers/wire_peers", not bad_self, str(bad_self[:5]))
check("peers/wire_peers 无重复项", not bad_dup, str(bad_dup[:5]))

print()
print("ALL: %s" % ("PASS" if not FAILS else "FAIL(%d)" % len(FAILS)))
sys.exit(0 if not FAILS else 1)
