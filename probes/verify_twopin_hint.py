# -*- coding: utf-8 -*-
"""netfind 两脚件提示回归（脚本入 probes/）。

判据：netfind 命中"串联类两脚件"（R/L/F/短接/二极管等）时，行内应带
other_side（另一脚网络或同线对象），提示继续追；电容（C*）应被过滤。

默认工程 ../examples/涡流传感器.eprj2，可用 LCEDA_EPRJ 覆盖。
"""
import io
import json
import os
import re
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
    try:
        return json.loads(p.stdout)
    except (ValueError, TypeError):
        return None


if not os.path.isfile(EPRJ):
    print(f"工程不存在: {EPRJ}")
    sys.exit(1)
print(f"工程: {EPRJ}")

nets = run(["--json", "netlist"]) or []
hit = None
tried = 0
for r in nets:
    comps = r.get("components") or []
    if not any(re.match(r"^(R|L|FB|F|D|LED|SHORT)", c.upper()) for c in comps):
        continue
    tried += 1
    rows = run(["--json", "netfind", r["net"]]) or []
    if any(x.get("other_side") for x in rows):
        hit = (r["net"], rows)
        break
    if tried >= 12:
        break
check(bool(hit), f"找到带两脚件提示的网络（尝试 {tried} 个）")
if hit:
    net, rows = hit
    o = next(x["other_side"] for x in rows if x.get("other_side"))
    print(f"      net={net}  例: {o}")
    check("pin" in o, "other_side 含另一脚引脚号")
    check("net" in o, "other_side 含另一脚网络（可为空）")

# 电容不应被当作"串联件"提示：找含 C 且不含 R/L/D 的网络
cap_ok = True
for r in nets:
    comps = r.get("components") or []
    if not comps or not any(c.upper().startswith("C") for c in comps):
        continue
    if any(re.match(r"^(R|L|FB|F|D|LED|SHORT)", c.upper()) for c in comps):
        continue
    rows = run(["--json", "netfind", r["net"]]) or []
    if any((x.get("designator") or "").upper().startswith("C")
           and x.get("other_side") for x in rows):
        cap_ok = False
        print(f"      电容被误标: {r['net']}")
        break
check(cap_ok, "电容（C*）不输出 other_side")

print("ALL: " + ("PASS" if ok else "FAIL"))
sys.exit(0 if ok else 1)
