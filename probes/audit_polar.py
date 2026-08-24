"""极性器件引脚信息审计：二极管/LED/TVS 的符号引脚名 + pins 输出现状。"""
import io, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

E = (r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch"
     r"\涡流传感器-V1.0-2026.04.01.eprj2")
db = lr.LcedaDB(E)

POLAR_PAT = re_pat = None
import re
POLAR_RE = re.compile(r"二极管|LED|TVS|稳压|肖特基|ESD|Schottky|Diode|Zener",
                      re.I)

# 1) 找极性器件实例，看符号引脚名
seen_sym = {}
pol_comps = []
for u, t, s, dt in db.sheets():
    if dt != 1:
        continue
    sh = lr.parse_sheet(db, u)
    for c in sh["components"]:
        du = c.get("device_uuid") or ""
        desc = (db.device_map().get(du, ("", "", ""))[2] if du else "")
        title = c.get("title") or ""
        if POLAR_RE.search(desc) or POLAR_RE.search(title):
            pol_comps.append((t, c, desc))

print(f"极性器件实例(前5页): {len(pol_comps)}")
name_pat = collections.Counter()
shown = 0
for page, c, desc in pol_comps:
    sym = lr.symbol_of(db, c)
    if sym and sym not in seen_sym:
        sp = db.symbol_pins(sym)
        names = tuple(sorted({p["name"] for p in (sp or {}).get("pins", [])}))
        seen_sym[sym] = names
        name_pat[names] += 1
        if shown < 8:
            shown += 1
            print(f"  {c.get('designator')}: title={c['title'][:24]!r} "
                  f"desc={desc[:24]!r} 引脚名={names}")
for names, n in name_pat.most_common():
    print(f"引脚名模式 {names}: {n} 个符号")

# 2) pins 命令对极性器件的输出（取一页 D2/LED 样例）
u0 = [u for u, t, s, dt in db.sheets() if dt == 1 and t == "高速DA"][0]
sh = lr.parse_sheet(db, u0)
pinc = lr._collect_pinmap_data(db, sh, u0)
cp, ws, pw, ep = pinc
dom = lr.resolve_nets_by_domain(db, sh, cp, ws, pw, ep)
print("\n== 高速DA 页极性器件 pins 输出 ==")
for (des, cid), plist in cp.items():
    d = (des or "")
    if any(k in d for k in ("D", "LED")) and any(
            POLAR_RE.search(p.get("device") or "") or
            POLAR_RE.search(str(plist[0].get("device") or ""))
            for p in plist if p.get("device")):
        for p in plist:
            net = dom.get((d, p["key"]), "?")
            print(f"  {d} pin={p['pin']!r} number={p.get('number')!r} "
                  f"net={net}")
        break
