import io, sys, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

V3 = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
db = lr.Epro2DB(V3)

# 找 ControlDAC_A 页（quadPizeoDriver_RevA）
page = None
for u, t, s, dt in db.sheets():
    if t == "quadPizeoDriver_RevA::ControlDAC_A":
        page = u
        break
print("page:", page)
recs = db.sheet_records(page)
kinds = collections.Counter(r[0] for r in recs)
print("合成记录分布:", dict(kinds))

sheet = lr.parse_sheet(db, page)
named = [n for n in sheet["nets"] if n["net"]]
print(f"nets: 总{len(sheet['nets'])} 命名{len(named)}",
      [n['net'] for n in named[:6]])
print("components:", len(sheet["components"]))

# 一个带 Designator 的元件：位置与符号引脚绝对坐标
c0 = next(c for c in sheet["components"] if c.get("designator"))
sym = lr.symbol_of(db, c0)
sp = db.symbol_pins(sym)
print(f"\n样本 {c0.get('designator')} title={c0.get('title')!r} "
      f"pos=({c0['x']},{c0['y']}) rot={c0['rot']} mirror={c0['mirror']}")
print(f"  symbol={str(sym)[:16]} symbol_type={sp.get('symbol_type')} "
      f"pins={len(sp['pins'])}")
p0 = sp["pins"][0]
print(f"  pin0 raw=({p0['x']},{p0['y']}) rot={p0['rot']}")
# 绝对坐标（复用工具变换）
rx, ry = p0["x"], p0["y"]
if c0.get("mirror"):
    rx = -rx
rot = (c0.get("rot") or 0) % 360
for _ in range(int(rot // 90)):
    rx, ry = -ry, rx
ax, ay = c0["x"] + rx, c0["y"] + ry
print(f"  pin0 绝对=({ax},{ay})")

# 附近 wire 端点
near = []
for n in sheet["nets"]:
    for px, py in n["points"]:
        d2 = (ax - px) ** 2 + (ay - py) ** 2
        if d2 <= 400:
            near.append((round(d2, 1), n["net"], px, py))
near.sort()
print("  附近端点(距离²<=400):", near[:6])

# wire 端点整体范围
allpts = [pt for n in sheet["nets"][:5] for pt in n["points"]]
print("  前5个wire的端点样例:", allpts[:6])
