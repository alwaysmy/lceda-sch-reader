"""工具完善性审计：命令清单/帮助完整性、错误路径、边界输入。"""
import io, sys, subprocess, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
TOOL = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader"
        r"\lceda_reader.py")
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def run(args, timeout=300):
    p = subprocess.run([sys.executable, TOOL] + args,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=ENV, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


E = (r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch"
     r"\涡流传感器-V1.0-2026.04.01.eprj2")
EP = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples"
      r"\ProPrj_TPS56C230_Buck_12Vto5V_6A_2026-08-13.epro")

checks = [
    ("--help 列出全部子命令", ["--help"], lambda rc, o: rc == 0 and all(
        k in o for k in ("list", "boards", "tree", "components", "texts",
                         "nets", "pinmap", "pins", "netlist", "netfind",
                         "trace", "link-check", "find", "search", "bom",
                         "datasheets", "attrs", "devmap", "raw", "pcbsch",
                         "render"))),
    ("无 --eprj 自动探测(工作目录无工程应明确报错)",
     ["list"], lambda rc, o: "未找到" in o or rc == 0),
    ("不存在的文件", ["--eprj", r"D:\not\exist.eprj2", "list"],
     lambda rc, o: rc != 0 and ("无法打开" in o or "不支持" in o or o.strip())),
    ("不存在的页名", ["--eprj", E, "components", "不存在的页XYZ"],
     lambda rc, o: rc == 0 or "未找到" in o),
    ("render 不存在的页", ["--eprj", E, "render", "不存在XYZ"],
     lambda rc, o: rc != 0 and "未找到" in o),
    ("pcbsch 在 epro 上可用(不再报错)", ["--eprj", EP, "pcbsch"],
     lambda rc, o: rc == 0 and "PCB" in o),
    ("--json pcbsch 可解析", ["--eprj", E, "--json", "pcbsch"],
     lambda rc, o: rc == 0 and o.strip().startswith("{")),
    ("--json render 不支持? 应正常出 SVG", ["--eprj", E, "render",
                                            "高速DA", "-o",
                                            os.path.join(
                                                os.path.dirname(TOOL),
                                                "probes", "tmp",
                                                "r.json.svg")],
     lambda rc, o: rc == 0),
    ("同名页未指定 --schematic 有 stderr 警告",
     ["--eprj", E, "components", "激励输出和AD采集"],
     lambda rc, o: "重名" in o or rc == 0),
    ("bom --bom-only", ["--eprj", E, "bom", "--bom-only"],
     lambda rc, o: rc == 0),
    ("find 不存在位号", ["--eprj", E, "find", "XYZ999"],
     lambda rc, o: rc == 0 or "未找到" in o),
    ("netfind 不存在网络", ["--eprj", E, "netfind", "NOPE_NET"],
     lambda rc, o: rc == 0 or "未" in o or o.strip() == ""),
    ("raw 输出到 probes/tmp", ["--eprj", E, "raw", "高速DA", "-o",
                               os.path.join(os.path.dirname(TOOL),
                                            "probes", "tmp", "raw.ndjson")],
     lambda rc, o: rc == 0),
]

nfail = 0
for name, args, ok in checks:
    try:
        rc, o = run(args)
        passed = False
        try:
            passed = bool(ok(rc, o))
        except Exception as e:
            o += f" [checker:{e}]"
        tail = o.strip().splitlines()[-1][:80] if o.strip() else ""
        print(f"{'PASS' if passed else 'FAIL'} {name}  rc={rc}  {tail}")
        if not passed:
            nfail += 1
    except subprocess.TimeoutExpired:
        print(f"FAIL {name}  TIMEOUT")
        nfail += 1
print("ALL:", "PASS" if nfail == 0 else f"{nfail} FAIL")
