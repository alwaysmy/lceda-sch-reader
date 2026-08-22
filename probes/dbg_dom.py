"""DOM 路线：定位左侧工程树节点并模拟双击打开页。"""
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

# 找包含 ControlDAC_A 文本的最内层元素
r = ev("""
(function(){
 var els=Array.from(document.querySelectorAll('*')).filter(function(e){
  return e.children.length===0 && e.textContent.trim()==='ControlDAC_A';});
 return els.slice(0,5).map(function(e){
  return e.tagName+'.'+String(e.className).slice(0,60);}).join('\\n');
})()
""")
print("候选元素:\n", r)
