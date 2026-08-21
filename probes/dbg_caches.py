"""sheetCache / componentCache / instanceAttrMgr / isV2Format 深挖。"""
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

print("== currentProject 元信息 ==")
print(ev("""
var cp=SCH.gVars.currentProject;
JSON.stringify({isV2Format:cp.isV2Format,isCBB:cp.isCBB,title:cp.title,
 branchUuid:cp.branchUuid})
"""))
print("\n== sheetCache ==")
print(ev("""
var sc=SCH.gVars.projectMgr.sheetCache;
typeof sc+' | '+(sc?Object.keys(sc).length+' 键: '+Object.keys(sc).slice(0,8).join(','):'null')
"""))
print("\n== componentCache ==")
print(ev("""
var cc=SCH.gVars.projectMgr.componentCache;
typeof cc+' | '+(cc?Object.keys(cc).length+' 键: '+Object.keys(cc).slice(0,8).join(','):'null')
"""))
print("\n== instanceAttrMgr ==")
print(ev("""
var ia=SCH.gVars.projectMgr.instanceAttrMgr;
typeof ia+' | '+(ia?Object.keys(ia).slice(0,30).join(','):'null')
"""))
