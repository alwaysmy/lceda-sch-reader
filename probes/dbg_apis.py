"""SCH.gVars.apis 探查（官方自动化 API 入口）。"""
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

print("== apis 类型/键 ==")
print(ev("""
var a=SCH.gVars.apis;
typeof a+' | '+(a? (Array.isArray(a)?'数组['+a.length+']':
 (a.prototype? 'class fn':'obj keys='+Object.keys(a).slice(0,40).join(','))):'null')
"""))
print("\n== apis 二层 ==")
print(ev("""
var a=SCH.gVars.apis;
a&&a.prototype? Object.getOwnPropertyNames(a.prototype).slice(0,60).join(',') :
 (a? Object.getOwnPropertyNames(a).slice(0,60).join(','):'-')
"""))
print("\n== doCommand 线索 ==")
print(ev("typeof SCH.doCommand + ' | ' + SCH.doCommand.toString().slice(0,200)"))
