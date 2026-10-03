"""Synthetic export comparison regression; no private board files are used.

Run: python -m unittest discover -s probes -p test_pcb_export_comparison.py -v
Install optional requirements-pcb-validation.txt to exercise these tests.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import pcb_compare_exports as comparator

try:
    import gerbonara
    from gerbonara import graphic_primitives as gp
    import shapely
    from shapely.geometry import GeometryCollection, LineString, Point, box, mapping
except ImportError:
    gerbonara = None


def region(x0=0, y0=0, x1=10, y1=10):
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    return "G36*\n" + "\n".join(f"X{round(x*1000000)}Y{round(y*1000000)}D{'02' if i == 0 else '01'}*"
                                  for i, (x, y) in enumerate(pts)) + "\nG37*\n"


def gerber(body=None):
    return "%FSLAX46Y46*%\n%MOMM*%\n" + (region() if body is None else body) + "M02*\n"


def excellon(points=((5, 5),), diameter=1):
    return "M48\nMETRIC\nT01C" + f"{diameter:.6f}" + "\n%\nT01\n" + "\n".join(
        f"X{x:.6f}Y{y:.6f}" for x, y in points) + "\nM30\n"


@unittest.skipIf(gerbonara is None, "optional gerbonara/Shapely dependencies unavailable")
class ExportComparisonTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "probes" / "tmp"
        parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.hole = Point(5, 5).buffer(.5, quad_segs=256)
        self.board = box(0, 0, 10, 10)
        self.ir = {"schema_version": "lceda-pcb-ir/1", "status": "candidate", "units": "mm",
                   "source": {"sha256": hashlib.sha256(b"invented exported project").hexdigest()},
                   "pcb": {"uuid": "synthetic-pcb"}, "stackup": {"copper_order": [101, 102]},
                   "coverage": {"complete": True, "manufacturing_verified": False},
                   "vias": [{"hole_geometry": mapping(self.hole)}], "plated_through_holes": [],
                   "geometry": {"type": "FeatureCollection", "features": []}}
        for kind, geometry, extra in [("board", self.board, {}), ("substrate", self.board.difference(self.hole), {}),
                                      ("drill_holes", self.hole, {}),
                                      ("copper", self.board.difference(self.hole), {"layer": 101}),
                                      ("copper", self.board.difference(self.hole), {"layer": 102})]:
            self.ir["geometry"]["features"].append({"type": "Feature", "properties": {"kind": kind, "units": "mm", **extra},
                                                       "geometry": mapping(geometry)})
        self.ir_path = self.write("synthetic.ir.json", json.dumps(self.ir))
        self.top = self.write("synthetic-top.gbr", gerber())
        self.bottom = self.write("synthetic-bottom.gbr", gerber())
        self.drill = self.write("synthetic-all.drl", excellon())
        self.options = {"drill_exports": {"all-through": self.drill}, "gerber_units": "mm", "drill_units": "mm",
                        "offset_x_mm": 0, "offset_y_mm": 0, "tolerance_mm": .00001,
                        "max_xor_area_mm2": .001, "max_xor_fraction": .001, "min_overlap_fraction": .999}

    def write(self, name, text):
        path = self.directory / name
        path.write_text(text, encoding="utf-8")
        return path

    def save_ir(self):
        self.ir_path.write_text(json.dumps(self.ir), encoding="utf-8")

    def run_comparison(self, copper=None, **changes):
        return comparator.compare_exports(self.ir_path, copper or {101: self.top, 102: self.bottom}, **{**self.options, **changes})

    def test_complete_comparison_preserves_candidate_and_binds_every_file(self):
        original = self.ir_path.read_bytes()
        result = self.run_comparison()
        self.assertEqual(result["status"], "complete")
        self.assertTrue(result["comparison_passed"])
        self.assertFalse(result["manufacturing_verified"])
        self.assertEqual(self.ir_path.read_bytes(), original)
        self.assertEqual(result["binding"]["ir"]["sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(len(result["binding"]["exports"]), 3)
        self.assertEqual(result["binding"]["pcb_uuid"], "synthetic-pcb")
        self.assertIn("not real-board identity", result["limitations"][0])
        before = result["evidence_sha256"]
        self.top.write_text(gerber("G04 changed bytes, same geometry*\n" + region()))
        self.assertNotEqual(before, self.run_comparison()["evidence_sha256"])
        self.assertNotEqual(self.run_comparison()["evidence_sha256"], self.run_comparison(max_xor_area_mm2=.002)["evidence_sha256"])

    def test_partial_mapping_and_missing_drills_never_claim_complete(self):
        result = self.run_comparison({101: self.top}, drill_exports={})
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["comparison_passed"])
        self.assertEqual(result["coverage"]["missing_copper_layers"], [102])
        self.assertEqual(result["coverage"]["missing_drill_roles"], ["all-through"])
        self.assertFalse(result["manufacturing_verified"])

    def test_incomplete_ir_makes_full_mapping_partial(self):
        self.ir["coverage"]["complete"] = False
        self.save_ir()
        result = self.run_comparison()
        self.assertEqual(result["status"], "partial")
        self.assertIn("ir_coverage_incomplete", result["coverage"]["blockers"])

    def test_unknown_layer_and_pairing_fail_closed(self):
        with self.assertRaisesRegex(comparator.ComparisonError, "Unknown mapped"):
            self.run_comparison({999: self.top})
        for roles in ({"via-subset": self.drill}, {"all-through": self.drill, "plated-through": self.drill}):
            with self.assertRaisesRegex(comparator.ComparisonError, "Unsupported drill pairing"):
                self.run_comparison(drill_exports=roles)

    def test_missing_fill_and_offboard_artwork_are_not_clipped_away(self):
        self.top.write_text(gerber(region(x1=9)))
        result = self.run_comparison()
        self.assertFalse(result["comparison_passed"])
        self.assertAlmostEqual(result["copper"][0]["expected_only_mm2"], 10)
        self.top.write_text(gerber(region() + region(20, 20, 21, 21)))
        result = self.run_comparison()
        self.assertFalse(result["comparison_passed"])
        self.assertAlmostEqual(result["copper"][0]["export_outside_board_mm2"], 1)

    def test_disjoint_geometry_fails_even_with_permissive_xor_thresholds(self):
        result = self.run_comparison(offset_x_mm=100, max_xor_area_mm2=10000, max_xor_fraction=1, min_overlap_fraction=.0001)
        self.assertFalse(result["comparison_passed"])
        self.assertFalse(result["copper"][0]["checks"]["positive_overlap"])

    def test_explicit_translation_applies_to_copper_and_drills(self):
        self.top.write_text(gerber(region(10, 20, 20, 30)))
        self.bottom.write_text(gerber(region(10, 20, 20, 30)))
        self.drill.write_text(excellon(((15, 25),)))
        result = self.run_comparison(offset_x_mm=-10, offset_y_mm=-20)
        self.assertTrue(result["comparison_passed"])
        self.assertEqual(result["binding"]["parameters"]["export_to_ir_translation_mm"], [-10, -20])

    def test_empty_unknown_and_truncated_exports_are_rejected(self):
        for text in ("", gerber(""), gerber("G999*\n" + region()), gerber()[:-5], gerber().replace("M02*", "%IFother.gbr*%\nM02*")):
            with self.subTest(text=text[:20]):
                self.top.write_text(text)
                with self.assertRaises((comparator.ComparisonError, SyntaxError)):
                    self.run_comparison()
        self.top.write_text(gerber())
        for text in ("", excellon(()), excellon().replace("M30", "")):
            self.drill.write_text(text)
            with self.assertRaises(comparator.ComparisonError):
                self.run_comparison()

    def test_wrong_units_nan_thresholds_and_empty_ir_geometry_are_rejected(self):
        with self.assertRaisesRegex(comparator.ComparisonError, "declared units"):
            self.run_comparison(gerber_units="inch")
        for field, value in [("offset_x_mm", float("nan")), ("tolerance_mm", 0), ("max_xor_fraction", 2),
                             ("max_xor_area_mm2", -1), ("min_overlap_fraction", 0)]:
            with self.subTest(field=field), self.assertRaises(comparator.ComparisonError):
                self.run_comparison(**{field: value})
        self.ir["geometry"]["features"][3]["geometry"] = mapping(GeometryCollection())
        self.save_ir()
        with self.assertRaisesRegex(comparator.ComparisonError, "empty"):
            self.run_comparison()

    def test_layer_clear_polarity(self):
        raw = gerber("%ADD10C,2*%\nD10*\nX0Y0D03*\nX5000000Y0D03*\n%LPC*%\n%ADD11C,1*%\nD11*\nX0Y0D03*\n").encode()
        geometry, stats = comparator.gerber_geometry(raw, "synthetic.gbr", expected_units="mm", tolerance_mm=.00001)
        self.assertAlmostEqual(geometry.area, 1.75 * math.pi, places=3)
        self.assertFalse(geometry.contains(Point(0, 0)))
        self.assertTrue(geometry.contains(Point(5, 0)))
        self.assertEqual(stats["clear_objects"], 1)

    def test_macro_local_clearing_preserves_existing_artwork(self):
        raw = gerber("%AMANN*1,1,2,0,0*1,0,1,0,0*%\n%ADD10C,0.2*%\n%ADD11ANN*%\nD10*\nX0Y0D03*\nD11*\nX0Y0D03*\n").encode()
        geometry, _ = comparator.gerber_geometry(raw, "synthetic.gbr", expected_units="mm", tolerance_mm=.00001)
        self.assertTrue(geometry.contains(Point(0, 0)))
        self.assertFalse(geometry.contains(Point(.25, 0)))
        self.assertTrue(geometry.contains(Point(.75, 0)))

    def test_region_arc_and_rotated_rectangle(self):
        geometry = comparator.primitive_geometry(gp.Rectangle(0, 0, 2, 1, math.pi / 4), .00001)
        self.assertAlmostEqual(geometry.area, 2)
        arc = gp.ArcPoly([(0, 0), (0, 0), (1, 0), (0, 1)], [(False, (0, 0)), None, None])
        self.assertAlmostEqual(comparator.primitive_geometry(arc, .00001).area, .5)
        raw = gerber("G75*\n%ADD10C,0.5*%\nD10*\nX1000000Y0D02*\nG03X0Y1000000I-1000000J0D01*\n").encode()
        geometry, _ = comparator.gerber_geometry(raw, "arc.gbr", expected_units="mm", tolerance_mm=.00001)
        self.assertAlmostEqual(geometry.area, 5 * math.pi / 16, places=4)
        with self.assertRaisesRegex(comparator.ComparisonError, "Unsupported"):
            comparator.primitive_geometry(object(), .00001)

    def test_split_drills_are_complete_when_ir_has_only_plated_holes(self):
        result = self.run_comparison(drill_exports={"plated-through": self.drill})
        self.assertEqual(result["status"], "complete")
        self.assertTrue(result["comparison_passed"])

    def test_split_drills_missing_nonplated_are_partial(self):
        npth = Point(7, 7).buffer(.5, quad_segs=256)
        holes = self.hole.union(npth)
        self.ir["geometry"]["features"][2]["geometry"] = mapping(holes)
        self.ir["geometry"]["features"][1]["geometry"] = mapping(self.board.difference(holes))
        for feature in self.ir["geometry"]["features"][3:]:
            feature["geometry"] = mapping(self.board.difference(holes))
        self.save_ir()
        result = self.run_comparison(drill_exports={"plated-through": self.drill})
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["coverage"]["missing_drill_roles"], ["nonplated-through"])
        npth_file = self.write("synthetic-npth.drl", excellon(((7, 7),)))
        result = self.run_comparison(drill_exports={"plated-through": self.drill, "nonplated-through": npth_file})
        self.assertEqual(result["status"], "complete")
        self.assertTrue(result["comparison_passed"])
        npth_file.write_text(excellon())
        with self.assertRaisesRegex(comparator.ComparisonError, "Duplicate drill"):
            self.run_comparison(drill_exports={"plated-through": self.drill, "nonplated-through": npth_file})

    def test_wrong_drill_diameter_and_missing_hole_fail(self):
        self.drill.write_text(excellon(diameter=.5))
        self.assertFalse(self.run_comparison()["comparison_passed"])
        self.drill.write_text(excellon(((5, 5), (7, 7))))
        self.assertFalse(self.run_comparison()["comparison_passed"])

    def test_drill_slot_geometry(self):
        self.drill.write_text("M48\nMETRIC\nT01C1.0\n%\nT01\nX4.000000Y5.000000G85X6.000000Y5.000000\nM30\n")
        geometry, metadata = comparator.drill_geometry(self.drill.read_bytes(), self.drill.name, role="all-through",
                                                       expected_units="mm", tolerance_mm=.00001)
        self.assertAlmostEqual(geometry.area, 2 + math.pi / 4, places=3)
        self.assertEqual(metadata["object_types"], {"Line": 1})

    def test_cli_required_parameters_and_partial_exit_status(self):
        script = str(ROOT / "scripts" / "pcb_compare_exports.py")
        command = [sys.executable, script, "--ir", str(self.ir_path), "--copper", f"101={self.top}",
                   "--gerber-units", "mm", "--offset-x-mm", "0", "--offset-y-mm", "0", "--tolerance-mm", ".00001",
                   "--max-xor-area-mm2", ".001", "--max-xor-fraction", ".001", "--min-overlap-fraction", ".999"]
        run = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertEqual(json.loads(run.stdout)["status"], "partial")
        before = self.ir_path.read_bytes()
        run = subprocess.run(command + ["--out", str(self.ir_path)], text=True, capture_output=True)
        self.assertEqual(run.returncode, 2)
        self.assertEqual(self.ir_path.read_bytes(), before)
        run = subprocess.run(command + ["--copper", f"101={self.bottom}"], text=True, capture_output=True)
        self.assertEqual(run.returncode, 2)

    def test_unknown_copper_order_uses_feature_set_and_stays_partial(self):
        self.ir["stackup"] = {"copper_order": None, "active_copper_layers": [101, 102]}
        self.ir["coverage"]["complete"] = False
        self.save_ir()
        result = self.run_comparison()
        self.assertTrue(result["comparison_passed"])
        self.assertEqual(result["coverage"]["missing_copper_layers"], [])
        self.assertEqual(result["status"], "partial")

    def test_unified_holes_drive_drill_roles_and_reject_inconsistent_entities(self):
        self.ir["holes"] = [{"kind": "via", "plated": True, "geometry": mapping(self.hole)}]
        self.save_ir()
        self.assertEqual(self.run_comparison(drill_exports={"plated-through": self.drill})["status"], "complete")
        self.ir["holes"][0]["geometry"] = mapping(Point(5, 5).buffer(.1))
        self.save_ir()
        with self.assertRaisesRegex(comparator.ComparisonError, "disagree"):
            self.run_comparison(drill_exports={"plated-through": self.drill})

    def test_inch_exports_convert_to_millimetres_and_crlf_is_supported(self):
        # Synthetic one-inch square in native inch units, then an inch drill.
        raw = ("%FSLAX46Y46*%\n%MOIN*%\n" + region(x1=1, y1=1) + "M02*\n").replace("\n", "\r\n").encode()
        geometry, _ = comparator.gerber_geometry(raw, "inch.gbr", expected_units="inch", tolerance_mm=.00001)
        self.assertAlmostEqual(geometry.area, 25.4**2)
        raw = b"M48\r\nINCH,TZ,00.0000\r\nT01C0.1\r\n%\r\nT01\r\nX0.5Y0.5\r\nM30\r\n"
        geometry, _ = comparator.drill_geometry(raw, "inch.drl", role="all-through", expected_units="inch", tolerance_mm=.00001)
        self.assertAlmostEqual(geometry.centroid.x, 12.7)
        self.assertAlmostEqual(geometry.area, math.pi*1.27**2, places=3)

    def test_export_eof_cannot_hide_ignored_geometry(self):
        self.top.write_text(gerber() + region(20, 20, 30, 30) + "M02*\n")
        with self.assertRaisesRegex(comparator.ComparisonError, "M02"):
            self.run_comparison()
        self.top.write_text(gerber().replace("%FSLAX46Y46*%", ""))
        with self.assertRaisesRegex(comparator.ComparisonError, "coordinate format"):
            self.run_comparison()
        self.top.write_text(gerber())
        self.drill.write_text(excellon() + "M30\n")
        with self.assertRaisesRegex(comparator.ComparisonError, "M30"):
            self.run_comparison()

    def test_plating_metadata_and_overlapping_split_drills_rejected(self):
        raw = excellon().replace("METRIC", "METRIC\n;TYPE=NON_PLATED").encode()
        with self.assertRaisesRegex(comparator.ComparisonError, "plating contradicts"):
            comparator.drill_geometry(raw, "npth.drl", role="plated-through", expected_units="mm", tolerance_mm=.00001)
        npth = Point(7, 7).buffer(.5, quad_segs=256)
        self.ir["geometry"]["features"][2]["geometry"] = mapping(self.hole.union(npth))
        self.save_ir()
        overlapping = self.write("overlapping.drl", excellon(((5, 5), (7, 7))))
        with self.assertRaisesRegex(comparator.ComparisonError, "overlap"):
            self.run_comparison(drill_exports={"plated-through": self.drill, "nonplated-through": overlapping})

    def test_full_circle_and_clockwise_arc_have_correct_area(self):
        full = gp.Arc(1, 0, 1, 0, 0, 0, False, .5)
        self.assertAlmostEqual(comparator.primitive_geometry(full, .00001).area, math.pi, places=4)
        cw = gp.Arc(0, 1, 1, 0, 0, 0, True, .5)
        self.assertAlmostEqual(comparator.primitive_geometry(cw, .00001).area, 5*math.pi/16, places=4)

    def test_cli_structured_failure_and_complete_success(self):
        script = str(ROOT / "scripts" / "pcb_compare_exports.py")
        command = [sys.executable, script, "--ir", str(self.ir_path),
                   "--copper", f"101={self.top}", "--copper", f"102={self.bottom}",
                   "--drill", f"all-through={self.drill}", "--gerber-units", "mm", "--drill-units", "mm",
                   "--offset-x-mm", "0", "--offset-y-mm", "0", "--tolerance-mm", ".00001",
                   "--max-xor-area-mm2", ".001", "--max-xor-fraction", ".001", "--min-overlap-fraction", ".999"]
        run = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["status"], "complete")
        alias = self.directory / "ir-hardlink.json"
        os.link(self.ir_path, alias)
        run = subprocess.run(command + ["--out", str(alias)], text=True, capture_output=True)
        self.assertEqual(run.returncode, 2)
        self.assertEqual(json.loads(run.stderr)["status"], "error")
        self.drill.write_text(excellon().replace("T01C1.000000", "T01C1"))
        run = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(run.returncode, 2)
        self.assertEqual(json.loads(run.stderr)["status"], "error")

    def test_self_touching_region_requires_explicit_audited_repair(self):
        # Invented 10x10 outer square with a 2x2 hole, reached by retracing
        # a zero-width bridge. This is not just an adjacent duplicate vertex.
        points = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 5),
                  (4, 5), (4, 6), (6, 6), (6, 4), (4, 4), (4, 5), (0, 5), (0, 0)]
        body = "G36*\n" + "\n".join(f"X{x*1000000}Y{y*1000000}D{'02' if i == 0 else '01'}*"
                                      for i, (x, y) in enumerate(points)) + "\nG37*\n"
        raw = gerber(body).encode()
        with self.assertRaisesRegex(comparator.ComparisonError, "invalid"):
            comparator.gerber_geometry(raw, "invented.gbr", expected_units="mm", tolerance_mm=.0001)
        geometry, parser = comparator.gerber_geometry(raw, "invented.gbr", expected_units="mm", tolerance_mm=.0001,
                                                     repair_invalid=True)
        self.assertAlmostEqual(geometry.area, 96)
        self.assertFalse(geometry.contains(Point(5, 5)))
        audit = parser["geometry_repairs"][0]
        self.assertEqual(audit["source"]["object_index"], 0)
        self.assertEqual(audit["source"]["primitive_index"], 0)
        self.assertEqual(audit["discarded_types"], {"LineString": 1})
        self.assertEqual(audit["area_delta_mm2"], 0)
        self.assertIn("geometry_before", audit)
        self.assertIn("geometry_after", audit)
        self.assertNotEqual(audit["before_wkb_sha256"], audit["after_wkb_sha256"])
        self.top.write_bytes(raw)
        result = self.run_comparison(repair_invalid=True, max_xor_area_mm2=10, max_xor_fraction=.1)
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["manufacturing_verified"])
        self.assertEqual(result["export_geometry_repair_count"], 1)
        self.assertIn("export_geometry_repairs_applied", result["coverage"]["blockers"])

    def test_self_crossing_primitive_records_area_change_and_default_rejects(self):
        p = gp.ArcPoly([(0, 0), (2, 2), (0, 2), (2, 0)], [])
        with self.assertRaisesRegex(comparator.ComparisonError, "invalid"):
            comparator.primitive_geometry(p, .0001)
        audit = []
        geometry = comparator.primitive_geometry(p, .0001, repair_invalid=True, repairs=audit)
        self.assertAlmostEqual(geometry.area, 2)
        self.assertAlmostEqual(audit[0]["area_before_mm2"], 0)
        self.assertAlmostEqual(audit[0]["area_delta_mm2"], 2)
        self.assertEqual(audit[0]["type_after"], "MultiPolygon")

    def test_repair_opt_in_without_repair_does_not_degrade_clean_comparison(self):
        result = self.run_comparison(repair_invalid=True)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["export_geometry_repair_count"], 0)

    def test_nonarea_remnants_require_explicit_audited_removal(self):
        geometry = GeometryCollection([box(0, 0, 1, 1), LineString([(2, 0), (2, 1e-12)])])
        with self.assertRaisesRegex(comparator.ComparisonError, "non-polygonal"):
            comparator._export_polygonal(geometry, "composed aperture", repair_invalid=False, repairs=[], source={})
        repairs = []
        result = comparator._export_polygonal(geometry, "composed aperture", repair_invalid=True, repairs=repairs,
                                              source={"stage": "aperture_composition"})
        self.assertAlmostEqual(result.area, 1)
        self.assertEqual(repairs[0]["reason"], "nonpolygonal_remnants")
        self.assertEqual(repairs[0]["discarded_types"], {"LineString": 1})
        self.assertEqual(len(repairs[0]["discarded_nonarea_geometry"]["geometries"]), 1)

    def test_excellon_absolute_mode_after_header_is_applied_and_reported(self):
        raw = excellon().replace("%\nT01", "%\nG05\nG90\nT01").encode()
        geometry, metadata = comparator.drill_geometry(raw, "invented.drl", role="all-through", expected_units="mm",
                                                       tolerance_mm=.00001)
        self.assertAlmostEqual(geometry.centroid.x, 5)
        self.assertAlmostEqual(geometry.centroid.y, 5)
        self.assertEqual(metadata["parser_warnings"][0]["code"], "EXCELLON_G90_AFTER_HEADER")
        with self.assertRaises(comparator.ComparisonError):
            comparator.drill_geometry(raw.replace(b"G90", b"G999"), "invented.drl", role="all-through",
                                       expected_units="mm", tolerance_mm=.00001)


if __name__ == "__main__":
    unittest.main()
