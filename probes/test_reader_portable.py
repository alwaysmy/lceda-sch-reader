"""Portable, synthetic old-format regressions; no private project is required.

Run: python -m unittest discover -s probes -p test_reader_portable.py -v
All fixture identifiers, labels and geometry below are invented. Generated files
stay in probes/tmp and are removed after each test. These small fixtures augment,
but do not replace, the private engineering-project regression suite.
"""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import lceda_reader as reader


def ndjson(records):
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in records)


def log_record(kind, ident, body, ticket=1):
    header = {"type": kind, "ticket": ticket}
    if ident is not None:
        header["id"] = ident
    payload = "" if body is None else json.dumps(body, ensure_ascii=False)
    return json.dumps(header, separators=(",", ":")) + "||" + payload + "|"


def log_document(kind, uuid, meta, records=()):
    return [log_record("DOCHEAD", None, {
        "docType": kind, "uuid": uuid, "client": "0123456789abcdef"}),
        log_record("META", "META", meta)] + list(records)


def fixture_arrays(flat_wires=False):
    symbol = [
        ["DOCTYPE", "SYMBOL", "1.1"],
        ["HEAD", {"symbolType": 2, "originX": 0, "originY": 0}],
        ["PART", "Generic.1", {"BBOX": [-5, -5, 5, 5]}],
        ["PIN", "p1", None, None, -10, 0, 10, 0],
        ["ATTR", "pn1", "p1", "NAME", "LEFT"],
        ["ATTR", "pi1", "p1", "NUMBER", "1"],
        ["PIN", "p2", None, None, 10, 0, 10, 180],
        ["ATTR", "pn2", "p2", "NAME", "RIGHT"],
        ["ATTR", "pi2", "p2", "NUMBER", "2"],
    ]
    sheet = [
        ["DOCTYPE", "SCH", "1.1"],
        ["COMPONENT", "c1", "sym1" if flat_wires else "Generic.1",
         100, 100, 0, False, {}, 0],
        ["ATTR", "a1", "c1", "Designator", "R1"],
        ["ATTR", "a2", "c1", "Symbol", "sym1"],
        ["ATTR", "a3", "c1", "Device", "dev1"],
        ["ATTR", "a4", "c1", "Name", "Generic.1"],
        ["ATTR", "a5", "c1", "Value", "1k"],
        ["WIRE", "w1", [70, 100, 90, 100] if flat_wires else
         [[70, 100, 90, 100]]],
        ["ATTR", "n1", "w1", "NET", "SIGNAL_A"],
        ["WIRE", "w2", [110, 100, 130, 100] if flat_wires else
         [[110, 100, 130, 100]]],
        ["ATTR", "n2", "w2", "NET", "SIGNAL_B"],
    ]
    return symbol, sheet


