"""主进程 Node CDP 侦察：history_data 原样读取 + 加密特征定位。"""
import io, sys, json, time, base64
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cdp", r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes\cdp_eval.py")
cdp = importlib.util.module_from_spec(spec)
sys.argv = ["cdp"]
spec.loader.exec_module(cdp)

import urllib.request
targets = json.loads(urllib.request.urlopen(
    "http://127.0.0.1:9229/json/list", timeout=5).read().decode())
node_t = next(t for t in targets if t.get("type") == "node")
ws = cdp.WS(node_t["webSocketDebuggerUrl"])
ws.send_json({"id": 0, "method": "Runtime.enable"})
try:
    ws.recv_text()
except SystemExit:
    pass

def ev(expr, tid=2, timeout=60):
    ws.send_json({"id": tid, "method": "Runtime.evaluate",
                  "params": {"expression": expr,
                             "returnByValue": True,
                             "awaitPromise": True,
                             "userGesture": True}})
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

# ① 主进程内搜加密相关 require 路径
print("== node_modules 加密库 ==")
print(ev("""
(function(){
  var out=[];
  try {
    var fs=require('fs'), path=require('path');
    var root='C:/Program Files/lceda-pro/resources/app/node_modules';
    fs.readdirSync(root).forEach(function(d){
      if (/crypt|aes|cipher|blow|tea|secret/i.test(d)) out.push(d);
    });
  } catch(e){ out.push('ERR '+e); }
  return out.join(', ');
})()
"""))

# ② 主进程搜源码级 decrypt 特征（app.js 已加载为函数/闭包，改搜全局+模块缓存）
print("\n== 主进程全局键采样 ==")
print(ev("""
Object.keys(global).filter(function(k){
  return /manager|project|doc|db|hist/i.test(k);}).slice(0,20).join(',')
"""))

# ③ 用 ORM 反射不可行的话：直接 sqlite3 读并确认密文一致（对照）
print("\n== 确认主进程可见的 history_data（经文件） ==")
print(ev("""
(function(){
  try {
    var Database = require('sqlite3').Database;
    return 'sqlite3 可用';
  } catch(e) { return 'sqlite3 不可用: ' + e.message; }
})()
"""))
