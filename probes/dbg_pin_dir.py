"""探针：PIN 旋转方向语义——(cos rot, sin rot) 从引脚位置出发指向体还是体外。
用 DAC8562 符号(U27 用)与标题块符号验证：比较 引脚位置+方向*len 与 BBOX 中心的距离变化。"""
import io, sys, json, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

db = lr.LcedaDB(r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch"
                r"\涡流传感器-V1.0-2026.04.01.eprj2")
for u, t, s, dt in db.sheets():
    if dt != 1 or t != "高速DA":
        continue
    sh = lr.parse_sheet(db, u)
    for c in sh["components"]:
        if c.get("designator") not in ("U27",):
            continue
        sym = lr.symbol_of(db, c)
        row = db.cur.execute(
            "SELECT dataStr FROM components WHERE uuid=?", (sym,)).fetchone()
        text = db.decompress(row[0])
        bbox = None
        pins = []
        cur_part = None
        for ln in text.splitlines():
            try:
                a = json.loads(ln)
            except Exception:
                continue
            if not isinstance(a, list):
                continue
            if a[0] == "PART" and len(a) > 2 and isinstance(a[2], dict):
                cur_part = a[1]
                b = a[2].get("BBOX")
                if b and len(b) == 4:
                    bbox = [min(b[0], b[2]), min(b[1], b[3]),
                            max(b[0], b[2]), max(b[1], b[3])]
            elif a[0] == "PIN" and len(a) >= 8:
                pins.append({"id": a[1], "show": a[2], "elec": a[3],
                             "x": a[4], "y": a[5], "len": a[6],
                             "rot": a[7], "part": cur_part})
        cx = (bbox[0] + bbox[2]) / 2 if bbox else 0
        cy = (bbox[1] + bbox[3]) / 2 if bbox else 0
        print(f"U27 符号 {sym[:12]} BBOX={bbox} 中心=({cx},{cy})")
        d2c = lambda x, y: math.hypot(x - cx, y - cy)
        for p in pins[:14]:
            dx, dy = math.cos(math.radians(p["rot"])), \
                math.sin(math.radians(p["rot"]))
            L = float(p["len"] or 20)
            tip = (p["x"] + dx * L, p["y"] + dy * L)
            tail = (p["x"] - dx * L, p["y"] - dy * L)
            inward_tip = d2c(*tip) < d2c(p["x"], p["y"])
            inward_tail = d2c(*tail) < d2c(p["x"], p["y"])
            verdict = "tip向体内" if inward_tip else (
                "tail向体内" if inward_tail else "都不向")
            print(f'  pin {p["id"]} ({p["x"]},{p["y"]}) rot={p["rot"]} '
                  f'len={L} elec={p["elec"]} -> {verdict}')
    break
