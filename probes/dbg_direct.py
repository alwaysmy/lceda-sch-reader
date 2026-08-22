"""在编辑器运行时直接调用解码函数处理 history_data blob。"""
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

# 思路：找到 MGR 模块（pro-mgr），它有工程数据的读写能力
# 然后通过它调用底层解析器处理 blob

# 先看 MGR 全局对象的结构
r = ev("""
(function(){
  if (typeof MGR === 'undefined') return 'MGR 不存在';
  var keys = Object.keys(MGR);
  return 'MGR keys(' + keys.length + '): ' + keys.slice(0,30).join(',');
})()
""")
print("MGR:", r)

# 搜索 window 上所有含 "flowRead" 或 "parseFull" 的可调用对象
r = ev("""
(function(){
  var results = [];
  function scan(obj, path, depth) {
    if (!obj || depth > 2) return;
    try {
      var ks = Object.keys(obj);
      for (var i = 0; i < ks.length; i++) {
        try {
          var v = obj[ks[i]];
          if (typeof v === 'object' && v !== null) {
            if (typeof v.flowRead === 'function') {
              results.push(path + '.' + ks[i] + '.flowRead');
            }
            if (typeof v.parseFull === 'function') {
              results.push(path + '.' + ks[i] + '.parseFull');
            }
            scan(v, path + '.' + ks[i], depth + 1);
          }
        } catch(e){}
      }
    } catch(e){}
  }
  // 扫描 MGR 和 SCH
  if (typeof MGR !== 'undefined') scan(MGR, 'MGR', 0);
  if (typeof SCH !== 'undefined') scan(SCH.gVars, 'SCH.gVars', 0);
  return results.join('\\n') || '未找到';
})()
""")
print("\nflowRead/parseFull 持有者:\n", r)

# 尝试直接从 blob 读数据：用编辑器的内部 API
# projectMgr 应该有读取 history 的方法
r = ev("""
(function(){
  var pm = SCH.gVars.projectMgr;
  var methods = [];
  var proto = Object.getPrototypeOf(pm);
  while(proto) {
    Object.getOwnPropertyNames(proto).forEach(function(p){
      try{
        if(typeof pm[p]==='function' && /hist|read|load|blob|data/i.test(p))
          methods.push(p);
      }catch(e){}
    });
    proto = Object.getPrototypeOf(proto);
  }
  return Array.from(new Set(methods)).join(', ');
})()
""")
print("\nprojectMgr 历史/读取方法:", r)
