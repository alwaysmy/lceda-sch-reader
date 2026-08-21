"""枚举脚本资源 + messageBus 频道名（从 doCommand 源码提取 publish 频道）。"""
import io, sys, re
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\probes")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cdp", r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\probes\cdp_eval.py")
cdp = importlib.util.module_from_spec(spec)
sys.argv = ["cdp"]
spec.loader.exec_module(cdp)

def ev(expr):
    return cdp.evaluate(expr)

print("== 脚本资源 URL ==")
print(ev("""
performance.getEntriesByType('resource').map(function(r){return r.name})
 .filter(function(n){return /ui\\.js|pro-ui/.test(n)}).slice(0,5).join('\\n')
"""))
src = cdp.evaluate("SCH.doCommand.toString()")
pubs = sorted(set(re.findall(r'publish\("([^"]+)"', src)))
print("\n== messageBus 频道（doCommand 内） ==")
print(len(pubs), pubs[:40])
# 找含 open/page/sheet 的频道
rel = [p for p in pubs if re.search(r"open|page|sheet|doc", p, re.I)]
print("相关:", rel)
