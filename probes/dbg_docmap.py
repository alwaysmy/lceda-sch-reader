"""docMap 深挖：键列表 + 值结构（多行输出版）。"""
import io, sys, json
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\probes")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cdp", r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\probes\cdp_eval.py")
cdp = importlib.util.module_from_spec(spec)
sys.argv = ["cdp"]
spec.loader.exec_module(cdp)

def ev(expr):
    return cdp.evaluate(expr)

keys = ev("Object.keys(SCH.docMemoryManager.docMap)")
print("docMap 键数:", len(keys) if keys else 0)
for k in (keys or [])[:40]:
    print("  ", k)
if keys:
    k0 = keys[0]
    js = f"""
    var d = SCH.docMemoryManager.docMap[{json.dumps(k0)}];
    'type='+typeof d+' | '+Object.keys(d).slice(0,30).join(',')
    """
    print("\n首个值结构:", ev(js))
