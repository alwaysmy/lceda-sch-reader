"""dump docManager 的 shapeManager.modelMap 中全部对象的属性键。"""
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

# 加载 ControlDAC_A 页并 dump 前几个 shape 的全部属性
r = ev("""
(async function(){
  var pm = SCH.gVars.projectMgr;
  // 找 RevA 的 ControlDAC_A (sch=120095be3ade)
  var su = null;
  Object.keys(pm.sheetCache.sheet).forEach(function(k){
    var s = pm.sheetCache.sheet[k];
    if (s.schematic_uuid && s.schematic_uuid.startsWith('120095be')) {
      if (s.title.toLowerCase() === 'controldac_a') su = k;
    }
  });
  if (!su) {
    // 列出全部页找
    var pages = [];
    Object.keys(pm.sheetCache.sheet).forEach(function(k){
      var s = pm.sheetCache.sheet[k];
      pages.push({uuid:k, title:s.title, sch:s.schematic_uuid});
    });
    return JSON.stringify({error:'not found', pages:pages.slice(0,10)});
  }
  
  var dm = await SCH.docMemoryManager.getOrInitDoc(su);
  var mm = dm.shapeManager.modelMap;
  var shapes = [];
  var count = 0;
  mm.forEach(function(shape, id) {
    count++;
    if (shapes.length >= 5) return;
    try {
      var ownKeys = Object.keys(shape);
      var protoKeys = [];
      var proto = Object.getPrototypeOf(shape);
      while(proto && proto !== Object.prototype) {
        Object.getOwnPropertyNames(proto).forEach(function(p){
          try{ if(typeof shape[p]==='function' && /attr|desig|name|device/i.test(p)) 
            protoKeys.push(p); }catch(e){}
        });
        proto = Object.getPrototypeOf(proto); n++;
      }
      shapes.push({
        id: id.slice(0,12),
        ctor: shape.constructor.name || '?',
        keys: ownKeys.slice(0,15),
        attrMethods: Array.from(new Set(protoKeys)).slice(0,10)
      });
    } catch(e){}
  });
  return JSON.stringify({total: count, samples: shapes});
})()
""")
print(r[:3000] if r else "None")

# 如果找到了 getAttr 方法，用它提取
r2 = ev("""
(async function(){
  var pm = SCH.gVars.projectMgr;
  var su = null;
  Object.keys(pm.sheetCache.sheet).forEach(function(k){
    var s = pm.sheetCache.sheet[k];
    if (s.schematic_uuid && s.schematic_uuid.startsWith('120095be') &&
        s.title.toLowerCase() === 'controldac_a') su = k;
  });
  if (!su) return 'page not found';
  
  var dm = await SCH.docMemoryManager.getOrInitDoc(su);
  var results = [];
  var mm = dm.shapeManager.modelMap;
  mm.forEach(function(shape, id) {
    if (results.length >= 20) return;
    try {
      // 尝试多种方式获取位号
      var desig = null, dev = null;
      // 方式1: getAttr
      try { desig = shape.getAttr('Designator'); } catch(e){}
      // 方式2: 直接属性
      if (!desig && shape.attrs && shape.attrs.Designator) 
        desig = shape.attrs.Designator;
      if (!desig && shape._attrs && shape._attrs.Designator)
        desig = shape._attrs.Designator;
      // device
      try { dev = shape.getAttr('Device'); } catch(e){}
      
      if (desig) {
        results.push({id:id.slice(0,10), desig:desig, dev:String(dev||'').slice(0,30),
                      type: shape.constructor.name});
      }
    } catch(e){}
  });
  return JSON.stringify(results);
})()
""")
print("\n有位号的元件:")
print(r2[:2000] if r2 else r2)
