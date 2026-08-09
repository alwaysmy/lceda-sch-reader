import sqlite3
conn = sqlite3.connect(r'D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2')
cur = conn.cursor()
row = cur.execute("SELECT display_title, dataStr FROM documents WHERE docType=1 AND display_title='高速AD'").fetchone()
print(row[0])
print(repr(row[1][:2000]))
