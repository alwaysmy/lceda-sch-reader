"""直接调用编辑器内部的 flowRead 解码 history_data blob。"""
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

# 从 DB 读 blob（base64 字符串）
E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)
blobs = list(conn.execute(
    "SELECT uuid, dataStr FROM history_data ORDER BY id"))
conn.close()

print(f"blobs: {len(blobs)}")

# 取最小的 blob 先测试
smallest = min(blobs, key=lambda x: len(x[1] or ""))
buuid, bdata = smallest
print(f"测试 blob: uuid={buuid[:20]}, base64_len={len(bdata or '')}")

if not bdata:
    print("blob 为空")
    sys.exit(1)

# 在编辑器中调用 flowRead 解码
expr = f"""
(async function(){{
  var b64 = {json.dumps(bdata)};
  var lines = [];
  var frm = SCH.gVars.projectMgr;
  if (!frm) {{
    // 尝试通过 projectMgr 找
    var icm = SCH.gVars.projectMgr.instanceConsistencyManager;
    if (icm && icm.base && icm.base.flowRead) {{
      await icm.base.flowRead(b64, {{update: function(line) {{
        lines.push(line);
      }}}});
      return {{method: 'icm.base.flowRead', lines: lines.length,
               sample: lines.slice(0,5).map(function(l){{
                 return typeof l === 'string' ? l.slice(0,100) : JSON.stringify(l).slice(0,100);
               }})}};
    }}
  }}
  return {{error: 'flowRead 不可达'}};
}})()
"""
r = ev(expr)
print(json.dumps(r, ensure_ascii=False, indent=1)[:2000] if r else "None")
