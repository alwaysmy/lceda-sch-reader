"""回归：.eprj3 元件可读名（partId 占位 -> DeviceName/DEVICE title）。

官方生成器把 COMPONENT.partId 固定为 ``pid...``；真实客户端的 partId
是可读型号（如 ``CL05B104KB54PNC.1``）。本回归确认：
  1. 官方 blink 的 C1/R1 在 components/find/pinmap 中显示 CAP/RES；
  2. 官方真实导出示例仍保留 CapAcitance.1；
  3. MMC 真实工程仍保留 CL05B104KB54PNC.1；
  4. Fresnel 的 CBB 哈希 partId 回退为模板名。
用法：python probes/verify_eprj3_title.py
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

BLINK = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\upstream"
         r"\easyeda-eprj3-skill\examples\blink")
REAL_EXPORT = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\upstream"
               r"\easyeda-eprj3-skill\examples\easyeda-eprj3-project")
MMC = r"C:\Users\dell\Documents\LCEDA-Pro\projects\MMC-110-MultiFields"
FRESNEL = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Fresnel_V2.1_LaserDriver_EVM"

FAILS = []


def check(name, cond, detail=""):
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name,
                           ("  -- " + detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def run(db, fn, args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn(db, args)
    return json.loads(buf.getvalue())


def components(db, sheet):
    return run(db, L.cmd_components,
               SimpleNamespace(sheet=sheet, json=True))


def find(db, des):
    return run(db, L.cmd_find,
               SimpleNamespace(designator=des, raw=False, json=True))


def pinmap(db, page, des):
    return run(db, L.cmd_pinmap,
               SimpleNamespace(page=page, schematic=None, designator=des,
                               json=True, no_domain=False))


def main():
    print("blink（官方生成器）")
    if os.path.isdir(BLINK):
        db = L.Eprj3DB(BLINK)
        cs = {c["designator"]: c["title"] for c in components(db, "P1")}
        check("components C1 -> CAP", cs.get("C1") == "CAP", str(cs.get("C1")))
        check("components R1 -> RES", cs.get("R1") == "RES", str(cs.get("R1")))
        f = find(db, "R1")
        check("find R1 -> RES", f and f[0]["title"] == "RES",
              str(f[0]["title"] if f else None))
        pm = pinmap(db, "P1", "R1")
        check("pinmap R1 -> RES", pm and pm[0]["symbol"] == "RES",
              str(pm[0]["symbol"] if pm else None))
    else:
        print("  跳过：blink 不存在")

    print("\n官方真实导出示例（不应改名）")
    if os.path.isdir(REAL_EXPORT):
        db = L.Eprj3DB(REAL_EXPORT)
        cs = {c["designator"]: c["title"] for c in components(db, "P1")}
        check("C1 保持 CapAcitance.1",
              cs.get("C1") == "CapAcitance.1", str(cs.get("C1")))
    else:
        print("  跳过：示例不存在")

    print("\n真实工程（不应改名）")
    if os.path.isdir(MMC):
        db = L.Eprj3DB(MMC)
        cs = {c["designator"]: c["title"] for c in components(db, "控制器")}
        check("C300 保持 CL05B104KB54PNC.1",
              cs.get("C300") == "CL05B104KB54PNC.1", str(cs.get("C300")))
    else:
        print("  跳过：MMC 不存在")
    if os.path.isdir(FRESNEL):
        db = L.Eprj3DB(FRESNEL)
        cs = {c["designator"]: c["title"] for c in components(db, "Power Supply")}
        check("CBB200 回退为模板名",
              cs.get("CBB200") == "ADP5071_DualPowerSupply",
              str(cs.get("CBB200")))
    else:
        print("  跳过：Fresnel 不存在")

    print()
    print("ALL: %s" % ("PASS" if not FAILS else "FAIL(%d)" % len(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
