"""MGR 上下文深挖：结构 + history 相关方法。"""
import io, sys, json, time, socket
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
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
                  "params": {"expression": expr, "returnByValue": True,
                             "awaitPromise": True}})
    ws.sock.settimeout(20)
    t0 = time.time()
    while time.time() - t0 < 20:
        try:
            m = json.loads(ws.recv_text())
        except socket.timeout:
            return None
        if m.get("id") == myid:
            r = m.get("result", {})
            if "exceptionDetails" in r:
                return "EXC: " + json.dumps(r["exceptionDetails"])[:200]
            return r.get("result", {}).get("value")
    return None

# 收集 sessions
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

# 找含 MGR 的 session
target_sid = None
for si in list(sessions)[-len(workers):]:
    v = None
    try:
        v = rpc_eval("typeof MGR", si)
    except Exception:
        pass
    print(f"session {si[:14]} type={sessions[si]} MGR={v}")
    if v == "object":
        target_sid = si

if not target_sid:
    raise SystemExit("未找到 MGR 上下文")

sid = target_sid
print("\n== MGR 键 ==")
print(rpc_eval("Object.keys(MGR).slice(0,50).join(',')", sid))
print("\n== history 相关 ==")
print(rpc_eval("""
(function(){
  var out=[];
  function scan(o, name){
    try {
      Object.getOwnPropertyNames(o).forEach(function(p){
        try{
          var v=o[p];
          if (/history/i.test(p)) out.push(name+'.'+p+':'+typeof v);
          else if (v && typeof v==='object' && depth<2) scan(v, name+'.'+p);
        }catch(e){}
      });
    } catch(e){}
  }
  var depth=0;
  Object.keys(MGR).forEach(function(k){
    try{ if (MGR[k] && typeof MGR[k]==='object'){
      Object.keys(MGR[k]).forEach(function(p){
        if (/history/i.test(p)) out.push(k+'.'+p+':'+typeof MGR[k][p]);
      });
    }}catch(e){}
  });
  return out.join('\\n') || '无';
})()
""", sid))
