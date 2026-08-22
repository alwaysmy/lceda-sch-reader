"""探索 MGR.CommonDB 和 instanceConsistencyManager 的实际结构。"""
import io, sys, json, time, os, socket
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
t = next(x for x in targets if x["type"] == "page")

ws = cdp.WS(t["webSocketDebuggerUrl"])
mid = [0]

def ev(expr, timeout=120):
    mid[0] += 1
    ws.send_json({"id": mid[0], "method": "Runtime.evaluate",
                  "params": {"expression": expr, "returnByValue": True,
                             "awaitPromise": True}})
    ws.sock.settimeout(timeout)
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            m = json.loads(ws.recv_text())
        except socket.timeout:
            break
        if m.get("id") == mid[0]:
            r = m.get("result", {})
            if "exceptionDetails" in r:
                print("EXC:", json.dumps(r["exceptionDetails"])[:300])
                return None
            return r.get("result", {}).get("value")
    return "(超时)"

# 1) MGR.CommonDB 结构
r = ev("""
(function(){
  if (typeof MGR === 'undefined' || !MGR.CommonDB) return 'MGR.CommonDB 不存在';
  var db = MGR.CommonDB;
  var out = {type: typeof db};
  if (typeof db === 'object') {
    out.keys = Object.keys(db).slice(0,20);
    // 检查方法
    var methods = [];
    var proto = Object.getPrototypeOf(db);
    while(proto && proto !== Object.prototype) {
      Object.getOwnPropertyNames(proto).forEach(function(p){
        try{ if(typeof db[p]==='function') methods.push(p); }catch(e){}
      });
      proto = Object.getPrototypeOf(proto);
    }
    out.methods = Array.from(new Set(methods)).slice(0,30);
  }
  return JSON.stringify(out);
})()
""")
print("MGR.CommonDB:", r)

# 2) projectMgr 的全部子对象树（找 consistencyManager）
r = ev("""
(function(){
  var pm = SCH.gVars.projectMgr;
  if (!pm) return 'projectMgr 不存在';
  var results = [];
  function scan(obj, path, depth) {
    if (!obj || depth > 2) return;
    try {
      Object.keys(obj).forEach(function(k){
        if (/consist|flow|decode|blob/i.test(k)) {
          results.push(path + '.' + k + ' (' + typeof obj[k] + ')');
        }
        try {
          var v = obj[k];
          if (v && typeof v === 'object' && depth < 2) {
            scan(v, path + '.' + k, depth + 1);
          }
        } catch(e){}
      });
    } catch(e){}
  }
  scan(pm, 'pm', 0);
  return results.join('\\n') || '未找到';
})()
""")
print("\nprojectMgr 中 consist/flow/decode 相关:\n", r)

# 3) 检查已加载的 docManager 的 consistencyManager
r = ev("""
(async function(){
  var su = Object.keys(SCH.gVars.projectMgr.sheetCache.sheet)[0];
  var dm = await SCH.docMemoryManager.getOrInitDoc(su);
  var ci = dm.consistencyImpl;
  if (!ci) return '无 consistencyImpl';
  var out = {};
  // base 属性
  if (ci.base) {
    out.baseType = typeof ci.base;
    out.baseKeys = Object.keys(ci.base).slice(0,15);
    out.hasFlowRead = typeof ci.base.flowRead === 'function';
    out.hasParseFull = typeof ci.base.parseFull === 'function';
  }
  // manager 属性
  if (ci.manager) {
    out.mgrType = typeof ci.manager;
    out.mgrKeys = Object.keys(ci.manager).slice(0,15);
  }
  return JSON.stringify(out);
})()
""")
print("\ndocManager.consistencyImpl:", r)
