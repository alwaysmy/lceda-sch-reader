"""通过 schematicConsistencyManagerMap 找到可用的解析器并喂入 blob。"""
import io, sys, json, time, os, socket, sqlite3, base64
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
                print("EXC:", json.dumps(r["exceptionDetails"])[:400])
                return None
            return r.get("result", {}).get("value")
    return "(超时)"

# 1) 检查 schematicConsistencyManagerMap 的内容
r = ev("""
(function(){
  var pm = SCH.gVars.projectMgr;
  var map = pm.schematicConsistencyManagerMap;
  if (!map) return 'map 不存在';
  var keys = [];
  if (map instanceof Map) {
    map.forEach(function(v,k){ keys.push(k); });
  } else {
    keys = Object.keys(map);
  }
  return 'entries=' + keys.length + ' keys=' + keys.slice(0,5).join(',');
})()
""")
print("consistencyManagerMap:", r)

# 2) 取一个 consistencyManager 并检查其能力
r = ev("""
(function(){
  var pm = SCH.gVars.projectMgr;
  var map = pm.schematicConsistencyManagerMap;
  var mgr = null;
  if (map instanceof Map) {
    var first = map.entries().next();
    if (!first.done) mgr = first.value[1];
  } else {
    var ks = Object.keys(map);
    if (ks.length) mgr = map[ks[0]];
  }
  if (!mgr) return 'mgr 为空';
  var out = {};
  // 检查各层的方法
  ['base', 'consistencyManager', 'handler'].forEach(function(k){
    if (mgr[k]) {
      out[k] = Object.keys(mgr[k]).slice(0,10);
      out[k+'_hasParse'] = typeof mgr[k].parseFull === 'function';
      out[k+'_hasFlow'] = typeof mgr[k].flowRead === 'function';
    }
  });
  // 自身方法
  var proto = Object.getPrototypeOf(mgr);
  var methods = [];
  while(proto && proto !== Object.prototype) {
    Object.getOwnPropertyNames(proto).forEach(function(p){
      try{ if(typeof mgr[p]==='function') methods.push(p); }catch(e){}
    });
    proto = Object.getPrototypeOf(proto);
  }
  out.methods = Array.from(new Set(methods)).filter(function(p){
    return /parse|flow|read|decode|blob/i.test(p);});
  return JSON.stringify(out);
})()
""")
print("\nconsistencyManager 结构:", r)

# 3) 从 DB 读 blob 并尝试通过编辑器的解析器处理
E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)
blobs = list(conn.execute("SELECT uuid, dataStr FROM history_data ORDER BY id"))
conn.close()

# 用最小的 blob 测试
smallest = min(blobs, key=lambda x: len(x[1] or ""))
buuid, bdata = smallest
print(f"\n测试 blob: uuid={buuid[:20]}, len={len(bdata or '')}")

if bdata:
    # 尝试多种方式喂入
    expr = f"""
    (async function(){{
      var b64 = {json.dumps(bdata)};
      var results = {{}};
      
      // 方式1: 通过 instanceConsistencyManager
      try {{
        var icm = SCH.gVars.projectMgr.instanceConsistencyManager;
        if (icm && icm.base && icm.base.consistencyManager) {{
          var cm = icm.base.consistencyManager;
          if (typeof cm.parseFull === 'function') {{
            cm.parseFull(b64);
            results.method1 = 'parseFull 直接调用成功';
          }} else if (typeof cm.flowRead === 'function') {{
            var lines = [];
            await cm.flowRead(b64);
            results.method1 = 'flowRead 调用成功';
          }}
        }}
      }} catch(e) {{ results.method1 = 'ERR: ' + String(e).slice(0,100); }}
      
      // 方式2: 通过 schematicConsistencyManagerMap
      try {{
        var map = SCH.gVars.projectMgr.schematicConsistencyManagerMap;
        var mgr = null;
        if (map instanceof Map) {{
          var first = map.entries().next();
          if (!first.done) mgr = first.value[1];
        }}
        if (mgr && mgr.consistencyManager) {{
          var cm2 = mgr.consistencyManager;
          if (typeof cm2.parseFull === 'function') {{
            cm2.parseFull(b64);
            results.method2 = 'map.parseFull 成功';
          }}
        }}
      }} catch(e) {{ results.method2 = 'ERR: ' + String(e).slice(0,100); }}
      
      return JSON.stringify(results);
    }})()
    """
    r = ev(expr)
    print("解析结果:", r)
