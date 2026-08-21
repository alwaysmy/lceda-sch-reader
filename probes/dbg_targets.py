"""枚举 CDP targets（含 worker）与主页面 iframe，定位真正的编辑器上下文。"""
import io, sys, json
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\probes")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cdp", r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\probes\cdp_eval.py")
cdp = importlib.util.module_from_spec(spec)
sys.argv = ["cdp"]
spec.loader.exec_module(cdp)

import urllib.request
targets = json.loads(urllib.request.urlopen(
    "http://127.0.0.1:9222/json/list", timeout=5).read().decode())
print("targets:")
for i, t in enumerate(targets):
    print(f"  [{i}] type={t['type']:8s} url={t.get('url','')[:70]} "
          f"title={t.get('title','')[:40]}")

print("\n主页面 iframe:")
v = cdp.evaluate(
    "Array.from(document.querySelectorAll('iframe')).map(f=>f.src.slice(0,90)).join('\\n')")
print(v or "(无)")

# 逐 worker 探全局键
for i, t in enumerate(targets):
    if t["type"] != "worker":
        continue
    try:
        v = cdp.evaluate(
            "Object.keys(self).filter(k=>/SCH|PCB|doc|Doc|lceda|eda/i.test(k))"
            ".slice(0,20).join(',') + ' || location:' + (self.location ? self.location.href.slice(0,60) : 'n/a')",
            t["webSocketDebuggerUrl"])
        print(f"\nworker[{i}]: {v}")
    except Exception as e:
        print(f"worker[{i}] 失败: {str(e)[:80]}")
