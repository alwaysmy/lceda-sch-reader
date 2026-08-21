"""SCH 模块深挖：app/SchDocManager/gVars 结构与文档数据定位。"""
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

print("== SCH.app ==")
print(ev("typeof SCH.app + ' | ' + Object.keys(SCH.app||{}).slice(0,40).join(',')"))
print("\n== SchDocManager ==")
print(ev("typeof SCH.SchDocManager + ' | ' + "
         "Object.keys(SCH.SchDocManager||{}).slice(0,40).join(',')"))
print("\n== gVars 键 ==")
print(ev("Object.keys(SCH.gVars||{}).slice(0,40).join(',')"))
print("\n== RPC 对象自有属性(含函数) ==")
print(ev("""
var k='/542034058334d75e/project/8cfe3e92d7123712ba7d4a69b766d44daa839e24783f8cb2bd52a12e717f535e';
var o=window[k]; Object.getOwnPropertyNames(o).map(function(p){
 return p+':'+(typeof o[p]==='function'?'fn':typeof o[p]);}).join(' ')
"""))
print("\n== 全局搜含 doc 的深层引用（采样 window 大对象） ==")
print(ev("""
Object.keys(window).filter(function(k){
 try{ var v=window[k]; return v && typeof v==='object' &&
   Object.keys(v).length>20 && /manager|editor|doc/i.test(k); }catch(e){return false}
}).join(',')
"""))
