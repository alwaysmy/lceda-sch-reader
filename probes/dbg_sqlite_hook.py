"""方案B：运行中挂 sqlite3/crypto 钩子，渲染层 reload 触发读库。
输出: probes/newfmt_sql_cap.json"""
import io, sys, json, time
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cdp", r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes\cdp_eval.py")
cdp = importlib.util.module_from_spec(spec)
sys.argv = ["cdp"]
spec.loader.exec_module(cdp)

import urllib.request

# ① 等待两个 target 都就绪
def wait_targets():
    for _ in range(20):
        try:
            targets = json.loads(urllib.request.urlopen(
                "http://127.0.0.1:9229/json/list", timeout=3).read().decode())
            node_t = next((t for t in targets if t.get("type") == "node"), None)
            pages = json.loads(urllib.request.urlopen(
                "http://127.0.0.1:9222/json/list", timeout=3).read().decode())
            page_t = next((t for t in pages
                           if t.get("type") == "page" and "/editor" in t.get("url", "")),
                          None)
            if node_t and page_t:
                return node_t, page_t
        except Exception:
            pass
        time.sleep(2)
    raise SystemExit("targets 未就绪")

HOOK = """
(function(){
  if (globalThis.__sqlHooked) return 'already';
  globalThis.__sqlHooked = true;
  globalThis.__cap = [];
  var req = process.mainModule ? process.mainModule.require : null;
  if (!req) return 'no require';
  var sq = null;
  try { sq = req('sqlite3'); } catch(e) {}
  if (!sq || !sq.Database) return 'sqlite3 不可达';
  var proto = sq.Database.prototype;
  ['all','get','run'].forEach(function(mn){
    var impl = proto[mn];
    proto[mn] = function(sql){
      var args = Array.prototype.slice.call(arguments, 1);
      var self = this;
      try {
        if (/history_data|documents|project_structures/i.test(String(sql))) {
          globalThis.__cap.push({m: mn, sql: String(sql).slice(0,200)});
          // 包装最后一个回调参数以捕获结果规模
          if (args.length && typeof args[args.length-1] === 'function') {
            var cb = args[args.length-1];
            args[args.length-1] = function(){
              try {
                var rows = arguments[1];
                var n = Array.isArray(rows) ? rows.length :
                        (rows ? Object.keys(rows).length : 0);
                var sample = '';
                if (Array.isArray(rows) && rows[0]) {
                  var d = rows[0].dataStr || '';
                  sample = String(d).slice(0,40);
                }
                globalThis.__cap.push({m: mn+'-done', rows: n,
                                       dsHead: sample});
              } catch(e){}
              return cb.apply(this, arguments);
            };
          }
        }
      } catch(e){}
      return impl.apply(this, args);
    };
  });
  return 'sqlite hooks installed';
})()
"""

node_t, page_t = wait_targets()
ws_n = cdp.WS(node_t["webSocketDebuggerUrl"])
ws_n.send_json({"id": 0, "method": "Runtime.enable"})
try:
    ws_n.recv_text()
except SystemExit:
    pass

def ev_n(expr, timeout=60):
    ws_n.send_json({"id": 77, "method": "Runtime.evaluate",
                    "params": {"expression": expr, "returnByValue": True,
                               "awaitPromise": True}})
    t0 = time.time()
    while time.time() - t0 < timeout:
        msg = json.loads(ws_n.recv_text())
        if msg.get("id") == 77:
            r = msg.get("result", {})
            if "exceptionDetails" in r:
                return "EXC: " + json.dumps(r["exceptionDetails"])[:200]
            return r.get("result", {}).get("value")
    raise SystemExit("超时")

print("主进程钩子:", ev_n(HOOK))

# 渲染层 reload 触发重新读库（若主进程有内存缓存则可能不触发）
ws_p = cdp.WS(page_t["webSocketDebuggerUrl"])
ws_p.send_json({"id": 0, "method": "Runtime.enable"})
try:
    ws_p.recv_text()
except SystemExit:
    pass
ws_p.send_json({"id": 88, "method": "Page.reload"})
time.sleep(30)

cap = ev_n("JSON.stringify(globalThis.__cap||[])")
data = json.loads(cap or "[]")
outp = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader"
        r"\probes\newfmt_sql_cap.json")
with open(outp, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print(f"捕获 {len(data)} 条 -> {outp}")
for d in data[:14]:
    print(json.dumps(d, ensure_ascii=False)[:160])