def write_fixture(directory, kind):
    """Create the same invented two-terminal circuit in three old formats."""
    path = directory / ("generic." + kind)
    attrs = {"Symbol": "sym1", "Description": "阻值:1kΩ;",
             "Manufacturer Part": "Generic", "Add into BOM": "yes"}
    symbol, sheet = fixture_arrays(flat_wires=kind == "epro")
    if kind == "eprj2":
        with sqlite3.connect(path) as conn:
            conn.executescript("""
                CREATE TABLE schematics(uuid, name, display_name);
                CREATE TABLE documents(uuid, display_title, schematic_uuid,
                                       docType, dataStr);
                CREATE TABLE components(uuid, title, display_title,
                                        description, dataStr);
                CREATE TABLE devices(uuid, title, display_title, description);
                CREATE TABLE attributes(device_uuid, key, value);
            """)
            conn.execute("INSERT INTO schematics VALUES(?,?,?)",
                         ("sch1", "Board", "Board"))
            conn.execute("INSERT INTO documents VALUES(?,?,?,?,?)",
                         ("page1", "Page", "sch1", 1, ndjson(sheet)))
            conn.execute("INSERT INTO components VALUES(?,?,?,?,?)",
                         ("sym1", "Generic.1", "Generic", "", ndjson(symbol)))
            conn.execute("INSERT INTO devices VALUES(?,?,?,?)",
                         ("dev1", "Generic", "Generic", attrs["Description"]))
            conn.executemany("INSERT INTO attributes VALUES(?,?,?)",
                             [("dev1", key, val) for key, val in attrs.items()])
    elif kind == "epro":
        project = {
            "boards": {"Board": {"schematic": "sch1"}},
            "schematics": {"sch1": {"name": "Schematic", "sheets": [
                {"uuid": "page1", "id": 1, "name": "Page"}]}},
            "devices": {"dev1": {"title": "Generic", "attributes": attrs}},
            "symbols": {"sym1": {"title": "Generic.1"}},
        }
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("project.json", json.dumps(project))
            zf.writestr("SHEET/sch1/1.esch", ndjson(sheet))
            zf.writestr("SYMBOL/sym1.esym", ndjson(symbol))
    elif kind == "epro2":
        lines = log_document("BOARD", "board1", {"title": "Board"})
        lines += log_document("SCH", "sch1", {
            "title": "Schematic", "board": "board1"})
        pin_records = [log_record("CANVAS", "CANVAS", {
            "originX": 0, "originY": 0}),
            log_record("PART", "Generic.1", {"BBOX": [-5, -5, 5, 5]})]
        for pin, x, name, number in (("p1", -10, "LEFT", "1"),
                                     ("p2", 10, "RIGHT", "2")):
            pin_records += [
                log_record("PIN", pin, {"partId": "Generic.1", "x": x,
                           "y": 0, "length": 0, "rotation": 0}),
                log_record("ATTR", pin + "name", {"parentId": pin,
                           "key": "Pin Name", "value": name}),
                log_record("ATTR", pin + "num", {"parentId": pin,
                           "key": "Pin Number", "value": number}),
            ]
        lines += log_document("SYMBOL", "sym1", {
            "title": "Generic.1", "docType": 2}, pin_records)
        lines += log_document("DEVICE", "dev1", {
            "title": "Generic", "attributes": attrs})
        records = [log_record("CANVAS", "CANVAS", {
            "originX": 0, "originY": 0}),
            log_record("COMPONENT", "c1", {"partId": "Generic.1",
                       "x": 100, "y": -100, "rotation": 0,
                       "isMirror": False, "attrs": {}})]
        for idx, key, value in ((1, "Designator", "R1"), (2, "Symbol", "sym1"),
                                (3, "Device", "dev1"), (4, "Name", "Generic.1"),
                                (5, "Value", "1k")):
            records.append(log_record("ATTR", "a" + str(idx), {
                "parentId": "c1", "key": key, "value": value}))
        for wid, start, end, net in (("w1", 70, 90, "SIGNAL_A"),
                                      ("w2", 110, 130, "SIGNAL_B")):
            records += [log_record("WIRE", wid, {"groupId": ""}),
                        log_record("LINE", wid + "line", {
                            "lineGroup": wid, "startX": start, "startY": -100,
                            "endX": end, "endY": -100}),
                        log_record("ATTR", wid + "net", {
                            "parentId": wid, "key": "NET", "value": net})]
        lines += log_document("SCH_PAGE", "page1", {
            "title": "Page", "schematic": "sch1"}, records)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("project2.json", json.dumps({"title": "Generic"}))
            zf.writestr("generic.epru", "\n".join(lines) + "\n")
    else:
        raise ValueError(kind)
    return path


class PortableReaderTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "probes" / "tmp"
        parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="reader-test-", dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.paths = {kind: write_fixture(Path(self.temp.name), kind)
                      for kind in ("eprj2", "epro", "epro2")}

    def open_backend(self, path):
        backend = reader.detect_backend(path)(path)
        handle = getattr(backend, "conn", None) or getattr(backend, "zip", None)
        if handle is not None:
            self.addCleanup(handle.close)
        return backend

    def cli(self, path, *args):
        return subprocess.run([sys.executable, str(ROOT / "lceda_reader.py"),
                               "--eprj", str(path), "--json", *args],
                              cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", timeout=30)

    def test_content_detection_ignores_extension(self):
        expected = {"eprj2": reader.LcedaDB, "epro": reader.EproDB,
                    "epro2": reader.Epro2DB}
        for kind, path in self.paths.items():
            with self.subTest(kind=kind):
                renamed = path.with_suffix(".data")
                renamed.write_bytes(path.read_bytes())
                self.assertIs(reader.detect_backend(renamed), expected[kind])

    def test_components_and_pin_connectivity_match_across_formats(self):
        for kind, path in self.paths.items():
            with self.subTest(kind=kind):
                backend = self.open_backend(path)
                self.assertEqual(len(backend.sheets()), 1)
                sheet = reader.parse_sheet(backend, "page1")
                self.assertEqual([c["designator"] for c in sheet["components"]],
                                 ["R1"])
                parts, wires, points, ends = reader._collect_pinmap_data(
                    backend, sheet, "page1")
                nets = reader.resolve_nets_by_domain(
                    backend, sheet, parts, wires, points, ends)
                self.assertEqual(nets, {("R1", "LEFT"): "SIGNAL_A",
                                        ("R1", "RIGHT"): "SIGNAL_B"})

    def test_cli_pinmap_and_read_only_input(self):
        for kind, path in self.paths.items():
            with self.subTest(kind=kind):
                before = hashlib.sha256(path.read_bytes()).hexdigest()
                proc = self.cli(path, "pinmap", "Page", "--designator", "R1")
                self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
                rows = json.loads(proc.stdout)
                self.assertEqual(len(rows), 1)
                self.assertEqual([(p["number"], p["nets"]) for p in rows[0]["pins"]],
                                 [("1", ["SIGNAL_A"]), ("2", ["SIGNAL_B"])])
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_cli_missing_page_is_explicit(self):
        for kind, path in self.paths.items():
            with self.subTest(kind=kind):
                proc = self.cli(path, "pinmap", "MissingPage")
                self.assertEqual(proc.returncode, 2)

    def test_text_pinmap_keeps_unknown_numbers_explicit(self):
        backend = self.open_backend(self.paths["epro2"])
        # A pin may have a name but no Pin Number attribute (e.g. a net flag).
        # Exercise the common presentation contract without inventing a number.
        backend.symbol_pins("sym1")["pins"][0]["number"] = None
        args = SimpleNamespace(page="Page", schematic=None, designator=None,
                               no_domain=False, json=False)
        text = io.StringIO()
        with contextlib.redirect_stdout(text):
            reader.cmd_pinmap(backend, args)
        self.assertIn("(#  ?)", text.getvalue())
        args.json = True
        machine = io.StringIO()
        with contextlib.redirect_stdout(machine):
            reader.cmd_pinmap(backend, args)
        pins = json.loads(machine.getvalue())[0]["pins"]
        self.assertIsNone(next(p for p in pins if p["pin"] == "LEFT")["number"])

    def symbol_fixture(self, records):
        path = Path(self.temp.name) / "pin-order.epro2"
        lines = log_document("SYMBOL", "sym-order", {"title": "Generic.1"}, [
            log_record("PART", "Generic.1", {"BBOX": [-5, -5, 5, 5]})] + records)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("project2.json", "{}")
            zf.writestr("pin-order.epru", "\n".join(lines))
        return self.open_backend(path)

    def append_fixture_log(self, records):
        path = self.paths["epro2"]
        with zipfile.ZipFile(path) as zf:
            contents = {name: zf.read(name) for name in zf.namelist()}
        contents["generic.epru"] += ("\n".join(records) + "\n").encode("utf-8")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in contents.items():
                zf.writestr(name, data)
        return self.open_backend(path)

    def test_epro2_deleted_page_is_not_active(self):
        backend = self.append_fixture_log([
            log_record("DELETE_DOC", None, {"isDelete": True}, 20)])
        self.assertEqual(backend.sheets(), [])
        self.assertIsNone(backend.sheet_records("page1"))
        self.assertNotIn("page1", [d["uuid"] for d in backend.doc_metas()])

    def test_epro2_delete_header_order_whitespace_and_escapes(self):
        headers = ['{"ticket":20,"type":"DELETE_DOC"}',
                   '{     "ticket" : 20,     "type" : "DELETE_DOC"   }',
                   '{"ticket":20,"t\\u0079pe":"DELETE_DOC"}',
                   '{"ticket":20,"type":"DELETE_\\u0044OC"}']
        for header in headers:
            with self.subTest(header=header):
                self.paths["epro2"] = write_fixture(Path(self.temp.name), "epro2")
                backend = self.append_fixture_log([header + '||{"isDelete":true}|'])
                self.assertEqual(backend.sheets(), [])
                self.assertIsNone(backend.sheet_records("page1"))

    def test_epro2_dochead_and_meta_header_order(self):
        path = self.paths["epro2"]
        with zipfile.ZipFile(path) as zf:
            contents = {name: zf.read(name) for name in zf.namelist()}
        rows = []
        for line in contents["generic.epru"].decode("utf-8").splitlines():
            header, separator, body = line.partition("||")
            fields = json.loads(header)
            if fields["type"] in ("DOCHEAD", "META"):
                header = json.dumps({"ticket": fields.get("ticket", 0),
                                     "id": fields.get("id", fields["type"]),
                                     "type": fields["type"]}, indent=None)
            rows.append(header + separator + body)
        contents["generic.epru"] = ("\n".join(rows) + "\n").encode("utf-8")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in contents.items():
                zf.writestr(name, data)
        backend = self.open_backend(path)
        self.assertEqual(len(backend.sheets()), 1)
        self.assertEqual(backend.sheets()[0][1], "Board::Page")

    def test_epro2_document_restore_obeys_ticket_within_segment(self):
        backend = self.append_fixture_log([
            log_record("DELETE_DOC", None, {"isDelete": True}, 20),
            log_record("DELETE_DOC", None, {"isDelete": False}, 30),
            log_record("DELETE_DOC", None, {"isDelete": True}, 10)])
        self.assertEqual(len(backend.sheets()), 1)
        self.assertIsNotNone(backend.sheet_records("page1"))

    def test_epro2_document_restore_keeps_existing_segment_precedence(self):
        backend = self.append_fixture_log([
            log_record("DELETE_DOC", None, {"isDelete": True}, 200)] +
            log_document("SCH_PAGE", "page1", {
                "title": "Page", "schematic": "sch1"}, [
                    log_record("DELETE_DOC", None, {"isDelete": False}, 1)]))
        self.assertEqual(len(backend.sheets()), 1)
        self.assertIsNotNone(backend.sheet_records("page1"))

    def test_epro2_later_segment_can_delete_document(self):
        backend = self.append_fixture_log([
            log_record("DELETE_DOC", None, {"isDelete": False}, 200)] +
            log_document("SCH_PAGE", "page1", {
                "title": "Page", "schematic": "sch1"}, [
                    log_record("DELETE_DOC", None, {"isDelete": True}, 1)]))
        self.assertEqual(backend.sheets(), [])

    def test_epro2_attributes_may_precede_pin_geometry(self):
        backend = self.symbol_fixture([
            log_record("ATTR", "an", {"parentId": "p1", "key": "Pin Name",
                                      "value": "INPUT"}, 2),
            log_record("ATTR", "ai", {"parentId": "p1", "key": "Pin Number",
                                      "value": "7"}, 3),
            log_record("ATTR", "at", {"parentId": "p1", "key": "Pin Type",
                                      "value": "IN"}, 4),
            log_record("PIN", "p1", {"partId": "Generic.1", "x": 10,
                                      "y": 0, "length": 0}, 5)])
        pin = backend.symbol_pins("sym-order")["pins"][0]
        self.assertEqual((pin["name"], pin["number"], pin["pin_type"]),
                         ("INPUT", "7", "IN"))

    def test_epro2_null_pin_number_remains_unknown(self):
        backend = self.symbol_fixture([
            log_record("PIN", "p1", {"partId": "Generic.1", "x": 10,
                                      "y": 0, "length": 0}),
            log_record("ATTR", "an", {"parentId": "p1", "key": "Pin Name",
                                      "value": "PORT"}),
            log_record("ATTR", "ai", {"parentId": "p1", "key": "Pin Number",
                                      "value": None})])
        pin = backend.symbol_pins("sym-order")["pins"][0]
        self.assertEqual(pin["name"], "PORT")
        self.assertIsNone(pin["number"])

    def test_epro2_latest_pin_update_keeps_earlier_attributes(self):
        backend = self.symbol_fixture([
            log_record("PIN", "p1", {"partId": "Generic.1", "x": 10,
                                      "y": 0, "length": 0}, 1),
            log_record("ATTR", "an", {"parentId": "p1", "key": "Pin Name",
                                      "value": "INPUT"}, 2),
            log_record("ATTR", "ai", {"parentId": "p1", "key": "Pin Number",
                                      "value": "7"}, 3),
            log_record("PIN", "p1", {"partId": "Generic.1", "x": 25,
                                      "y": 0, "length": 0}, 10)])
        pins = backend.symbol_pins("sym-order")["pins"]
        self.assertEqual(len(pins), 1)
        self.assertEqual((pins[0]["name"], pins[0]["number"], pins[0]["x"]),
                         ("INPUT", "7", 25))

    def test_pinmap_aliases_do_not_overwrite_declared_names(self):
        backend = self.open_backend(self.paths["epro2"])
        args = SimpleNamespace(page="Page", schematic=None, designator=None,
                               no_domain=False, json=True)
        aliases = {("R1", "LEFT"): reader.NET_SEP.join(["SIGNAL_A", "SIGNAL_C"]),
                   ("R1", "RIGHT"): "SIGNAL_B"}
        output = io.StringIO()
        with patch.object(reader, "resolve_nets_by_domain", return_value=aliases), \
                contextlib.redirect_stdout(output):
            reader.cmd_pinmap(backend, args)
        pin = json.loads(output.getvalue())[0]["pins"][0]
        self.assertEqual(pin["net"], "SIGNAL_A")
        self.assertEqual(pin["nets"], ["SIGNAL_A"])
        self.assertEqual(pin.get("resolved_nets"), ["SIGNAL_A", "SIGNAL_C"])
        args.no_domain = True
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            reader.cmd_pinmap(backend, args)
        self.assertNotIn("resolved_nets", json.loads(output.getvalue())[0]["pins"][0])

    def test_unknown_json_does_not_claim_native_eprj3_support(self):
        path = Path(self.temp.name) / "generic.eprj3"
        path.write_text('{"format":"folder","profile":{}}', encoding="utf-8")
        with self.assertRaises(reader.UnsupportedFormatError):
            reader.detect_backend(path)

    def test_json_report_preserves_legacy_data(self):
        for kind, path in self.paths.items():
            with self.subTest(kind=kind):
                legacy = self.cli(path, "netlist")
                report = self.cli(path, "--json-report", "netlist")
                self.assertEqual(report.returncode, 0, report.stderr)
                payload = json.loads(report.stdout)
                self.assertEqual(payload["data"], json.loads(legacy.stdout))
                self.assertTrue(payload["complete"])
                self.assertEqual(payload["diagnostics"], [])
                self.assertEqual(payload["semantic_validation"], "not_assessed")

    def test_report_retains_query_error_status(self):
        proc = self.cli(self.paths["epro2"], "--json-report", "pinmap", "MissingPage")
        self.assertEqual(proc.returncode, 2)
        report = json.loads(proc.stdout)
        self.assertFalse(report["complete"])
        self.assertIsNone(report["data"])
        self.assertEqual(report["query_exit_code"], 2)

    def test_strict_reports_degraded_cbb_coverage(self):
        def incomplete(db, *args):
            reader._record_cbb_issue(db, "CBB_INSTANCE_TARGET_UNAVAILABLE",
                                     target="missing-template",
                                     member_overrides_applied=False)
        output = io.StringIO()
        with patch.object(sys, "argv", ["lceda_reader.py", "--eprj",
                str(self.paths["epro2"]), "--json-report", "--strict", "netlist"]), \
                patch.object(reader, "_expand_cbb", side_effect=incomplete), \
                contextlib.redirect_stdout(output), \
                contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit) as stopped:
            reader.main()
        self.assertEqual(stopped.exception.code, 3)
        report = json.loads(output.getvalue())
        self.assertFalse(report["complete"])
        self.assertEqual(report["query_exit_code"], 0)
        self.assertEqual(report["diagnostics"][0]["code"],
                         "CBB_INSTANCE_TARGET_UNAVAILABLE")
        self.assertTrue(report["data"])


