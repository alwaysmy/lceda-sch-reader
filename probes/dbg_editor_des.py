"""从编辑器内存中直接读取 CBB6 所在页的全部器件位号。
方法：通过 CDP 在编辑器页面中遍历 docManager 的 shapeManager.modelMap，
提取全部 COMPONENT 的 designator 和 device 信息。"""
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

# ① 确认 ControlDAC_A 页的 docManager 已加载
r = ev("""
(async function(){
  var pm = SCH.gVars.projectMgr;
  var su = null;
  // 找 quadPizeoDriver_RevA 的 ControlDAC_A 页
  Object.keys(pm.sheetCache.sheet).forEach(function(k){
    var s = pm.sheetCache.sheet[k];
    if (s.title === 'ControlDAC_A' && s.schematic_uuid) {
      // 检查是否属于 RevA（非 _1/_1.1）
      var schMeta = SCH.gVars.projectMgr;
    }
  });
  // 直接列出全部 sheet 及其 schematic_uuid
  var sheets = [];
  Object.keys(pm.sheetCache.sheet).forEach(function(k){
    var s = pm.sheetCache.sheet[k];
    sheets.push({uuid:k, title:s.title, sch:s.schematic_uuid});
  });
  return JSON.stringify(sheets.slice(0,10));
})()
""")
print("sheetCache 样例:", r[:500] if r else "None")

# ② 找到目标页 uuid 并获取其 docManager
r = ev("""
(async function(){
  var pm = SCH.gVars.projectMgr;
  // 找 quadPizeoDriver_RevA (无后缀) 的 ControlDAC_A
  for (var k in pm.sheetCache.sheet) {
    var s = pm.sheetCache.sheet[k];
    if (s.title === 'ControlDAC_A') {
      // 查它的 schematic 对应哪个板
      return JSON.stringify({uuid: k, title: s.title, sch_uuid: s.schematic_uuid});
    }
  }
  return 'not found';
})()
""")
print("\nControlDAC_A:", r)

info = json.loads(r) if r and r != "not found" else None
if info:
    su = info["uuid"]
    # 加载并提取全部元件位号
    r = ev(f"""
    (async function(){{
      var dm = await SCH.docMemoryManager.getOrInitDoc({json.dumps(su)});
      var shapes = [];
      var mm = dm.shapeManager.modelMap;
      mm.forEach(function(shape, id) {{
        try {{
          var t = shape.constructor.name || '';
          var desig = '', device = '';
          try {{ desig = shape.getAttr('Designator') || ''; }} catch(e){{}}
          try {{ device = shape.getAttr('Device') || ''; }} catch(e){{}}
          if (desig || /COMPONENT/i.test(t)) {{
            shapes.push({{id:id, type:t, desig:desig, device:device.slice(0,40)}});
          }}
        }} catch(e){{}}
      }});
      return JSON.stringify(shapes);
    }})()
    """)
    print(f"\n页上元件 ({su[:12]}):")
    if isinstance(r, str):
        items = json.loads(r)
        print(f"总数: {len(items)}")
        for it in items:
            d = it.get("desig","")
            dev = it.get("device","")
            if d:
                print(f"  {d:12s} {dev}")
