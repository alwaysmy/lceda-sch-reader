"""回归：.eprj3 的 CBB 实例展开与 netlist 对齐 .epro2。

用法：
    set PYTHONIOENCODING=utf-8
    python probes\\verify_eprj3_cbb.py

默认使用本机两个真实工程（路径可用环境变量覆盖）：
    Fresnel: C:\\Users\\dell\\Documents\\LCEDA-Pro\\projects\\
             Fresnel_V2.1_LaserDriver_EVM
             参考 probes/data/eprj3_ref/Fresnel_..._2026-10-22.epro2
    MMC:     C:\\Users\\dell\\Documents\\LCEDA-Pro\\projects\\
             MMC-110-MultiFields
             参考 MMC-110-MultiFields_backup\\..._2026-10-28-18-11.epro2

覆盖点：
  1. Fresnel 的 CBB200~203 通过 INSTANCE 文档展开，netlist 中能看到
     CBB200.U200 等母图位号；
  2. Fresnel / MMC 的 netlist 与同工程 .epro2 逐网络成员集合一致；
  3. 不出现 CBB_TEMPLATE_NOT_FOUND / CBB_INSTANCE_TARGET_UNAVAILABLE
     等展开缺口诊断。
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

DEFAULT_FRESNEL3 = (r"C:\Users\dell\Documents\LCEDA-Pro\projects"
                     r"\Fresnel_V2.1_LaserDriver_EVM")
DEFAULT_FRESNEL2 = os.path.join(
    HERE, "data", "eprj3_ref",
    "Fresnel_V2.1_LaserDriver_EVM_2026-10-22.epro2")
DEFAULT_MMC3 = (r"C:\Users\dell\Documents\LCEDA-Pro\projects"
                r"\MMC-110-MultiFields")
DEFAULT_MMC2 = (r"C:\Users\dell\Documents\LCEDA-Pro\projects"
                r"\MMC-110-MultiFields_backup"
                r"\MMC-110-MultiFields_2026-10-28-18-11.epro2")

FAILS = []


def check(name, cond, detail=""):
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name,
                           ("  -- " + detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def netlist(path):
    db = L.detect_backend(path)(path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        L.cmd_netlist(db, SimpleNamespace(json=True))
    return db, json.loads(buf.getvalue())


def shape(rows):
    """net -> (components, sheets, aliases)；别名顺序不参与比较。"""
    return {
        r["net"]: (
            tuple(sorted(r.get("components") or [])),
            tuple(sorted(r.get("sheets") or [])),
            tuple(sorted(r.get("aliases") or [])),
        )
        for r in rows
    }


def check_list(db, name):
    buf = io.StringIO()
    with redirect_stdout(buf):
        L.cmd_list(db, SimpleNamespace(json=False))
    check("%s list 含 PCB 文档" % name, "[docType=3]" in buf.getvalue(),
          buf.getvalue()[-160:])


def compare(name, path3, path2):
    print("\n%s" % name)
    if not (os.path.exists(path3) and os.path.exists(path2)):
        print("  跳过：工程或参考文件不存在")
        print("    eprj3=%s" % path3)
        print("    epro2=%s" % path2)
        return
    db3, r3 = netlist(path3)
    _db2, r2 = netlist(path2)
    s3, s2 = shape(r3), shape(r2)
    keys = set(s3) | set(s2)
    diff = [k for k in keys if s3.get(k) != s2.get(k)]
    check("netlist 网络数一致（%d）" % len(keys),
          len(s3) == len(s2), "eprj3=%d epro2=%d" % (len(s3), len(s2)))
    check("逐网络成员/页/别名一致", not diff,
          "差异 %d：%s" % (len(diff), sorted(diff)[:8]))
    bad = [d for d in db3.diagnostics
           if str(d.get("code", "")).startswith("CBB_")
           and d.get("affects_completeness")]
    check("无 CBB 展开缺口诊断", not bad, str(bad[:3]))
    check_list(db3, name)


def check_fresnel_cbb():
    print("\nFresnel CBB 位号")
    if not os.path.exists(DEFAULT_FRESNEL3):
        print("  跳过：Fresnel .eprj3 不存在")
        return
    _db, rows = netlist(DEFAULT_FRESNEL3)
    en = next((r for r in rows if r["net"] == "EN/SYNC"), None)
    comps = set((en or {}).get("components") or [])
    check("EN/SYNC 含 CBB200.U200", "CBB200.U200" in comps, str(sorted(comps)[:12]))
    check("EN/SYNC 含 CBB200 黑盒", "CBB200" in comps)
    check("EN/SYNC 成员数 >= 20", len(comps) >= 20, str(len(comps)))


if __name__ == "__main__":
    f3 = os.environ.get("LCEDA_EPRJ3", DEFAULT_FRESNEL3)
    f2 = os.environ.get("LCEDA_EPRO2", DEFAULT_FRESNEL2)
    m3 = os.environ.get("LCEDA_MMC_EPRJ3", DEFAULT_MMC3)
    m2 = os.environ.get("LCEDA_MMC_EPRO2", DEFAULT_MMC2)
    compare("Fresnel", f3, f2)
    check_fresnel_cbb()
    compare("MMC", m3, m2)
    print()
    print("ALL: %s" % ("PASS" if not FAILS else "FAIL(%d)" % len(FAILS)))
    sys.exit(0 if not FAILS else 1)
