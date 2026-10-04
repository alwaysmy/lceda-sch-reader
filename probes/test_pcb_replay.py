"""Invented, portable PCB export/replay fixtures. No private engineering data."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import lceda_pcb as pcb


def row(kind, data, ident=None, ticket=1):
    header = {"type": kind, "ticket": ticket}
    if ident is not None:
        header["id"] = ident
    return json.dumps(header) + "||" + (json.dumps(data) if data is not None else "") + "|"


def doc(uuid="board-a", kind="PCB", client="a", title="Synthetic board", rows=()):
    return [row("DOCHEAD", {"docType": kind, "uuid": uuid, "client": client}),
            row("META", {"title": title})] + list(rows)


class ReplayTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "probes" / "tmp"
        parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.epru"

    def read(self, rows, policy="auto"):
        self.path.write_text("\n".join(rows), encoding="utf-8")
        return pcb.load_project(self.path, policy)

    def assert_code(self, code, fn):
        with self.assertRaises(pcb.PCBError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def test_unterminated_line_and_embedded_delimiter(self):
        result = self.read(doc(rows=[row("ATTR", {"value": "ends||with|pipe"}, "a")[:-1]]))
        self.assertEqual(pcb.records(pcb.select_pcb(result), "ATTR")[0]["data"]["value"], "ends||with|pipe")

    def test_tombstone_and_restore(self):
        result = self.read(doc(rows=[row("LINE", {"x": 1}, "line", 1), row("LINE", None, "line", 2),
                                            row("DELETE_DOC", {"isDelete": True}, ticket=2),
                                            row("DELETE_DOC", {"isDelete": False}, ticket=3)]))
        self.assertEqual(pcb.list_pcbs(result)[0]["tombstones"], 1)
        self.assertEqual(pcb.records(pcb.select_pcb(result), "LINE"), [])

    def test_deleted_pcb_not_selected(self):
        result = self.read(doc(rows=[row("DELETE_DOC", {"isDelete": True})]))
        self.assertEqual(pcb.list_pcbs(result), [])
        self.assert_code("PCB_SELECTION_REQUIRED", lambda: pcb.select_pcb(result, "board-a"))

    def test_disagreement_requires_policy(self):
        rows = doc(rows=[row("LINE", {"x": 9}, "line", 9)]) + doc(rows=[row("LINE", {"x": 1}, "line", 1)])
        self.assert_code("AMBIGUOUS_REPLAY_POLICY", lambda: self.read(rows))
        for policy, expected in (("segment-ticket", 1), ("ticket-client", 9)):
            result = self.read(rows, policy)
            self.assertEqual(pcb.records(pcb.select_pcb(result), "LINE")[0]["data"]["x"], expected)
            self.assertFalse(result["source"]["replay_policy_agreement"])

    def test_client_tie_break_is_explicit(self):
        rows = doc(client="a", rows=[row("LINE", {"x": 1}, "line", 2)]) + doc(client="z", rows=[row("LINE", {"x": 2}, "line", 2)])
        result = self.read(rows, "ticket-client")
        self.assertEqual(pcb.records(pcb.select_pcb(result), "LINE")[0]["data"]["x"], 1)
        self.assert_code("AMBIGUOUS_REPLAY_POLICY", lambda: self.read(rows))

    def test_equal_rank_conflict_fails(self):
        rows = doc(rows=[row("LINE", {"x": 1}, "line"), row("LINE", {"x": 2}, "line")])
        self.assert_code("CONFLICTING_EQUAL_RANK", lambda: self.read(rows))

    def test_auto_checks_equal_ranks_in_both_policies(self):
        rows = doc(rows=[row("LINE", {"x": 1}, "line", 2)]) + doc(rows=[row("LINE", {"x": 2}, "line", 2)])
        self.assert_code("CONFLICTING_EQUAL_RANK", lambda: self.read(rows))
        result = self.read(rows, "segment-ticket")
        self.assertEqual(pcb.records(pcb.select_pcb(result), "LINE")[0]["data"]["x"], 2)

    def test_nonfinite_json_is_structured_error(self):
        for value in ("1e400", "NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                rows = doc() + ['{"type":"ATTR","id":"x","ticket":2}||{"value":' + value + '}|']
                self.assert_code("NONFINITE_JSON", lambda: self.read(rows))

    def test_state_change_provenance_survives_tombstone(self):
        result = self.read(doc(rows=[row("LINE", None, "removed", 2)]))
        evidence = pcb.select_pcb(result)["state_provenance"][0]
        self.assertEqual((evidence["id"], evidence["state"], evidence["ticket"]), ("removed", "tombstone", 2))

    def test_multiple_boards_never_guess(self):
        project = self.read(doc() + doc("board-b"))
        self.assert_code("PCB_SELECTION_REQUIRED", lambda: pcb.select_pcb(project))
        self.assert_code("PCB_SELECTION_REQUIRED", lambda: pcb.select_pcb(project, "Synthetic board"))
        self.assertEqual(pcb.select_pcb(project, "board-b")["head"]["uuid"], "board-b")

    def test_archive_member_ambiguity(self):
        with zipfile.ZipFile(self.path, "w") as z:
            for name in ("a.epru", "b.epru"):
                z.writestr(name, "\n".join(doc()))
        self.assert_code("AMBIGUOUS_ARCHIVE", lambda: pcb.load_project(self.path))

    def test_archive_size_limit(self):
        with zipfile.ZipFile(self.path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("a.epru", " " * 20000)
        self.assert_code("INPUT_TOO_LARGE", lambda: pcb.load_project(self.path, max_input_bytes=1000))

    def test_native_eprj3_json_fails(self):
        self.path.write_text('{"format":"folder"}')
        self.assert_code("INVALID_HEADER", lambda: pcb.load_project(self.path))

    def test_list_cli_is_stdlib_only(self):
        self.read(doc())
        process = subprocess.run([sys.executable, "-S", str(ROOT / "lceda_pcb.py"), str(self.path), "list"],
                                 capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["pcbs"][0]["uuid"], "board-a")


if __name__ == "__main__":
    unittest.main()
