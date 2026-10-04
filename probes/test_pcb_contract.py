"""Public CLI/schema contract checks using only invented PCB inputs."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from test_pcb_geometry import fixture, geometry
from test_pcb_replay import doc
try:
    import jsonschema
except ImportError:
    jsonschema = None


@unittest.skipIf(geometry is None, "Shapely 2 is optional")
class ContractTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "probes" / "tmp"
        parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.epru"
        board, footprint = fixture()
        self.path.write_text("\n".join(doc(rows=board) + doc("footprint-a", "FOOTPRINT", rows=footprint)), encoding="utf-8")

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "lceda_pcb.py"), str(self.path), *args],
                              capture_output=True, text=True, timeout=30)

    def test_explicit_profile_and_machine_output(self):
        missing = self.cli("extract")
        self.assertNotEqual(missing.returncode, 0)
        process = self.cli("extract", "--profile", "observed-export-v1", "--include-primitives", "--strict")
        self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
        result = json.loads(process.stdout)
        self.assertEqual(result["schema_version"], "lceda-pcb-ir/1")
        self.assertFalse(result["coverage"]["manufacturing_verified"])

    def test_output_never_overwrites_source_or_previous_result(self):
        before = self.path.read_bytes()
        process = self.cli("extract", "--profile", "observed-export-v1", "-o", str(self.path))
        self.assertEqual(process.returncode, 2)
        self.assertEqual(json.loads(process.stdout)["diagnostics"][0]["code"], "OUTPUT_EXISTS")
        self.assertEqual(before, self.path.read_bytes())
        output = Path(self.temp.name) / "candidate.json"
        first = self.cli("extract", "--profile", "observed-export-v1", "-o", str(output))
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(output.read_text())["status"], "candidate")
        self.assertEqual(self.cli("extract", "--profile", "observed-export-v1", "-o", str(output)).returncode, 2)

    def test_strict_partial_stackup_returns_three(self):
        lines = [line for line in self.path.read_text().splitlines() if '"LAYER_PHYS"' not in line]
        self.path.write_text("\n".join(lines))
        partial = self.cli("extract", "--profile", "observed-export-v1", "--strict")
        self.assertEqual(partial.returncode, 3, partial.stderr + partial.stdout)
        self.assertIsNone(json.loads(partial.stdout)["stackup"]["copper_order"])
        required = self.cli("extract", "--profile", "observed-export-v1", "--require-stackup")
        self.assertEqual(required.returncode, 2)
        self.assertEqual(json.loads(required.stdout)["diagnostics"][0]["code"], "STACKUP_REQUIRED")

    @unittest.skipIf(jsonschema is None, "jsonschema is a test-only optional dependency")
    def test_schema_accepts_candidate_rejects_false_verification(self):
        schema = json.loads((ROOT / "schemas" / "pcb-ir-v1.schema.json").read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        result = json.loads(self.cli("extract", "--profile", "observed-export-v1", "--include-primitives").stdout)
        jsonschema.validate(result, schema)
        forged = copy.deepcopy(result)
        forged["coverage"]["manufacturing_verified"] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(forged, schema)
        missing = copy.deepcopy(result)
        missing["geometry"]["features"] = []
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(missing, schema)
        missing = copy.deepcopy(result)
        copper = next(f for f in missing["geometry"]["features"] if f["properties"]["kind"] == "copper")
        del copper["properties"]["layer"]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(missing, schema)
        del forged["units"]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(forged, schema)


if __name__ == "__main__":
    unittest.main()
