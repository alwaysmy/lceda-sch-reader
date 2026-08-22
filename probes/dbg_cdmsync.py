"""createDocManagerWithRealTimeSync 源码分析。"""
import io, sys
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cdp", r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes\cdp_eval.py")
cdp = importlib.util.module_from_spec(spec)
sys.argv = ["cdp"]
spec.loader.exec_module(cdp)

print(cdp.evaluate(
    "SCH.docMemoryManager.createDocManagerWithRealTimeSync"
    ".toString().slice(0, 1200)"))
