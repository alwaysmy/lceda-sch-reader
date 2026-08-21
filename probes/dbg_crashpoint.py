import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

X = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver_export.epro2"
db = lr.Epro2DB(X)
u = next(u for u, t, s, dt in db.sheets() if t.endswith("::controldac"))
sh = lr.parse_sheet(db, u)
target = (625.0, 1085.0)
print("目标点在 sheet['nets']?",
      any(target in [tuple(p) for p in n["points"]] for n in sh["nets"]))
# 该点的 net 值
for n in sh["nets"]:
    for px, py in n["points"]:
        if abs(px-625) < 0.6 and abs(py-1085) < 0.6:
            print("  nets 点:", (px, py), "net=", repr(n["net"]))

pinc = lr._collect_pinmap_data(db, sh, u)
cp, ws_, pw, ep = pinc
print("_collect 后 endp[(625,1085)] =", repr(ep.get(target)))
print("pt_wires 含该点?", target in pw, "wids=", pw.get(target))
# PORTe2592 实例信息
c = next(c for c in sh["components"]
         if c.get("designator") == "PORTe2592" or
         c["cid"] == "e2592")
print("PORTe2592:", {k: c.get(k) for k in ("cid", "title", "designator")},
      "Name attr =", repr(c["attrs"].get("Name")),
      "net =", repr(c.get("net")))
