"""找文档内容读取路径：projectMgr 原型方法 / device.cache 结构 / doc_id 线索。"""
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

print("== sheet 完整键 ==")
print(ev("""
var s=SCH.gVars.projectMgr.sheetCache.sheet;
var k=Object.keys(s)[0]; Object.keys(s[k]).join(',')
"""))
print("\n== projectMgr 原型函数名（含 doc/read/get/fetch） ==")
print(ev("""
var pm=SCH.gVars.projectMgr;
var names=new Set();
var o=pm; var n=0;
while(o && n<4){ Object.getOwnPropertyNames(o).forEach(function(p){
 try{ if(typeof pm[p]==='function' && /doc|read|get|fetch|load/i.test(p)) names.add(p);}catch(e){} });
 o=Object.getPrototypeOf(o); n++; }
Array.from(names).slice(0,40).join(',')
"""))
print("\n== device[k].cache/base 结构 ==")
print(ev("""
var d=SCH.gVars.projectMgr.componentCache.device;
var k=Object.keys(d)[0]; var v=d[k];
'cache: '+typeof v.cache+' | '+(v.cache?Object.keys(v.cache).slice(0,10).join(','):'-')
 + ' || base: '+typeof v.base+' | '+(v.base?Object.keys(v.base).slice(0,10).join(','):'-')
"""))
print("\n== SCH.docMemoryManager 原型方法 ==")
print(ev("""
var dm=SCH.docMemoryManager; var names=[];
var o=dm; var n=0;
while(o && n<3){ Object.getOwnPropertyNames(o).forEach(function(p){
 try{ if(typeof dm[p]==='function') names.push(p);}catch(e){} });
 o=Object.getPrototypeOf(o); n++; }
Array.from(new Set(names)).join(',')
"""))
