"""sheet/symbol/device 缓存值结构采样。"""
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

print("== sheet 值类型与键 ==")
print(ev("""
var s=SCH.gVars.projectMgr.sheetCache.sheet;
var k=Object.keys(s)[0]; var v=s[k];
'type='+typeof v+' | '+(typeof v==='string'?
 'str len='+v.length+' head='+JSON.stringify(v.slice(0,80)) :
 'keys='+Object.keys(v).slice(0,25).join(','))
"""))
print("\n== symbol 值类型 ==")
print(ev("""
var c=SCH.gVars.projectMgr.componentCache.symbol;
var k=Object.keys(c)[0]; var v=c[k];
'type='+typeof v+' | '+(typeof v==='string'?
 'str len='+v.length+' head='+JSON.stringify(v.slice(0,80)) :
 'keys='+Object.keys(v).slice(0,25).join(','))
"""))
print("\n== device 值类型 ==")
print(ev("""
var d=SCH.gVars.projectMgr.componentCache.device;
var k=Object.keys(d)[0]; var v=d[k];
'type='+typeof v+' | '+(typeof v==='string'?
 'str len='+v.length+' head='+JSON.stringify(v.slice(0,80)) :
 'keys='+Object.keys(v).slice(0,25).join(','))
"""))
print("\n== instanceAttrMgr.savedData 结构 ==")
print(ev("""
var ia=SCH.gVars.projectMgr.instanceAttrMgr.savedData;
JSON.stringify(Object.keys(ia).map(function(k){
 var v=ia[k]; return {k:k, type:typeof v,
  keys: typeof v==='object'?Object.keys(v).slice(0,5):null});
}))
"""))
