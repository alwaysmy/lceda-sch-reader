import base64, gzip, io, json, sqlite3, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

NEW = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"
conn = sqlite3.connect(f"file:{NEW}?mode=ro", uri=True)

def decompress(ds):
    if not ds:
        return ""
    s = ds[6:] if isinstance(ds, str) and ds.startswith("base64") else ds
    try:
        data = base64.b64decode(s)
    except Exception:
        return ""
    try:
        return gzip.decompress(data).decode("utf-8")
    except Exception:
        return data.decode("utf-8", errors="replace")

# 工具实现路径模拟：某页 NetFlag 实例引脚 -> 附近 wire 是否有 NET
# 先找有 Global Net Name 的页
found = 0
for u, t, dt, ds in conn.execute(
        "SELECT uuid, display_title, docType, dataStr FROM documents WHERE docType=1").fetchall():
    if found >= 2:
        break
    text = decompress(ds)
    comps = {}
    netflags = {}
    wires = []
    nets = {}
    for ln in text.splitlines():
        try:
            a = json.loads(ln)
        except Exception:
            continue
        if not isinstance(a, list) or not a:
            continue
        if a[0] == "COMPONENT":
            comps[a[1]] = {"title": a[2] if len(a) > 2 else "",
                           "x": a[3] if len(a) > 3 else 0,
                           "y": a[4] if len(a) > 4 else 0,
                           "rot": a[5] if len(a) > 5 else 0,
                           "mirror": a[6] if len(a) > 6 else 0}
        elif a[0] == "WIRE":
            wires.append((a[1], a[2]))
        elif a[0] == "ATTR" and len(a) >= 5:
            if a[3] == "Symbol":
                comps.setdefault(a[2], {})["sym"] = a[4]
            elif a[3] == "Global Net Name":
                netflags[a[2]] = a[4]
            elif a[3] == "NET":
                nets[a[2]] = a[4]
    if not netflags:
        continue
    found += 1
    print(f"===== 页 {t} (uuid {u[:8]}): Global Net Name {len(netflags)} 个 =====")
    for cid, nm in list(netflags.items())[:4]:
        c = comps.get(cid, {})
        print(f"  实例 {cid}: {nm}  title={c.get('title')!r} pos=({c.get('x')},{c.get('y')})")
    # NetFlag 实例附近（±20）的 wire 端点及其 NET 名
    for cid, nm in list(netflags.items())[:4]:
        c = comps.get(cid, {})
        near = []
        for wid, segs in wires:
            for s_ in segs:
                for p in ((s_[0], s_[1]), (s_[2], s_[3])):
                    if abs(p[0] - c.get("x", 0)) <= 20 and abs(p[1] - c.get("y", 0)) <= 20:
                        near.append((wid, p, nets.get(wid)))
        print(f"  实例 {cid}({nm}) 附近 wire: {near[:6]}")

conn.close()
