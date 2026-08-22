"""DEVICE 缓存值内部结构探查。"""
import io, sys, json
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cdp", r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes\cdp_eval.py")
cdp = importlib.util.module_from_spec(spec)
sys.argv = ["cdp"]
spec.loader.exec_module(cdp)

def ev(expr):
    return cdp.evaluate(expr)

print(ev("""
var d=SCH.gVars.projectMgr.componentCache.device;
var k=Object.keys(d)[0]; var v=d[k];
JSON.stringify({
 uuid:k,
 path:v.path,
 cacheType:typeof v.cache,
 cacheKeys:v.cache?Object.keys(v.cache).slice(0,10):null,
 baseKeys:v.base?Object.keys(v.base).slice(0,12):null,
 deviceResultType:typeof v.deviceResult,
 deviceResultKeys:v.deviceResult?Object.keys(v.deviceResult).slice(0,12):null,
}, null, 1)
"""))
print("\n== deviceResult 内容采样 ==")
print(ev("""
var d=SCH.gVars.projectMgr.componentCache.device;
var k=Object.keys(d)[0]; var v=d[k];
var r=v.deviceResult||v.cache||{};
JSON.stringify(r).slice(0,600)
"""))