class CbbReferenceTests(unittest.TestCase):
    """Invented references reproduce stale INSTANCE targets without private data."""

    def setUp(self):
        warnings = patch.object(reader, "_WARN_ONCE", set())
        warnings.start()
        self.addCleanup(warnings.stop)
        maps = patch.dict(reader._CBB_MAP, {}, clear=True)
        maps.start()
        self.addCleanup(maps.stop)
        self.sheet = {"title": "parent", "components": [
            {"cid": "block1", "designator": "B1", "symbol_uuid": "block-symbol"}]}
        self.pins = {("B1", "block1"): [
            {"sym_type": 17, "pin": "IN", "key": "IN"}]}
        self.template = {"components": [
            {"cid": "member1", "designator": "R1", "title": "Generic.1"},
            {"cid": "port1", "designator": None, "title": "IN",
             "attrs": {"Name": "IN"}}]}
        self.dom = {("R1", "LEFT"): "LOCAL", ("PORTport1", "IN"): "LOCAL"}

    def backend(self, source, mapped):
        return SimpleNamespace(
            path=Path("synthetic.epro2"), _cbb_dom_cache={}, diagnostics=[],
            cbb_instances=lambda: {("parent", "block1"): {
                "src": source, "members": {"member1": "RENAMED"}}},
            cbb_symbol_board_map=lambda: {"block-symbol": mapped} if mapped else {})

    def expand(self, db, signatures):
        result = {("B1", "IN"): "PARENT"}
        stderr = io.StringIO()
        with patch.object(reader, "_cbb_sig", return_value=signatures), \
                patch.object(reader, "_cbb_dom", return_value=self.dom) as domain, \
                patch.object(reader, "parse_sheet", return_value=self.template), \
                contextlib.redirect_stderr(stderr):
            reader._expand_cbb(db, self.sheet, self.pins, result)
        return result, domain, stderr.getvalue()

    def test_missing_instance_target_uses_available_native_mapping(self):
        db = self.backend("missing-template", "template")
        result, domain, warnings = self.expand(
            db, {"template": (frozenset({"IN"}), (), "Template")})
        domain.assert_called_once_with(db, "template")
        self.assertIn(("B1.R1", "LEFT"), result)
        self.assertNotIn(("B1.RENAMED", "LEFT"), result)
        self.assertIn("INSTANCE", warnings)
        self.assertIn("missing-template", warnings)

    def test_missing_instance_target_does_not_expand_unrelated_template(self):
        db = self.backend("missing-template", None)
        # No symbol mapping and no matching ports: retain the black-box pins.
        db._cbb_sym_map = {}
        result, domain, warnings = self.expand(
            db, {"unrelated": (frozenset({"OTHER"}), (), "Unrelated")})
        domain.assert_not_called()
        self.assertEqual(result, {("B1", "IN"): "PARENT"})
        self.assertIn("INSTANCE", warnings)

    def test_valid_instance_target_keeps_its_member_override(self):
        db = self.backend("template", "different-template")
        result, domain, warnings = self.expand(
            db, {"template": (frozenset({"IN"}), (), "Template")})
        domain.assert_called_once_with(db, "template")
        self.assertIn(("B1.RENAMED", "LEFT"), result)
        self.assertEqual(warnings, "")

    def test_missing_template_is_not_passed_to_pin_parser(self):
        db = self.backend("missing-template", None)
        stderr = io.StringIO()
        with patch.object(reader, "parse_sheet", return_value=None), \
                contextlib.redirect_stderr(stderr):
            self.assertEqual(reader._cbb_dom(db, "missing-template"), {})
        self.assertIn("missing-template", stderr.getvalue())


