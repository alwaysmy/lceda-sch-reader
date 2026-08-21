"""提取 doCommand 中 case"open"/openTemplatePage/sheet(toPage) 的实现片段。"""
import io, sys, re
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\probes")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cdp", r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\probes\cdp_eval.py")
cdp = importlib.util.module_from_spec(spec)
sys.argv = ["cdp"]
spec.loader.exec_module(cdp)

src = cdp.evaluate("SCH.doCommand.toString()")
for key in ('case"open":', 'case"openTemplatePage":', 'case"openCBB":',
            '"sheet(toPage)"'):
    i = src.find(key)
    if i < 0:
        print(f"未找到 {key}")
        continue
    seg = src[i:i + 500]
    print(f"== {key} ==\n{seg}\n")
