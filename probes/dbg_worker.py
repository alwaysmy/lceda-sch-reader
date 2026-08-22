"""worker 直连诊断：不发 enable，直接 evaluate，打印全部回包。"""
import io, sys, json, time
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cdp", r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes\cdp_eval.py")
cdp = importlib.util.module_from_spec(spec)
sys.argv = ["cdp"]
spec.loader.exec_module(cdp)

import urllib.request
targets = json.loads(urllib.request.urlopen(
    "http://127.0.0.1:9222/json/list", timeout=5).read().decode())
workers = [t for t in targets if t["type"] == "worker"]

for i, t in enumerate(workers):
    print(f"== worker[{i}] {t['webSocketDebuggerUrl'][-20:]} ==")
    try:
        ws = cdp.WS(t["webSocketDebuggerUrl"])
        ws.send_json({"id": 1, "method": "Runtime.evaluate",
                      "params": {"expression":
                                 "Object.keys(self).length + ':' + "
                                 "typeof self.SCH",
                                 "returnByValue": True}})
        t0 = time.time()
        while time.time() - t0 < 15:
            try:
                msg = ws.recv_text()
            except SystemExit:
                print("   closed"); break
            m = json.loads(msg)
            if m.get("id") == 1:
                res = m.get("result", {}).get("result", {})
                print("   结果:", res.get("value",
                      json.dumps(res)[:150]))
                break
            else:
                print("   事件:", msg.get("method"),
                      str(msg)[:100])
        else:
            print("   超时(15s)")
    except Exception as e:
        print("   失败:", type(e).__name__, str(e)[:80])
