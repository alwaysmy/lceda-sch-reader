"""render 批量冒烟：跨格式多页渲染，校验 SVG 可解析+元素数，输出汇总。"""
import io, sys, json, subprocess, xml.etree.ElementTree as ET, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
TOOL = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\lceda_reader.py"
OUTDIR = os.path.dirname(os.path.abspath(__file__)) + r"\data\render_smoke"
os.makedirs(OUTDIR, exist_ok=True)

CASES = [
    # (eprj, sheet或None=取第一页, 标签)
    (r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2", "高速DA", "woLiu-V1.0-eprj2"),
    (r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2", "激励输出和AD采集", "woLiu-V1.0-eprj2"),
    (r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\V1.1版主控原理图\MCU主控-V1.1-2026.05.06.eprj2", None, "MCU-V1.1-eprj2"),
    (r"C:\Users\dell\Documents\LCEDA-Pro\example-projects\示例工程_快速入门.eprj2", "P1", "demo-eprj2"),
    (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro", None, "Piezo-epro"),
    (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_TPS56C230_Buck_12Vto5V_6A_2026-08-13.epro", None, "Buck-epro"),
    (r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器_backup\涡流传感器_2026-08-10-14-47.epro2", None, "woLiu-epro2"),
]

def first_sheet(eprj):
    sys.path.insert(0, os.path.dirname(TOOL))
    import lceda_reader as lr
    r = lr.detect_backend(eprj)
    if r == "DECRYPT_NEW":
        tmp = lr._decrypt_new_eprj2(eprj)
        db = lr.Epro2DB(tmp)
        tag = "(解密)"
    else:
        db = r(eprj)
        tag = ""
    rows = [s for s in db.sheets() if s[3] == 1]
    return (rows[0][1], tag) if rows else (None, tag)

fails = 0
for eprj, sheet, tag in CASES:
    if sheet is None:
        sheet, dec = first_sheet(eprj)
        tag += dec or ""
        print(f"[{tag}] 自动选页: {sheet}")
    out = os.path.join(OUTDIR, f"{tag}.svg")
    p = subprocess.run(
        [sys.executable, TOOL, "--eprj", eprj, "render", sheet, "-o", out],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    ok = False; n_elem = 0; err = ""
    if p.returncode == 0 and os.path.exists(out):
        try:
            root = ET.parse(out).getroot()
            n_elem = len(list(root.iter()))
            vb = root.get("viewBox")
            ok = vb is not None and all(float(v) == float(v) for v in vb.split()) \
                and n_elem > 20
        except Exception as e:
            err = f"XML: {e}"
    if not ok:
        fails += 1
        err = err or p.stderr.strip().splitlines()[-1] if p.stderr.strip() else f"rc={p.returncode}"
    size = os.path.getsize(out) // 1024 if os.path.exists(out) else 0
    print(f"{'PASS' if ok else 'FAIL'} {tag:22s} 「{sheet}」 元素{n_elem:5d} {size:4d}KB {err}")
print("ALL:", "PASS" if fails == 0 else f"{fails} FAIL")
