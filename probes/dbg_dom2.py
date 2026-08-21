"""DOM 状态采样：可见文本/树节点结构。"""
import io, sys
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\probes")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cdp", r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\probes\cdp_eval.py")
cdp = importlib.util.module_from_spec(spec)
sys.argv = ["cdp"]
spec.loader.exec_module(cdp)

def ev(expr):
    return cdp.evaluate(expr)

print("body 文本长度:", ev("document.body.innerText.length"))
print("\n含 'ControlDAC' 的元素数（任意层级）:",
      ev("document.body.innerHTML.split('ControlDAC').length - 1"))
print("\n含 'Piezo' 的元素数:",
      ev("document.body.innerHTML.split('Piezo').length - 1"))
print("\n可见文本前 600:")
print(ev("document.body.innerText.replace(/\\n+/g,' | ').slice(0,600)"))
