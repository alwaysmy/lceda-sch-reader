"""逐 worker 全局键采样。"""
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
              "params": {"autoAttach": True, "flatten": True}})
time.sleep(1)
workers = [t for t in targets if t.get("type") == "worker"]
for i, w in enumerate(workers):
    ws.send_json({"id": 100+i, "method": "Target.attachToTarget",
                  "params": {"targetId": w["id"], "flatten": True}})
sessions = {}
mid = 500

def rpc_eval(expr, sid):
    global mid
    mid += 1
    myid = mid
    ws.send_json({"sessionId": sid, "id": myid,
                  "method": "Runtime.evaluate",
                  "params": {"expression": expr, "returnByValue": True}})
    ws.sock.settimeout(15)
    t0 = time.time()
    while time.time() - t0 < 15:
        try:
            m = json.loads(ws.recv_text())
        except socket.timeout:
            return None
        if m.get("id") == myid:
            r = m.get("result", {})
            if "exceptionDetails" in r:
                return "EXC"
            return r.get("result", {}).get("value")
    return None

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

for si in sessions:
    v = rpc_eval("""
      (function(){
        var ks = Object.keys(self);
        var interesting = ks.filter(function(k){
          return /mgr|project|doc|hist|crypt|decrypt|pako|db/i.test(k);
        });
        return 'total='+ks.length+' | '+interesting.slice(0,20).join(',');
      })()
    """, si)
    print(f"[{sessions.get(si,'?')} {si[:12]}] {v}")
