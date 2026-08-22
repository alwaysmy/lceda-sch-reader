"""完整实测：全部 CBB 实例的内部器件位号（含型号），按板/实例分组。"""
import io, sys, json, subprocess, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
R = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\lceda_reader.py"
E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"

p = subprocess.run(
    [sys.executable, R, "--eprj", E, "--json", "netlist"],
    capture_output=True, text=True, encoding="utf-8")
rows = json.loads(p.stdout)

# 收集展开条目
cbb_members = collections.defaultdict(set)
for r in rows:
    for c in r["components"]:
        if "." in c:
            prefix, member = c.split(".", 1)
            if prefix.startswith("CBB"):
                cbb_members[prefix].add(member)

# 获取器件信息
p = subprocess.run(
    [sys.executable, R, "--eprj", E, "--json", "devmap"],
    capture_output=True, text=True, encoding="utf-8")

# 按模板分组输出
templates = collections.defaultdict(lambda: {"instances": [], "members": set()})
for prefix in sorted(cbb_members):
    # 从 netlist 找该实例所在页 → 推断模板
    tmpl = None
    for r in rows:
        for c in r["components"]:
            if c == prefix or c.startswith(prefix + "."):
                for s in r["sheets"]:
                    pass
                break
            break

    # 用已知映射
    known = {
        "CBB6": "_CBB_MAX5318_2L", "CBB7": "_CBB_MAX5318_2L",
        "CBB8": "_CBB_MAX5318_2L", "CBB9": "_CBB_MAX5318_2L",
        "CBB10": "_CBB_ADHV4702__NOINV_2L", "CBB11": "_CBB_ADHV4702__NOINV_2L",
        "CBB12": "_CBB_ADHV4702__NOINV_2L", "CBB13": "_CBB_ADHV4702__NOINV_2L",
        "CBB14": "_CBB_ADHV4702__NOINV_2L", "CBB15": "_CBB_ADHV4702__NOINV_2L",
        "CBB1": "(4pin 电源模板之一)", "CBB2": "(4pin 电源模板之一)",
        "CBB3": "(4pin 电源模板之一)", "CBB4": "(4pin 电源模板之一)",
        "CBB5": "(4pin 电源模板之一)",
    }
    tmpl = known.get(prefix, "?")
    templates[tmpl]["instances"].append(prefix)
    templates[tmpl]["members"].update(cbb_members[prefix])

print("== quadPizeoDriver_RevA 全部 CBB 实例的内部器件 ==")
for tmpl in sorted(templates):
    info = templates[tmpl]
    insts = ",".join(sorted(info["instances"]))
    members = sorted(info["members"])
    print(f"\n  模板: {tmpl}")
    print(f"  实例: {insts}")
    print(f"  内部器件 ({len(members)} 个): {', '.join(members)}")
