"""枚举 User_*_v6 库的 objectStore 与数据量。"""
import io, sys, json
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
t = next(x for x in targets if x["type"] == "page")
ws = cdp.WS(t["webSocketDebuggerUrl"])
ws.send_json({"id": 0, "method": "Runtime.enable"})
try:
    ws.recv_text()
except SystemExit:
    pass

def ev_await(expr, tid=2, timeout=120):
    ws.send_json({"id": tid, "method": "Runtime.evaluate",
                  "params": {"expression": expr, "returnByValue": True,
                             "awaitPromise": True}})
    import time
    t0 = time.time()
    while time.time() - t0 < timeout:
        msg = json.loads(ws.recv_text())
        if msg.get("id") == tid:
            r = msg.get("result", {})
            if "exceptionDetails" in r:
                print("EXC:", json.dumps(r["exceptionDetails"],
                                         ensure_ascii=False)[:300])
                return None
            return r.get("result", {}).get("value")
    raise SystemExit("超时")

r = ev_await("""
(function(){
  return new Promise(function(res){
    var req = indexedDB.open('User_493dbeb8f6b44b0094189fcd4b7be136_v6');
    req.onsuccess = function(){
      var db = req.result;
      var out = {stores: [], detail: []};
      var names = Array.from(db.objectStoreNames);
      out.stores = names;
      var pending = names.length;
      if (!pending) { res(JSON.stringify(out)); return; }
      names.forEach(function(sn){
        try {
          var tx = db.transaction(sn, 'readonly');
          var st = tx.objectStore(sn);
          var cntReq = st.count();
          cntReq.onsuccess = function(){
            var keysReq = st.getAllKeys(null, 5);
            keysReq.onsuccess = function(){
              out.detail.push({store: sn, count: cntReq.result,
                               keySample: keysReq.result});
              if (--pending === 0) res(JSON.stringify(out));
            };
          };
        } catch(e) {
          out.detail.push({store: sn, err: String(e)});
          if (--pending === 0) res(JSON.stringify(out));
        }
      });
    };
    req.onerror = function(){ res('open 失败'); };
  });
})()
""")
print(json.dumps(json.loads(r), ensure_ascii=False, indent=1)[:2000])
