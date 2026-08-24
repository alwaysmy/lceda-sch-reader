"""全工程 polar 扫描：各工程极性器件 + 不规范位号汇总。"""
import io, sys, subprocess, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
TOOL = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader"
        r"\lceda_reader.py")
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

FILES = [
    ("涡流V1.0", r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"),
    ("涡流", r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2"),
    ("MCU-V1.1", r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\V1.1版主控原理图\MCU主控-V1.1-2026.05.06.eprj2"),
    ("快速入门", r"C:\Users\dell\Documents\LCEDA-Pro\example-projects\示例工程_快速入门.eprj2"),
    ("Piezo-epro", r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro"),
    ("Buck-epro", r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_TPS56C230_Buck_12Vto5V_6A_2026-08-13.epro"),
    ("Piezo-新eprj2", r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"),
    ("涡流-epro2", r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器_backup\涡流传感器_2026-08-10-14-47.epro2"),
]

grand_bad = {}
for tag, path in FILES:
    if not os.path.exists(path):
        print(f"[{tag}] 文件不存在，跳过")
        continue
    p = subprocess.run(
        [sys.executable, TOOL, "--eprj", path, "--json", "polar"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=ENV, timeout=900)
    out = (p.stdout or "").strip()
    if not out.startswith("{"):
        print(f"[{tag}] FAIL rc={p.returncode} {out[:80]}")
        continue
    d = json.loads(out)
    items = d["items"]
    n_ok = sum(1 for r in items if r["polarity_resolved"])
    bad = [(r["designator"], r["page"], r["device"][:24])
           for r in items if not r["designator_std"]]
    print(f"[{tag}] 极性器件 {d['count']}（可归一 {n_ok} / 需查手册 "
          f"{d['count'] - n_ok}） 不规范位号 {len(bad)}")
    for des, page, dev in bad:
        print(f"    ⚠ {des!r:8s} {dev:26s} [{page}]")
        grand_bad.setdefault(tag, []).append((des, page, dev))

print("\n===== 不规范位号汇总 =====")
if not grand_bad:
    print("（仅涡流V1.0 存在，其余工程全部规范）")
for tag, lst in grand_bad.items():
    print(f"{tag}: {len(lst)} 个")
    for des, page, dev in lst:
        print(f"  {des!r:8s} {dev[:28]:28s} [{page}]")
