"""worker flatten attach + evaluate（完整版）。"""
import io, sys, json, time, socket
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
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
ver = json.loads(urllib.request.urlopen(
    "http://127.0.0.1:9222/json/version", timeout=5).read().decode())
ws = cdp.WS(ver["webSocketDebuggerUrl"])

ws.send_json({"id": 1, "method": "Target.setAutoAttach",
              "params": {"autoAttach": True, "flatten": True,
                         "waitForDebuggerOnStart": False}})
time.sleep(1)
workers = [t for t in targets if t.get("type") == "worker"]
sessions = {}
for i, w in enumerate(workers):
    ws.send_json({"id": 100+i, "method": "Target.attachToTarget",
                  "params": {"targetId": w["id"], "flatten": True}})

# 收 attach 响应
ws.sock.settimeout(5)
t0 = time.time()
try:
    while time.time() - t0 < 8 and len(sessions) < len(workers):
        m = json.loads(ws.recv_text())
        if m.get("method") == "Target.attachedToTarget":
            sessions[m["params"]["sessionId"]] = \
                m["params"]["targetInfo"].get("type")
except socket.timeout:
    pass

print("attached:", len(sessions))
# 逐 session evaluate
expr = ("Object.keys(self).filter(function(k){"
        "return /SCH|mgr|project|doc/i.test(k)}).slice(0,12).join(',') "
        "+ ' | total=' + Object.keys(self).length")
mid = 500
pending = {}
out = {}
for si in sessions:
    mid += 1
    pending[mid] = si
    ws.send_json({"sessionId": si, "id": mid, "method": "Runtime.evaluate",
                  "params": {"expression": expr, "returnByValue": True}})
ws.sock.settimeout(15)
t0 = time.time()
while pending and time.time() - t0 < 20:
    try:
        m = json.loads(ws.recv_text())
    except socket.timeout:
        break
    if "id" in m and m["id"] in pending:
        si = pending.pop(m["id"])
        r = m.get("result", {})
        val = r.get("result", {}).get("value",
              json.dumps(r)[:120])
        out[si] = val
for si, v in out.items():
    print(f"  [{sessions.get(si,'?')}] {v}")