class SamePageAliasTests(unittest.TestCase):
    """Synthetic named nets join only through explicit wires/eligible shorts."""

    def resolve(self, page="page1", short_type=22, no_connect=False, dnp=False):
        specs = [(0, 10, "SIGNAL_A"), (20, 30, "SIGNAL_B"),
                 (40, 50, "SIGNAL_B"), (60, 70, "SIGNAL_C"),
                 (100, 110, "SIGNAL_A"), (200, 210, "SIGNAL_C")]
        wires = [(str(i), [[x, 0, y, 0]]) for i, (x, y, _n) in enumerate(specs)]
        sheet = {"title": page, "nets": [{"net": n, "points": [(x, 0), (y, 0)]}
                 for x, y, n in specs], "components": []}

        def pin(key, x, typ=2, nc=False):
            return {"pin": key, "key": key, "x": x, "y": 0,
                    "sym_type": typ, "no_connect": nc}

        pins = {"PROBE_A": [pin("1", 110)], "PROBE_C": [pin("1", 210)]}
        for idx, (x, y) in enumerate(((10, 20), (50, 60)), 1):
            cid = "s" + str(idx)
            sheet["components"].append({"cid": cid, "designator": None,
                "title": "Generic", "attrs": {}, "dnp": dnp})
            pins["SHORT" + cid] = [pin("1", x, short_type, no_connect),
                                   pin("2", y, short_type)]
        return reader.resolve_nets_by_domain(None, sheet, pins, wires, {}, {},
                                             _cbb_depth=2)

    def test_explicit_aliases_propagate_transitively_to_remote_same_named_net(self):
        result = self.resolve()
        for endpoint in (("PROBE_A", "1"), ("PROBE_C", "1")):
            self.assertEqual(reader.net_tokens(result[endpoint]),
                             ["SIGNAL_A", "SIGNAL_B", "SIGNAL_C"])

    def test_active_component_does_not_create_aliases(self):
        result = self.resolve(short_type=2)
        self.assertEqual(reader.net_tokens(result[("PROBE_A", "1")]), ["SIGNAL_A"])
        self.assertEqual(reader.net_tokens(result[("PROBE_C", "1")]), ["SIGNAL_C"])

    def test_no_connect_does_not_complete_a_short_bridge(self):
        result = self.resolve(no_connect=True)
        self.assertEqual(reader.net_tokens(result[("PROBE_A", "1")]), ["SIGNAL_A"])
        self.assertEqual(reader.net_tokens(result[("PROBE_C", "1")]), ["SIGNAL_C"])
        self.assertNotIn(("SHORTs1", "1"), result)

    def test_dnp_short_does_not_create_aliases(self):
        result = self.resolve(dnp=True)
        self.assertEqual(reader.net_tokens(result[("PROBE_A", "1")]), ["SIGNAL_A"])
        self.assertEqual(reader.net_tokens(result[("PROBE_C", "1")]), ["SIGNAL_C"])

    def test_aliases_do_not_leak_into_another_page(self):
        self.resolve(page="first")
        result = self.resolve(page="second", short_type=2)
        self.assertEqual(reader.net_tokens(result[("PROBE_A", "1")]), ["SIGNAL_A"])
        self.assertEqual(reader.net_tokens(result[("PROBE_C", "1")]), ["SIGNAL_C"])


if __name__ == "__main__":
    unittest.main()
