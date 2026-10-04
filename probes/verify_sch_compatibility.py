#!/usr/bin/env python3
"""Compare SCH output against another checkout without publishing private data.

Inputs are never modified. The report contains only digests, return codes and
counts, not project filenames, page titles, UUIDs, netlists or component names.
This check supplements the repository-specific smoke tests; it does not turn
missing regression fixtures into a pass.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(reader, path, command, as_json=True):
    process = subprocess.run([sys.executable, str(reader), "--eprj", str(path)] +
                             (["--json"] if as_json else []) + command,
                             cwd=reader.parent, capture_output=True, timeout=180)
    valid = None
    if as_json and process.returncode == 0:
        try:
            json.loads(process.stdout)
            valid = True
        except ValueError:
            valid = False
    return process, valid


def verify(baseline, inputs, minimal_inputs=()):
    candidate = ROOT / "lceda_reader.py"
    spec = importlib.util.spec_from_file_location("compat_reader", candidate)
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    results = []
    for path in inputs:
        before = digest(path.read_bytes())
        backend_class = reader.detect_backend(path)
        if isinstance(backend_class, str):
            raise ValueError("Use an exported or plain supported input for this read-only regression")
        backend = backend_class(path)
        pages = [s for s in backend.sheets() if s[3] == 1]
        # The small synthetic SQLite fixture deliberately omits auxiliary
        # metadata tables. It covers netlist/pins/nets, not docs metadata.
        commands = ("netlist",) if path in minimal_inputs else ("tree", "list", "netlist", "pcbsch", "docs", "bom", "devmap")
        queries = [([command], True) for command in commands]
        for _uuid, title, schematic, _kind in pages:
            target = backend.schem_map().get(schematic, (schematic, schematic))[0]
            selector = [title, "--schematic", target] if target else [title]
            queries.extend([(["pinmap"] + selector, True), (["pinmap"] + selector, False),
                            (["pins"] + selector, True), (["nets"] + selector, True)])
        comparisons = []
        for command, as_json in queries:
            old, old_valid = run(baseline, path, command, as_json)
            new, new_valid = run(candidate, path, command, as_json)
            comparisons.append({"command": command[0], "json": as_json,
                                "baseline_exit": old.returncode, "candidate_exit": new.returncode,
                                "baseline_output_sha256": digest(old.stdout),
                                "candidate_output_sha256": digest(new.stdout),
                                "byte_identical": old.stdout == new.stdout,
                                "json_valid": new_valid,
                                "passed": old.returncode == new.returncode == 0 and old.stdout == new.stdout
                                          and new_valid is not False and old_valid is not False})
        for name in ("conn", "zip"):
            handle = getattr(backend, name, None)
            if handle is not None:
                handle.close()
        after = digest(path.read_bytes())
        results.append({"input_sha256": before, "input_unchanged": before == after,
                        "active_pages": len(pages), "comparisons": comparisons,
                        "passed": before == after and all(q["passed"] for q in comparisons)})
    return {"schema_version": 1, "scope": "byte-identical existing SCH queries only; not PCB or electrical validation",
            "baseline_reader_sha256": digest(baseline.read_bytes()),
            "candidate_reader_sha256": digest(candidate.read_bytes()),
            "inputs": results, "passed": all(item["passed"] for item in results)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True, help="Baseline checkout lceda_reader.py")
    parser.add_argument("--input", action="append", type=Path, default=[])
    parser.add_argument("--synthetic", action="store_true", help="Also generate three invented legacy formats")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.input and not args.synthetic:
        parser.error("Provide --input or --synthetic")
    if args.output.exists():
        parser.error("Choose a new output path")
    parent = ROOT / "probes" / "tmp"
    parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=parent) as directory:
        inputs = [p.resolve() for p in args.input]
        minimal_inputs = []
        if args.synthetic:
            from test_reader_portable import write_fixture
            minimal_inputs = [write_fixture(Path(directory), kind) for kind in ("eprj2", "epro", "epro2")]
            inputs += minimal_inputs
        report = verify(args.baseline.resolve(), inputs, minimal_inputs)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "inputs": len(report["inputs"]),
                      "comparisons": sum(len(item["comparisons"]) for item in report["inputs"])}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
