"""sheetCache.sheet / componentCache.symbol / instanceAttrMgr.savedData 展开。"""
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

print("== sheetCache.sheet ==")
print(ev("""
var s=SCH.gVars.projectMgr.sheetCache.sheet;
typeof s+' | '+(s?(Array.isArray(s)?'数组['+s.length+']':Object.keys(s).slice(0,20).join(',')):'null')
"""))
print("\n== componentCache.symbol 键 ==")
print(ev("""
var c=SCH.gVars.projectMgr.componentCache.symbol;
typeof c+' | '+(c?Object.keys(c).length+' 键: '+Object.keys(c).slice(0,6).join(','):'null')
"""))
print("\n== componentCache.device 键 ==")
print(ev("""
var d=SCH.gVars.projectMgr.componentCache.device;
typeof d+' | '+(d?Object.keys(d).length+' 键: '+Object.keys(d).slice(0,6).join(','):'null')
"""))
print("\n== instanceAttrMgr.savedData/unsavedData ==")
print(ev("""
var ia=SCH.gVars.projectMgr.instanceAttrMgr;
'saved:'+typeof ia.savedData+' keys='+Object.keys(ia.savedData||{}).length+
 ' | unsaved:'+typeof ia.unsavedData+' keys='+Object.keys(ia.unsavedData||{}).length
"""))
