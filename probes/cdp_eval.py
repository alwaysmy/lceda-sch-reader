"""最小 CDP Runtime.evaluate 客户端（无第三方依赖）。
用法: python cdp_eval.py [ws_url] "<js 表达式>"   # 缺省连编辑器页面
输出: JSON result.value（反序列化 byValue）。"""
import io, sys, json, socket, base64, hashlib, os, struct
if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HTTP = "http://127.0.0.1:9222/json/list"

def http_get_list():
    import urllib.request
    with urllib.request.urlopen(HTTP, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))

def pick_editor(targets):
    for t in targets:
        if t.get("type") == "page" and "/editor" in t.get("url", ""):
            return t
    for t in targets:
        if t.get("type") == "page":
            return t
    raise SystemExit("无可用 page target")

class WS:
    def __init__(self, url):
        assert url.startswith("ws://")
        rest = url[5:]
        hostport, path = rest.split("/", 1)
        path = "/" + path
        if ":" in hostport:
            host, port = hostport.rsplit(":", 1)
            port = int(port)
        else:
            host, port = hostport, 80
        self.sock = socket.create_connection((host, port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET {path} HTTP/1.1\r\nHost: {hostport}\r\n"
               "Upgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
               "\r\n")
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise SystemExit("WS 握手失败")
            buf += chunk
        head, _, restbuf = buf.partition(b"\r\n\r\n")
        assert b"101" in head.split(b"\r\n")[0], head[:120]
        self.buf = restbuf

    def _recv_exact(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise SystemExit("连接关闭")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv_text(self):
        while True:
            b1, b2 = self._recv_exact(2)
            opcode = b1 & 0x0F
            masked = b2 & 0x80
            ln = b2 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._recv_exact(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._recv_exact(8))[0]
            mask = self._recv_exact(4) if masked else None
            payload = self._recv_exact(ln)
            if mask:
                payload = bytes(c ^ mask[i % 4]
                                for i, c in enumerate(payload))
            if opcode == 0x9:          # ping → pong
                self.send_frame(0xA, payload)
                continue
            if opcode in (0x1, 0x0):
                return payload.decode("utf-8", errors="replace")
            if opcode == 0x8:
                raise SystemExit("WS closed")

    def send_frame(self, op, payload: bytes):
        header = bytes([0x80 | op])
        n = len(payload)
        mask_bit = 0x80
        if n < 126:
            header += bytes([mask_bit | n])
        elif n < 65536:
            header += bytes([mask_bit | 126]) + struct.pack(">H", n)
        else:
            header += bytes([mask_bit | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        masked = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
        self.sock.sendall(header + mask + masked)

    def send_json(self, obj):
        self.send_frame(0x1, json.dumps(obj).encode())

def evaluate(expr, url=None):
    targets = http_get_list()
    t = pick_editor(targets)
    wsurl = url or t["webSocketDebuggerUrl"]
    ws = WS(wsurl)
    ws.send_json({"id": 1, "method": "Runtime.enable"})
    try:
        ws.recv_text()             # 可能是事件
    except SystemExit:
        pass
    ws.send_json({"id": 2, "method": "Runtime.evaluate",
                  "params": {"expression": expr,
                             "returnByValue": True,
                             "awaitPromise": False}})
    deadline = 60
    import time
    t0 = time.time()
    while time.time() - t0 < deadline:
        msg = json.loads(ws.recv_text())
        if msg.get("id") == 2:
            r = msg.get("result", {})
            if "exceptionDetails" in r:
                ed = r["exceptionDetails"]
                print("EXC:", json.dumps(ed, ensure_ascii=False)[:500])
                return None
            res = r.get("result", {})
            return res.get("value")
    print("超时")
    return None

if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) >= 2 and args[0].startswith("ws://"):
        url, expr = args[0], args[1]
    else:
        url, expr = None, args[0] if args else "1+1"
    v = evaluate(expr, url)
    if isinstance(v, str):
        print(v)
    else:
        print(json.dumps(v, ensure_ascii=False)[:4000])
