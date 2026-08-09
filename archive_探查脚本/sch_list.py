import sqlite3, json
conn = sqlite3.connect(r'D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2')
cur = conn.cursor()
print("== SCHEMATICS ==")
for r in cur.execute('SELECT name, display_name, sheet_count, description FROM schematics'):
    print(r)
print()
print("== DOCUMENTS (sheets) ==")
for r in cur.execute('SELECT display_title, docType, length(dataStr) FROM documents'):
    print(r)
