"""apis.components/eda 二层方法枚举 + doCommand 命令名探测。"""
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

for sec in ("components", "eda", "others", "hw"):
    print(f"== apis.{sec} ==")
    print(ev(f"""
var a=SCH.gVars.apis.{sec};
typeof a+' | '+(a?Object.getOwnPropertyNames(a).filter(function(p){{
 try{{return typeof a[p]==='function'}}catch(e){{return false}}}}).slice(0,50).join(','):'-')
"""))
