#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对比两个 lceda_reader 版本在工程语料上的 netlist 输出（回归差分工具）。

用途：解析层/后端改动后，用旧版 reader 与新版本逐文件跑 `--json netlist`，
比较规范化 JSON，报告"完全一致 / 有差异 / 失败方式不一致 / 双方都失败"。
差异只报告事实（网络名增删、成员变化），不做优劣裁决。

用法：
    set PYTHONIOENCODING=utf-8
    python probes\\compare_reader_versions.py --a OLD.py --b NEW.py
    python probes\\compare_reader_versions.py --a OLD.py --b NEW.py ^
        --scan D:\\WorkDesigns --scan C:\\Users\\dell\\Documents\\LCEDA-Pro ^
        --scan C:\\Users\\dell\\Downloads --json-report probes\\tmp\\report.json --details

获取旧版 reader 的常用方式（旧版本已不在工作区时）：
    git show <rev>:lceda_reader.py > probes\\tmp\\old_reader.py

说明：
- 默认只扫描仓库自带样本 `../examples`；`--scan` 可重复，按目录递归。
- 自动跳过 probes/.git/__pycache__/node_modules 目录。
- 默认扩展名 .epro2/.epro/.eprj2/.eprj/.eprj3（.eprj3 传索引文件即可）。
- 退出码：0=无差异；1=存在差异或失败方式不一致；2=参数错误。
"""
import argparse
import io
import json
import os
import subprocess
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_SCAN = os.path.normpath(os.path.join(ROOT, "..", "examples"))
DEFAULT_EXTS = "epro2,epro,eprj2,eprj,eprj3"
SKIP_DIRS = {"probes", ".git", "__pycache__", "node_modules"}
FAIL_STATUSES = {"diff", "rc-mismatch", "json-error", "timeout"}


def parse_args():
    p = argparse.ArgumentParser(
        description="对比两个 lceda_reader 版本的 netlist 输出")
    p.add_argument("--a", required=True, help="旧版 reader（.py 路径）")
    p.add_argument("--b", required=True, help="新版 reader（.py 路径）")
    p.add_argument("--scan", action="append", default=[],
                   help="扫描目录，可重复；默认仓库自带 examples")
    p.add_argument("--ext", default=DEFAULT_EXTS,
                   help="扩展名逗号列表（默认 %s）" % DEFAULT_EXTS)
    p.add_argument("--json-report", help="结构化结果写入该 JSON 文件")
    p.add_argument("--details", action="store_true",
                   help="打印差异网络与成员明细")
    p.add_argument("--timeout", type=int, default=600,
                   help="单文件超时秒数（默认 600）")
    p.add_argument("--max-files", type=int, default=0,
                   help="最多扫描文件数（0=不限）")
    return p.parse_args()


def find_files(scans, exts, max_files):
    out = []
    for base in scans:
        base = os.path.abspath(base)
        if not os.path.isdir(base):
            print("跳过不存在的扫描目录: %s" % base, file=sys.stderr)
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            parts = {p.lower() for p in dirpath.split(os.sep)}
            if parts & SKIP_DIRS:
                dirnames[:] = []
                continue
            for fn in filenames:
                if os.path.splitext(fn)[1].lower().lstrip(".") in exts:
                    out.append(os.path.join(dirpath, fn))
                    if max_files and len(out) >= max_files:
                        return sorted(set(out))
    return sorted(set(out))


def run_reader(reader, path, timeout):
    return subprocess.run(
        [sys.executable, reader, "--eprj", path, "--json", "netlist"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        cwd=ROOT, timeout=timeout)


def member_diff(net_a, net_b):
    ca = set(net_a.get("components") or [])
    cb = set(net_b.get("components") or [])
    sa = set(net_a.get("sheets") or [])
    sb = set(net_b.get("sheets") or [])
    return {"only_a": sorted(ca - cb), "only_b": sorted(cb - ca),
            "sheets_only_a": sorted(sa - sb), "sheets_only_b": sorted(sb - sa)}


def compare_file(reader_a, reader_b, path, timeout):
    entry = {"file": path}
    try:
        ra = run_reader(reader_a, path, timeout)
        rb = run_reader(reader_b, path, timeout)
    except subprocess.TimeoutExpired:
        entry["status"] = "timeout"
        return entry
    entry["rc_a"], entry["rc_b"] = ra.returncode, rb.returncode
    if ra.returncode == rb.returncode == 0:
        try:
            ja, jb = json.loads(ra.stdout), json.loads(rb.stdout)
        except ValueError as exc:
            entry["status"] = "json-error"
            entry["error"] = str(exc)
            return entry
        if (json.dumps(ja, sort_keys=True, ensure_ascii=False)
                == json.dumps(jb, sort_keys=True, ensure_ascii=False)):
            entry["status"] = "same"
            return entry
        entry["status"] = "diff"
        ma = {n["net"]: n for n in ja}
        mb = {n["net"]: n for n in jb}
        entry["nets_removed"] = sorted(set(ma) - set(mb))
        entry["nets_added"] = sorted(set(mb) - set(ma))
        entry["nets_modified"] = [
            {"net": k, **member_diff(ma[k], mb[k])}
            for k in sorted(set(ma) & set(mb)) if ma[k] != mb[k]]
        return entry
    if ra.returncode != rb.returncode:
        entry["status"] = "rc-mismatch"
        entry["stderr_a"] = (ra.stderr or "")[-400:]
        entry["stderr_b"] = (rb.stderr or "")[-400:]
        return entry
    entry["status"] = "both-fail"      # 两版以相同退出码失败：视为无回归
    return entry


def print_details(entry, limit=30):
    print("    仅旧版网络(%d): %s" % (len(entry["nets_removed"]),
                                   entry["nets_removed"][:limit]))
    print("    仅新版网络(%d): %s" % (len(entry["nets_added"]),
                                   entry["nets_added"][:limit]))
    for m in entry["nets_modified"][:limit]:
        print("    ~ %s  成员 -%d/+%d  页 -%d/+%d"
              % (m["net"], len(m["only_a"]), len(m["only_b"]),
                 len(m["sheets_only_a"]), len(m["sheets_only_b"])))
        if m["only_a"]:
            print("        仅旧版: %s" % m["only_a"][:20])
        if m["only_b"]:
            print("        仅新版: %s" % m["only_b"][:20])


def main():
    args = parse_args()
    reader_a = os.path.abspath(args.a)
    reader_b = os.path.abspath(args.b)
    for r in (reader_a, reader_b):
        if not os.path.isfile(r):
            print("reader 不存在: %s" % r, file=sys.stderr)
            return 2
    exts = {x.strip().lower().lstrip(".")
            for x in args.ext.split(",") if x.strip()}
    scans = args.scan or [DEFAULT_SCAN]
    files = find_files(scans, exts, args.max_files)
    if not files:
        print("未找到待对比工程文件（扩展名: %s）" % ",".join(sorted(exts)),
              file=sys.stderr)
        return 2
    print("旧版: %s" % reader_a)
    print("新版: %s" % reader_b)
    print("扫描: %s" % ", ".join(os.path.abspath(s) for s in scans))
    print("候选文件: %d" % len(files))
    report = []
    for i, path in enumerate(files, 1):
        entry = compare_file(reader_a, reader_b, path, args.timeout)
        report.append(entry)
        print("[%3d/%3d] %-12s %s" % (i, len(files), entry["status"], path),
              flush=True)
        if args.details and entry["status"] in ("diff", "rc-mismatch"):
            print_details(entry)
    if args.json_report:
        out = os.path.abspath(args.json_report)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
        print("报告: %s" % out)
    counts = Counter(e["status"] for e in report)
    print("\n==== 汇总 ====")
    print("netlist: %s" % dict(counts))
    for e in report:
        if e["status"] in FAIL_STATUSES:
            extra = ""
            if e["status"] == "diff":
                extra = "  网络 -%d/+%d ~%d" % (
                    len(e["nets_removed"]), len(e["nets_added"]),
                    len(e["nets_modified"]))
            print("- %s: %s%s" % (e["status"], e["file"], extra))
    bad = sum(counts[s] for s in FAIL_STATUSES)
    print("结论: %s（差异/不一致 %d 个）"
          % ("PASS" if bad == 0 else "FAIL", bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
