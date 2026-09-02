"""CDP 探测 harness：执行 JS 表达式，完整结果存 probes/tmp/ 下文件。
用法:
  python cdp_probe.py eval "<js>" [-o out.json]   # 执行并打印/保存
  python cdp_probe.py targets                     # 列 targets
  python cdp_probe.py workers "<js>"              # 经 browser 端点逐 worker 执行
复用 cdp_eval.py 的 WS 客户端。"""
import io, sys, json, os, time, argparse
if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdp_eval

TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp")


def evaluate_full(expr, timeout=90):
    """同 cdp_eval.evaluate 但不截断、支持 awaitPromise。"""
    targets = cdp_eval.http_get_list()
    t = cdp_eval.pick_editor(targets)
    ws = cdp_eval.WS(t["webSocketDebuggerUrl"])
    ws.send_json({"id": 1, "method": "Runtime.enable"})
    try:
        ws.recv_text()
    except SystemExit:
        pass
    ws.send_json({"id": 2, "method": "Runtime.evaluate",
                  "params": {"expression": expr,
                             "returnByValue": True,
                             "awaitPromise": True}})
    t0 = time.time()
    while time.time() - t0 < timeout:
        msg = json.loads(ws.recv_text())
        if msg.get("id") == 2:
            r = msg.get("result", {})
            if "exceptionDetails" in r:
                ed = r["exceptionDetails"]
                txt = ed.get("exception", {}).get("description") or json.dumps(ed, ensure_ascii=False)
                return {"__exception__": txt[:2000]}
            res = r.get("result", {})
            if res.get("subtype") == "error":
                return {"__exception__": res.get("description", "")[:2000]}
            return res.get("value")
    return {"__timeout__": True}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["eval", "targets"])
    ap.add_argument("expr", nargs="?")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("-t", "--timeout", type=int, default=90)
    args = ap.parse_args()

    if args.mode == "targets":
        for t in cdp_eval.http_get_list():
            print(t["type"], "|", t["title"][:50], "|", t["url"][:80])
        return

    v = evaluate_full(args.expr, args.timeout)
    if args.out:
        os.makedirs(TMP, exist_ok=True)
        path = os.path.join(TMP, args.out)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(v, f, ensure_ascii=False, indent=1)
        size = os.path.getsize(path)
        print(f"saved -> probes/tmp/{args.out} ({size} bytes)")
        print(json.dumps(v, ensure_ascii=False)[:1500])
    else:
        out = json.dumps(v, ensure_ascii=False)
        print(out if len(out) < 8000 else out[:8000] + f"\n...[截断,共{len(out)}字符, 用 -o 保存]")


if __name__ == "__main__":
    main()
