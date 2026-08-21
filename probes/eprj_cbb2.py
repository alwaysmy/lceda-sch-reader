import io, sys, json, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")

E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)
cur = conn.cursor()

print("== 1) docType 分布 ==")
for row in cur.execute("SELECT docType, COUNT(*) FROM documents GROUP BY docType"):
    print("  docType", row)

print("\n== 2) block_symbol_attributes 全部内容 ==")
n = 0
for row in cur.execute("SELECT path, project_uuid, hash, attr FROM block_symbol_attributes"):
    n += 1
    if n <= 8:
        print(f"  path={row[0]}")
        print(f"    hash={row[2]} attr={str(row[3])[:300]}")
print("  总行数:", n)

print("\n== 3) documents.parent_uuid 非空的行 ==")
for row in cur.execute(
        "SELECT uuid, display_title, docType, parent_uuid FROM documents "
        "WHERE parent_uuid IS NOT NULL AND parent_uuid != '' LIMIT 15"):
    print("  ", row[1], "| docType=", row[2], "| parent=", str(row[3])[:12])

print("\n== 4) docType=1 页的 title/display_title 样例 ==")
for row in cur.execute(
        "SELECT uuid, title, display_title, schematic_uuid FROM documents "
        "WHERE docType=1 LIMIT 20"):
    print("  ", (row[1] or "")[:30], "|", (row[2] or "")[:30], "|",
          (row[3] or "")[:10])

print("\n== 5) schematics 表 ==")
cols = [r[1] for r in cur.execute("PRAGMA table_info(schematics)")]
print("  列:", cols)
for row in cur.execute("SELECT uuid, description FROM schematics LIMIT 12"):
    print("  ", row[0][:12], repr((row[1] or "")[:40]))
