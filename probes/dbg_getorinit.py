"""getOrInitDoc 源码 + 定位真正的文档拉取函数。"""
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

print("== getOrInitDoc source ==")
print(ev("SCH.docMemoryManager.getOrInitDoc.toString().slice(0,800)"))
print("\n== _docFetchPromiseMap 现状 ==")
print(ev("""
var dm=SCH.docMemoryManager;
'keys='+Object.keys(dm._docFetchPromiseMap).length+' sample='+
 Object.keys(dm._docFetchPromiseMap).slice(0,3).join(',')
"""))
