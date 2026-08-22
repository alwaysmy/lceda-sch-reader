"""从 SCH.doCommand 源码提取命令名（open/page 相关）。"""
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

src = ev("SCH.doCommand.toString()")
print("doCommand 源码长度:", len(src))
import re
cases = re.findall(r'case"([^"]+)"', src)
print("case 总数:", len(cases))
opens = [c for c in cases if "open" in c.lower() or "page" in c.lower()
         or "sheet" in c.lower() or "doc" in c.lower()]
print("open/page/doc 相关:", opens)
