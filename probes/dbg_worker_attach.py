"""① worker flatten attach 评估尝试 ② pro-mgr js blowfish 上下文。"""
import io, sys, json, time, socket, base64, os, struct
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import urllib.request
targets = json.loads(urllib.request.urlopen(
    "http://127.0.0.1:9222/json/list", timeout=5).read().decode())

# ① flatten attach：连 browser 端点，Target.attachToTarget worker
browser_ws = None
try:
    ver = json.loads(urllib.request.urlopen(
        "http://127.0.0.1:9222/json/version", timeout=5).read().decode())
    browser_ws = ver.get("webSocketDebuggerUrl")
except Exception:
    pass
print("browser ws:", browser_ws)

sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cdp", r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes\cdp_eval.py")
cdp = importlib.util.module_from_spec(spec)
sys.argv = ["cdp"]
spec.loader.exec_module(cdp)

if browser_ws:
    ws = cdp.WS(browser_ws)
    ws.send_json({"id": 1, "method": "Target.setAutoAttach",
                  "params": {"autoAttach": True, "flatten": True}})
    time.sleep(1)
    workers = [t for t in targets if t.get("type") == "worker"]
    for i, w in enumerate(workers):
        tid = w["id"]
        ws.send_json({"id": 100+i, "method": "Target.attachToTarget",
                      "params": {"targetId": tid, "flatten": True}})
        time.sleep(1)
        # 发 evaluate（sessionId 未知——先看 attach 响应）
    # 读取 3 秒内所有消息
    ws.sock.settimeout(3)
    t0 = time.time()
    sessions = {}
    try:
        while time.time() - t0 < 6:
            msg = ws.recv_text()
            m = json.loads(msg)
            if m.get("method") == "Target.attachedToTarget":
                si = m["params"]["sessionId"]
                ti = m["params"]["targetInfo"]
                sessions[si] = ti.get("type")
                print("attached:", ti.get("type"), si[:16])
                ws.send_json({"sessionId": si, "id": 500+len(sessions),
                              "method": "Runtime.evaluate",
                              "params": {"expression":
                                         "Object.keys(self).length",
                                         "returnByValue": True}})
    except socket.timeout:
        pass
    # 收 evaluate 结果
    ws.sock.settimeout(5)
    t0 = time.time()
    try:
        while time.time() - t0 < 8:
            msg = ws.recv_text()
            m = json.loads(msg)
            if "id" in m and m["id"] >= 500:
                r = m.get("result", {}).get("result", {})
                print(f"  eval id={m['id']}: {r.get('value', str(r)[:100])}")
    except socket.timeout:
        pass
