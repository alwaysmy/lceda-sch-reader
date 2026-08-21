import io, json, subprocess, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

R = r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\lceda_reader.py"
E1 = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro"
E2 = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_TPS56C230_Buck_12Vto5V_6A_2026-08-13.epro"

def run(eprj, *cmd):
    p = subprocess.run([sys.executable, R, "--eprj", eprj] + list(cmd),
                       capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout, p.stderr

print("== 1) 全命令冒烟（json 有效性 + 崩溃检查） ==")
for tag, E in (("E1-Piezo", E1), ("E2-Buck", E2)):
    fails = []
    for cmd in (["--json", "components"], ["--json", "netlist"],
                ["--json", "bom"], ["--json", "datasheets"],
                ["--json", "boards"], ["--json", "devmap"]):
        rc, out, err = run(E, *cmd)
        ok = rc == 0
        if "--json" in cmd and ok:
            try:
                json.loads(out)
            except Exception as e:
                ok = False
                fails.append(f"{' '.join(cmd)} JSON:{e}")
        if not ok:
            fails.append(f"{' '.join(cmd)} rc={rc} {err.strip().splitlines()[-1][:100] if err else ''}")
    print(f"  {tag}: {'全部 OK' if not fails else fails}")

print("== 2) E2 单页命令（原 KeyError 页） ==")
for cmd in (["--json", "pinmap", "P1"], ["--json", "pins", "P1"], ["nets", "P1"]):
    rc, out, err = run(E2, *cmd)
    print(f"  {' '.join(cmd):24s} rc={rc} lines={len(out.splitlines())}",
          "" if rc == 0 else err.strip().splitlines()[-1][:120])

print("== 3) E1 DNP 0R 专项：两脚网络是否不再合并 ==")
db = lr.EproDB(E1)
# 找一个 Add into BOM=no 的 0Ω（title/desc 判定）
target = None
normal = None
for uuid, title, sch, dt in db.sheets():
    sheet = lr.parse_sheet(db, uuid)
    dmap = db.device_map()
    for c in sheet["components"]:
        du = c.get("device_uuid") or ""
        desc = dmap.get(du, ("", "", ""))[2] if du else ""
        t = c.get("title") or ""
        if lr._is_zero_ohm(t, desc):
            if c.get("dnp") and target is None:
                target = (uuid, title, c)
            if not c.get("dnp") and normal is None:
                normal = (uuid, title, c)
    if target and normal:
        break
for tag, item in (("DNP 0Ω", target), ("正常 0Ω", normal)):
    if not item:
        print(f"  {tag}: 未找到")
        continue
    uuid, ptitle, c = item
    des = c.get("designator")
    print(f"  {tag}: {ptitle} {des} (dnp={c.get('dnp')})")
    rc, out, _ = run(E1, "--json", "pinmap", ptitle.split("::")[-1],
                     "--schematic", ptitle.split("::")[0],
                     "--designator", des)
    if rc != 0:
        print("    pinmap 失败:", out[:100])
        continue
    rows = json.loads(out)
    nets = [(p["pin"], p["net"]) for r in rows for p in r["pins"]]
    print(f"    两脚网络: {nets}  dnp标志: {[r.get('dnp') for r in rows]}")

print("== 4) E1 netlist 中 DNP 0R 两侧网络独立性抽查 ==")
if target:
    uuid, ptitle, c = target
    des = c.get("designator")
    # 用内部 API 直接看 dom
    sheet = lr.parse_sheet(db, uuid)
    pinc = lr._collect_pinmap_data(db, sheet, uuid)
    cp, ws, pw, ep = pinc
    dom = lr.resolve_nets_by_domain(db, sheet, cp, ws, pw, ep)
    pins = [(k[1], v) for k, v in dom.items() if k[0] == des]
    print(f"  {des} 引脚网络: {pins}")
    uniq = {v for _, v in pins}
    print("  两脚网络不同(未合并):", len(uniq) >= 2 or all(not v for v in uniq))

print("== 5) bridges 输出 dnp 字段 ==")
sheet = lr.parse_sheet(db, target[0]) if target else None
if sheet:
    pinc = lr._collect_pinmap_data(db, sheet, target[0])
    cp, ws, pw, ep = pinc
    pm = lr.resolve_nets_by_domain(db, sheet, cp, ws, pw, ep)
    br = lr.collect_two_pin_bridges(db, sheet, cp, pm, ep)
    dnps = [b for b in br if b.get("dnp")]
    print(f"  该页 bridges={len(br)}, 其中 dnp={len(dnps)}",
          [(b['designator'], b['kind'], b['direct']) for b in dnps[:4]])