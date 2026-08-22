"""对比修改前后 Piezo_Driver.eprj2 的结构树差异。"""
import io, sys, json, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)
rows = list(conn.execute(
    "SELECT id, branch_uuid, length(structure) FROM project_structures"))
print("project_structures:", rows)
for row in conn.execute("SELECT structure FROM project_structures"):
    st = json.loads(row[0])
    boards = st.get("boards", {})
    schs = st.get("schematics", {})
    sheets = st.get("sheets", {})
    print(f"  boards={len(boards)} schematics={len(schs)} sheets={len(sheets)}")
    for b in boards.values():
        print(f"    板: {b['title']}")
# history_data 行数与大小
for row in conn.execute("SELECT uuid, history_uuid, length(dataStr) FROM history_data"):
    print(f"  blob uuid={row[0][:20]} hist={row[1][:20]} len={row[2]}")
