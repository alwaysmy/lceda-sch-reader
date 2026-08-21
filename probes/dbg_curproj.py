"""currentProject / FileDataStr / projectMgr 深挖。"""
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

print("== currentProject ==")
print(ev("""
var cp=SCH.gVars.currentProject;
typeof cp+' | '+(cp?Object.keys(cp).slice(0,50).join(','):'null')
"""))
print("\n== FileDataStr ==")
print(ev("""
var f=SCH.gVars.FileDataStr;
typeof f+' | '+(f?(typeof f==='object'?Object.keys(f).slice(0,30).map(function(k){
 var v=f[k]; var s=typeof v==='string'?('str['+v.length+']:'+v.slice(0,40)):typeof v;
 return k+'='+s;}).join('\\n'):String(f).slice(0,200)):'null')
"""))
print("\n== projectMgr ==")
print(ev("""
var pm=SCH.gVars.projectMgr;
typeof pm+' | '+(pm?Object.keys(pm).slice(0,40).join(','):'null')
"""))
