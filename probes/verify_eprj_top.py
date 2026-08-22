import io, json, subprocess, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

TOOL = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\lceda_reader.py"
NEW = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"
OLD = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2"

def run(cmd):
    r = subprocess.run([sys.executable, TOOL] + cmd, capture_output=True,
                       text=True, encoding="utf-8")
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"ERR": r.stdout[:300], "rc": r.returncode}

print("== 单工程结构兼容 ==")
j = run(["--eprj", NEW, "--json", "find", "U28"])
print("find U28: is list:", isinstance(j, list), "len:", len(j))
j = run(["--eprj", NEW, "--json", "search", "LTC6655"])
print("search: is list:", isinstance(j, list), "len:", len(j))
j = run(["--eprj", NEW, "--json", "netfind", "3V3"])
print("netfind 3V3: is list:", isinstance(j, list), "len:", len(j))

print("\n== 多工程顶层 ==")
j = run(["--eprj", NEW, "--eprj", OLD, "--json", "find", "U1"])
print("find: keys:", list(j.keys()))
for p in j["projects"]:
    print(f"  eprj{p['eprj']}: {p['project']} <- {p['file'].split(chr(92))[-1]}")
print("rows:", len(j["rows"]))
j = run(["--eprj", NEW, "--eprj", OLD, "--json", "netfind", "3V3"])
print("netfind: keys:", list(j.keys()), "rows:", len(j["rows"]))