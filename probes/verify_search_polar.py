# -*- coding: utf-8 -*-
"""search 网络提示 + polar 方向/连通性 回归（脚本入 probes/）。

默认工程 ../examples/涡流传感器.eprj2，可用 LCEDA_EPRJ 覆盖。
"""
import io
import json
import os
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
READER = os.path.join(ROOT, "lceda_reader.py")
EPRJ = os.environ.get("LCEDA_EPRJ") or os.path.normpath(
    os.path.join(ROOT, "..", "examples", "涡流传感器.eprj2"))
ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")

ok = True


def check(cond, msg):
    global ok
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        ok = False


def run(args):
    p = subprocess.run([sys.executable, READER, "--eprj", EPRJ] + args,
                       capture_output=True, text=True, encoding="utf-8",
                       env=ENV, cwd=ROOT)
    return p.returncode, p.stdout, p.stderr


if not os.path.isfile(EPRJ):
    print(f"工程不存在: {EPRJ}")
    print("ALL: FAIL")
    sys.exit(1)
print(f"工程: {EPRJ}")

print("[1] search 命中 Name -> 所在网络提示")
rc, out, err = run(["--json", "search", "VREF2.5V"])
check(rc == 0, f"search rc={rc}")
try:
    rows = json.loads(out)
except ValueError:
    rows = []
    check(False, "search --json 输出可解析")
hints = [h for r in rows for h in (r.get("net_hints") or [])]
check(bool(hints), f"至少一条 net_hints（{len(hints)}）")
if hints:
    h = hints[0]
    check(h.get("member_count", 0) > 1, f"成员数 > 1（{h.get('member_count')}）")
    check("VREF2.5V" in (h.get("aliases") or []), "aliases 含命中的名字")
    check(bool(h.get("net")), f"net 非空（{h.get('net')}）")
    check(len(h.get("members") or []) > 0, "members 非空")

print("[2] polar：方向 + 两端网络 + 同网连接点")
rc, out, err = run(["--json", "polar"])
check(rc == 0, f"polar rc={rc}")
try:
    data = json.loads(out)
except ValueError:
    data = {}
    check(False, "polar --json 输出可解析")
items = data.get("items") or []
check(len(items) > 0, f"极性器件 {len(items)} 个")
check(any(r.get("direction") == "A→K" for r in items), "至少一件标出 A→K 方向")
pins = [p for r in items for p in r.get("pins") or []]
check(any(p.get("net_member_count") for p in pins), "至少一个引脚带连接点数")
check(all(len(p["net_aliases"]) > 1 for p in pins if p.get("net_aliases")),
      "net_aliases 若存在必为多名字（本工程可能无）")
# 未命名网络必须给出"同线"对象，而不是空白
unnamed = [p for p in pins if not p.get("net")]
check(any(p.get("wire_peers") for p in unnamed),
      f"未命名引脚给出同线对象（{sum(1 for p in unnamed if p.get('wire_peers'))}"
      f"/{len(unnamed)}）")

print("ALL: " + ("PASS" if ok else "FAIL"))
sys.exit(0 if ok else 1)
