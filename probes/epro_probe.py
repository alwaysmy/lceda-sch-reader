import io, json, subprocess, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
R = r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\lceda_reader.py"
E1 = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro"
E2 = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_TPS56C230_Buck_12Vto5V_6A_2026-08-13.epro"

def run(eprj, *cmd):
    p = subprocess.run([sys.executable, R, "--eprj", eprj] + list(cmd),
                       capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout, p.stderr

for tag, E in (("E1-Piezo", E1), ("E2-Buck", E2)):
    print("=" * 25, tag, "=" * 25)
    for cmd in (["--json", "components"], ["--json", "netlist"],
                ["--json", "bom"], ["--json", "datasheets"]):
        rc, out, err = run(E, *cmd)
        n = len(out.splitlines())
        ok = "OK"
        if "--json" in cmd:
            try:
                json.loads(out)
            except Exception as e:
                ok = f"JSON-INVALID({e})"
        print(f"  {' '.join(cmd):22s} rc={rc} lines={n} {ok}")
        if rc != 0:
            print("   stderr:", err[-300:])
    # 页列表与 pinmap
    rc, out, _ = run(E, "list")
    pages = [ln.split("] ", 1)[1].strip() for ln in out.splitlines()
             if "[sch=" in ln]
    print("  页:", pages)
    for pg in pages[:3]:
        short = pg.split("::")[-1]
        for cmd in (["--json", "pinmap", short], ["--json", "pins", short],
                    ["nets", short]):
            rc, out, err = run(E, *cmd)
            note = ""
            if rc != 0:
                note = " ERR:" + err.strip().splitlines()[-1][:120] if err else ""
            print(f"    {' '.join(cmd):30s} rc={rc} lines={len(out.splitlines())}{note}")

# DNP 标志探查：实例级 ATTR 名分布（找 BOM/PCB/DNP 相关）
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr
for tag, E in (("E1", E1), ("E2", E2)):
    print("=" * 20, f"{tag} 实例级 ATTR 名分布", "=" * 20)
    db = lr.EproDB(E)
    attr_names = collections.Counter()
    dnp_rows = []
    for uuid, title, sch, dt in db.sheets():
        recs = db.sheet_records(uuid)
        if not recs:
            continue
        comps = {}
        for a in recs:
            if isinstance(a, list) and a and a[0] == "COMPONENT":
                comps[a[1]] = a[2] if len(a) > 2 else ""
        for a in recs:
            if isinstance(a, list) and len(a) >= 5 and a[0] == "ATTR":
                nm = str(a[3])
                attr_names[nm] += 1
                if any(k in nm.lower() for k in
                       ("bom", "pcb", "dnp", "fit", "mount", "populate")):
                    desig = ""
                    # 找该实例的 Designator
                    cid = a[2]
                    dnp_rows.append((title, comps.get(cid, "?"), nm, str(a[4])))
    print("ATTR 名 top:", dict(collections.Counter(
        {k: v for k, v in attr_names.items() if v >= 1}).most_common(30)))
    seen = set()
    for t, c, nm, v in dnp_rows:
        key = (nm, v)
        if key in seen:
            continue
        seen.add(key)
        print(f"   [{t}] {nm} = {v!r} (示例实例 {c})")
