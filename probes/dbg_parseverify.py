"""验证 parseFull 后的内部状态 + 尝试通过编辑器提取解析结果。"""
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

# 从 DB 读最小 blob
E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)
blobs = list(conn.execute("SELECT uuid, dataStr FROM history_data ORDER BY id"))
conn.close()
smallest = min(blobs, key=lambda x: len(x[1] or ""))
buuid, bdata = smallest

# 喂入 blob 并检查内部状态
r = ev(f"""
(async function(){{
  var b64 = {json.dumps(bdata)};
  var pm = SCH.gVars.projectMgr;
  var map = pm.schematicConsistencyManagerMap;
  var mgr = null;
  if (map instanceof Map) {{
    var first = map.entries().next();
    if (!first.done) mgr = first.value[1];
  }}
  if (!mgr) return {{error: 'no mgr'}};
  
  // 记录 parseFull 前的状态
  var cm = mgr.consistencyManager;
  var before = {{
    wDocDataSize: cm.wDocData ? cm.wDocData.size : 'N/A',
    maxTicket: cm.maxTicket
  }};
  
  // 调用 parseFull
  cm.parseFull(b64);
  
  // 记录 parseFull 后的状态
  var after = {{
    wDocDataSize: cm.wDocData ? cm.wDocData.size : 'N/A',
    maxTicket: cm.maxTicket
  }};
  
  // 提取 wDocData 的内容
  var docs = {{}};
  if (cm.wDocData) {{
    cm.wDocData.forEach(function(docData, docUuid) {{
      var entries = [];
      if (docData && typeof docData.forEach === 'function') {{
        docData.forEach(function(record, recordId) {{
          entries.push({{
            id: recordId,
            type: record.last ? record.last.dataType || 
                  (typeof record.last.data === 'string' ? 
                   record.last.data.slice(0,30) : 'obj') : 'empty',
            ticket: record.last ? record.last.ticket : null
          }});
        }});
      }} else if (typeof docData === 'object') {{
        Object.keys(docData).forEach(function(rid) {{
          var rec = docData[rid];
          entries.push({{
            id: rid,
            type: rec.last ? rec.last.dataType || 
                  (typeof rec.last.data === 'string' ? 
                   rec.last.data.slice(0,30) : 'obj') : 'empty',
            data_preview: rec.last && rec.last.data ? 
              String(rec.last.data).slice(0,80) : ''
          }});
        }});
      }}
      docs[docUuid] = {{entries: entries.length, sample: entries.slice(0,3)}};
    }});
  }}
  
  return {{before: before, after: after, docs: docs}};
}})()
""")
print(json.dumps(r, ensure_ascii=False, indent=1)[:3000])
