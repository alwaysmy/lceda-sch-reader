import io, json, subprocess, sys, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

TOOL = r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\lceda_reader.py"
NEW = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"

def run(cmd):
    r = subprocess.run([sys.executable, TOOL, "--eprj", NEW] + cmd,
                       capture_output=True, text=True, encoding="utf-8")
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"ERR": r.stdout[:200]}

# 1) 同名页库内记录
conn = sqlite3.connect(f"file:{NEW}?mode=ro", uri=True)
rows = conn.execute("SELECT uuid, display_title, schematic_uuid FROM documents WHERE display_title='激励输出和AD采集' AND docType=1").fetchall()
print("== 同名页记录 ==")
for u, t, s in rows:
    nm = conn.execute("SELECT name FROM schematics WHERE uuid=?", (s,)).fetchone()[0]
    print(f"  uuid={u[:8]} sch={nm}")
conn.close()

# 2) pinmap 不带 schematic：应只取第一个匹配
a = run(["--json", "pinmap", "激励输出和AD采集"])
print("\n== pinmap 无 --schematic: {} 个元件 ==".format(len(a)))

# 3) 用 uuid 直接 pinmap（等价于 --schematic 指定后的行为）
u1 = rows[0][0]
u2 = rows[1][0]
b = run(["--json", "pinmap", u1])
c = run(["--json", "pinmap", u2])
print("== 按 uuid 读取 ==")
print(f"  uuid1={u1[:8]}: {len(b)} 元件")
print(f"  uuid2={u2[:8]}: {len(c)} 元件")
print("  内容相同?" , b == c)

# 4) --schematic 区分
d = run(["--json", "pinmap", "激励输出和AD采集", "--schematic", "schematic1"])
e = run(["--json", "pinmap", "激励输出和AD采集", "--schematic", "schematic1_2"])
print("\n== --schematic 区分 ==")
print(f"  schematic1: {len(d)} 元件")
print(f"  schematic1_2: {len(e)} 元件")
print("  不同内容?", d != e)