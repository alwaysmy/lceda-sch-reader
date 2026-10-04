"""Portable invented 2/4/6-layer boards; requires optional Shapely 2 backend."""
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import lceda_pcb as pcb
from test_pcb_replay import doc, row

try:
    import lceda_pcb_geometry as geometry
    from shapely.geometry import Point, shape
except ImportError:
    geometry = None


def layer(ident, kind):
    return row("LAYER", {"layerType": kind, "layerName": kind + str(ident), "use": True}, json.dumps(["LAYER", ident]))


def physical(ident, order, thickness):
    return row("LAYER_PHYS", {"zIndex": order, "thickness": thickness, "material": "synthetic"}, json.dumps(["LAYER_PHYS", ident]))


def fixture(copper_count=4):
    copper = [101] + list(range(215, 215 + copper_count - 2)) + [102]
    board = [layer(101, "TOP"), layer(102, "BOTTOM"), layer(112, "MULTI"), layer(111, "OUTLINE")]
    board += [layer(i, "SIGNAL") for i in copper[1:-1]]
    for i, ident in enumerate(copper):
        board.append(physical(ident, 2 * i, 1))
        if i < len(copper) - 1:
            board.append(physical(300 + i, 2 * i + 1, 10))
    board += [row("POLY", {"layerId": 111, "polyType": "BOARD_OUTLINE", "path": [0, 0, "L", 1000, 0, 1000, 800, 0, 800]}, "outline"),
              row("VIA", {"centerX": 100, "centerY": 100, "holeDiameter": 10, "viaDiameter": 20, "viaType": "NORMAL", "ruleName": "", "netName": "GROUND"}, "via"),
              row("LINE", {"layerId": 101, "startX": 100, "startY": 100, "endX": 400, "endY": 100, "width": 8, "netName": "GROUND"}, "track"),
              row("COMPONENT", {"layerId": 102, "x": 500, "y": 400, "angle": 90, "attrs": {"Footprint": "footprint-a", "Designator": "J1"}}, "component"),
              row("PAD_NET", {"padNet": "GROUND"}, json.dumps(["PAD_NET", "component", "1", "pad"])),
              row("POUR", {"layerId": 101, "netName": "GROUND", "path": [0, 0, "L", 1000, 0, 1000, 800, 0, 800], "pourType": {"pourType": "SOLID", "fineness": 4}}, "pour", 2),
              row("POURED", {"pourFill": [{"fill": True, "strokeWidth": 0, "path": [10, 10, "L", 40, 10, 40, 30, 10, 30]}]}, json.dumps(["POURED", "pour"]), 3)]
    footprint = [layer(1, "TOP"), layer(2, "BOTTOM"), layer(12, "MULTI"),
                 row("PAD", {"layerId": 1, "centerX": 20, "centerY": 10, "padAngle": 0, "num": "1", "defaultPad": {"padType": "RECT", "width": 30, "height": 10, "radius": 0}, "hole": None, "plated": False}, "pad")]
    return board, footprint


@unittest.skipIf(geometry is None, "optional Shapely 2 dependency is not installed")
class GeometryTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "probes" / "tmp"
        parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.epru"

    def project(self, board=None, footprint=None, count=4):
        base_board, base_fp = fixture(count)
        self.path.write_text("\n".join(doc(rows=base_board if board is None else board) +
                                      doc("footprint-a", "FOOTPRINT", rows=base_fp if footprint is None else footprint)), encoding="utf-8")
        return pcb.load_project(self.path)

    def extract(self, board=None, footprint=None, count=4, **kwargs):
        return pcb.extract_pcb(self.project(board, footprint, count), profile="observed-export-v1", **kwargs)

    def assert_code(self, code, fn):
        with self.assertRaises(pcb.PCBError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def replace(self, rows, kind, update):
        result = []
        for text in rows:
            h, body = text[:-1].split("||")
            h, body = json.loads(h), json.loads(body)
            if h["type"] == kind:
                update(body)
            result.append(row(h["type"], body, h.get("id"), h["ticket"]))
        return result

    def test_dynamic_two_four_six_layers(self):
        for count in (2, 4, 6):
            with self.subTest(count=count):
                ir = self.extract(count=count)
                self.assertEqual(len(ir["stackup"]["copper_order"]), count)
                self.assertEqual(ir["vias"][0]["start_layer"], 101)
                self.assertEqual(len(ir["vias"][0]["copper_layers"]), count)
                self.assertAlmostEqual(ir["stackup"]["total_thickness_mm"], (count + 10 * (count - 1)) * geometry.MIL)
                self.assertTrue(ir["coverage"]["complete"])
                self.assertFalse(ir["coverage"]["manufacturing_verified"])

    def test_units_cache_stroke_and_bottom_transform(self):
        ir = self.extract(include_primitives=True)
        board = shape(ir["geometry"]["features"][0]["geometry"])
        self.assertAlmostEqual(board.area, 1000 * 800 * geometry.MIL ** 2)
        pad = ir["pads"][0]
        self.assertEqual(pad["layers"], [102])
        # (20,10) -> mirrorY (20,-10) -> rotate90 (10,20) -> (510,420).
        self.assertAlmostEqual(pad["center_mm"][0], 510 * geometry.MIL)
        self.assertAlmostEqual(pad["center_mm"][1], 420 * geometry.MIL)
        fill = next(p for p in ir["primitive_provenance"] if p["kind"] == "POURED")
        bounds = shape(fill["geometry"]).bounds
        self.assertAlmostEqual(bounds[0], 10 * geometry.CACHE - 2 * geometry.MIL)
        self.assertAlmostEqual(bounds[2], 40 * geometry.CACHE + 2 * geometry.MIL)

    def test_arc_sign_and_sagitta(self):
        for angle, sign in ((180, -1), (-180, 1)):
            points = geometry.arc_points((-100, 0), (100, 0), angle)
            self.assertEqual(points[0], (-100, 0))
            self.assertEqual(points[-1], (100, 0))
            self.assertTrue(all(p[1] * sign >= -1e-10 for p in points))
            for a, b in zip(points, points[1:]):
                sagitta = (100 - math.hypot((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)) * geometry.MIL
                self.assertLessEqual(sagitta, geometry.TOLERANCE_MM * 1.000001)

    def test_thick_arc_splits_centerline_and_buffer_error_budget(self):
        g = geometry.primitive_shape("ARC", {"startX": 1, "startY": 0, "endX": 0,
                                            "endY": 1, "angle": 90, "width": 100})
        error = max(Point(51 * math.cos(i * math.pi / 2000), 51 * math.sin(i * math.pi / 2000)).distance(g)
                    for i in range(1001)) * geometry.MIL
        self.assertLessEqual(error, geometry.TOLERANCE_MM * 1.000001)

    def test_round_hole_and_offset_slot(self):
        body = {"hole": {"holeType": "ROUND", "width": 80, "height": 20}, "centerX": 10, "centerY": 20,
                "padAngle": 90, "relativeAngle": 0, "padOffsetX": 3, "padOffsetY": 4}
        g = geometry.hole_shape(body)
        self.assertAlmostEqual(g.centroid.x, 6)
        self.assertAlmostEqual(g.centroid.y, 23)
        self.assertAlmostEqual(g.bounds[2] - g.bounds[0], 20)
        body.update(hole={"holeType": "SLOT", "width": 60, "height": 20}, padOffsetX=0, padOffsetY=0,
                    centerX=0, centerY=0, relativeAngle=90)
        self.assertEqual(tuple(round(v, 8) for v in geometry.hole_shape(body).bounds), (-30, -10, 30, 10))

    def test_polygon_pad_does_not_double_apply_local_position(self):
        body = {"defaultPad": {"padType": "POLYGON", "path": [10, 20, "L", 40, 20, 10, 50]},
                "centerX": 20, "centerY": 30, "padAngle": 90}
        g = geometry.pad_shape(body)
        self.assertEqual(g.bounds, (10, 20, 40, 50))

    def test_board_hole_stays_out_of_copper(self):
        board, fp = fixture()
        board = self.replace(board, "POLY", lambda b: b.update(path=[b["path"], [200, 200, "L", 300, 200, 300, 300, 200, 300]]))
        ir = self.extract(board, fp)
        copper = shape(next(f["geometry"] for f in ir["geometry"]["features"] if f["properties"].get("layer") == 101))
        self.assertFalse(copper.covers(Point(250 * geometry.MIL, 250 * geometry.MIL)))

    def test_orphan_cache_is_ignored(self):
        board, fp = fixture()
        board += [row("POURED", {"pourFill": [{"fill": True, "path": [0, 0, "L", 100, 0, 100, 80, 0, 80]}]}, json.dumps(["POURED", "removed"]))]
        ir = self.extract(board, fp)
        self.assertEqual(len(ir["poured_cache_audit"]), 2)
        self.assertTrue(any(d["code"] == "ORPHAN_CACHE_IGNORED" for d in ir["diagnostics"]))
        self.assertEqual(sum(p["kind"] == "POURED" for p in ir["primitive_provenance"]), 1)

    def test_missing_cache_never_substitutes_boundary(self):
        board, fp = fixture()
        board = [r for r in board if json.loads(r.split("||")[0])["type"] != "POURED"]
        self.assert_code("MISSING_POUR_CACHE", lambda: self.extract(board, fp))

    def test_stale_cache_is_rejected(self):
        board, fp = fixture()
        board = [text.replace('"ticket": 3', '"ticket": 1') if '"POURED"' in text else text for text in board]
        self.assert_code("STALE_POUR_CACHE", lambda: self.extract(board, fp))

    def test_unknown_copper_and_multilayer_regions_rejected(self):
        board, fp = fixture()
        for kind in ("TEXT", "REGION", "POLY"):
            code = {"TEXT": "UNSUPPORTED_FOOTPRINT_COPPER", "REGION": "UNSUPPORTED_REGION", "POLY": "UNSUPPORTED_COPPER_GEOMETRY"}[kind]
            self.assert_code(code,
                             lambda kind=kind: self.extract(board, fp + [row(kind, {"layerId": 1}, "unknown")]))
        self.assert_code("UNSUPPORTED_MULTI_CUTOUT", lambda: self.extract(board, fp + [row("FILL", {"layerId": 12}, "unknown")]))

    def test_missing_pad_net_remains_null(self):
        board, fp = fixture()
        board = [r for r in board if json.loads(r.split("||")[0])["type"] != "PAD_NET"]
        ir = self.extract(board, fp)
        self.assertIsNone(ir["pads"][0]["net"])
        self.assertFalse(ir["coverage"]["complete"])

    def test_missing_and_deleted_footprints_fail(self):
        board, fp = fixture()
        self.assert_code("MISSING_FOOTPRINT", lambda: self.extract(self.replace(board, "COMPONENT", lambda b: b["attrs"].update(Footprint="absent")), fp))
        self.assert_code("MISSING_FOOTPRINT", lambda: self.extract(board, fp + [row("DELETE_DOC", {"isDelete": True})]))

    def test_rule_spanned_via_rejected(self):
        board, fp = fixture()
        self.assert_code("UNSUPPORTED_VIA_SPAN", lambda: self.extract(self.replace(board, "VIA", lambda b: b.update(ruleName="blind")), fp))

    def test_invalid_geometry_requires_explicit_audited_repair(self):
        board, fp = fixture()
        board += [row("FILL", {"layerId": 101, "fillStyle": "SOLID", "path": [50, 50, "L", 90, 90, 50, 90, 90, 50]}, "bowtie")]
        self.assert_code("INVALID_POLYGON", lambda: self.extract(board, fp))
        ir = self.extract(board, fp, repair_invalid=True)
        self.assertFalse(ir["coverage"]["geometry_complete"])
        self.assertTrue(ir["geometry_repairs"])

    def test_missing_stackup_never_fabricates_thickness(self):
        board, fp = fixture(2)
        board = [r for r in board if json.loads(r.split("||")[0])["type"] != "LAYER_PHYS"]
        ir = self.extract(board, fp)
        self.assertFalse(ir["coverage"]["stackup_complete"])
        self.assertIsNone(ir["stackup"]["total_thickness_mm"])
        board, fp = fixture(4)
        board = [r for r in board if json.loads(r.split("||")[0])["type"] != "LAYER_PHYS"]
        ir = self.extract(board, fp)
        self.assertIsNone(ir["stackup"]["copper_order"])
        self.assertEqual(len(ir["stackup"]["active_copper_layers"]), 4)
        self.assertFalse(ir["coverage"]["complete"])

    def test_duplicate_physical_order_rejected(self):
        board, fp = fixture()
        board += [physical(999, 0, 1)]
        self.assert_code("INVALID_STACKUP", lambda: self.extract(board, fp))

    def test_hole_span_and_special_pad_fail_closed(self):
        board, fp = fixture()
        modified = self.replace(fp, "PAD", lambda b: b.update(hole={"holeType": "ROUND", "width": 5, "height": 5}, plated=True))
        self.assert_code("UNSUPPORTED_HOLE_SPAN", lambda: self.extract(board, modified))
        modified = self.replace(fp, "PAD", lambda b: b.update(specialPad={"1": {}}))
        self.assert_code("UNSUPPORTED_PAD", lambda: self.extract(board, modified))

    def test_input_hash_unchanged_and_result_serializable(self):
        project = self.project()
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        result = pcb.extract_pcb(project, profile="observed-export-v1")
        json.dumps(result, allow_nan=False)
        self.assertEqual(digest, hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(result["source"]["sha256"], digest)

    def test_layer_missing_from_primitive_fails(self):
        board, fp = fixture()
        modified = self.replace(fp, "PAD", lambda b: b.pop("layerId"))
        self.assert_code("MISSING_PRIMITIVE_LAYER", lambda: self.extract(board, modified))
        self.assert_code("MISSING_PRIMITIVE_LAYER", lambda: self.extract(board + [row("REGION", {
            "regionType": "PROHIBIT", "prohibitType": ["COPPER"],
            "path": [0, 0, "L", 1, 0, 0, 1]}, "missing-layer")], fp))

    def test_board_multi_unknown_layer_and_record_fail_closed(self):
        board, fp = fixture()
        self.assert_code("UNSUPPORTED_MULTI_CUTOUT", lambda: self.extract(board + [row("FILL", {"layerId": 112}, "multi")], fp))
        self.assert_code("MISSING_PRIMITIVE_LAYER", lambda: self.extract(board + [row("REGION", {"layerId": 999}, "missing")], fp))
        self.assert_code("UNSUPPORTED_RECORD", lambda: self.extract(board + [row("NEW_GEOMETRY", {}, "unknown")], fp))

    def test_missing_interlayer_separations_make_stackup_partial(self):
        board, fp = fixture()
        board = [text for text in board if json.loads(text.split("||")[0]).get("id") not in (json.dumps(["LAYER_PHYS", 300]), json.dumps(["LAYER_PHYS", 301]))]
        ir = self.extract(board, fp)
        self.assertFalse(ir["coverage"]["stackup_complete"])
        self.assertIsNone(ir["stackup"]["total_thickness_mm"])
        self.assertTrue(all(layer["z_depth_mm"] is None for layer in ir["stackup"]["layers"]))

    def test_inactive_footprint_copper_rejected(self):
        board, fp = fixture()
        modified = self.replace(fp, "LAYER", lambda b: b.update(use=False))
        self.assert_code("INACTIVE_FOOTPRINT_LAYER", lambda: self.extract(board, modified))

    def test_extreme_curves_fail_with_bounded_machine_error(self):
        self.assert_code("GEOMETRY_LIMIT", lambda: geometry._quad_segments(1e20))
        self.assert_code("GEOMETRY_LIMIT", lambda: geometry.arc_points((0, 0), (1e20, 0), 90))

    def test_partition_and_unclassified_overrides_rejected(self):
        board, fp = fixture()
        self.assert_code("UNSUPPORTED_PARTITION", lambda: self.extract(self.replace(board, "LINE", lambda b: b.update(partitionId="flex-a")), fp))
        self.assert_code("UNSUPPORTED_RECORD", lambda: self.extract(board + [row("PARTITION", {"fileUuid": "subboard"}, "flex-a")], fp))
        self.assert_code("UNSUPPORTED_PRIMITIVE_OVERRIDE", lambda: self.extract(board + [row("PROP", {"rotation": 90}, "component")], fp))

    def test_nonplated_pad_holes_retain_individual_provenance(self):
        board, fp = fixture()
        fp = self.replace(fp, "PAD", lambda b: b.update(layerId=12, hole={"holeType": "ROUND", "width": 5, "height": 5}, plated=False))
        ir = self.extract(board, fp)
        self.assertEqual(len(ir["nonplated_through_holes"]), 1)
        self.assertEqual(len(ir["holes"]), 2)
        self.assertEqual(ir["nonplated_through_holes"][0]["kind"], "nonplated_pad")
        self.assertEqual(ir["nonplated_through_holes"][0]["provenance"]["id"], "pad")

    def test_multi_circle_is_npth_not_copper_and_width_is_not_diameter(self):
        board, fp = fixture()
        fp += [row("FILL", {"layerId": 12, "fillStyle": "SOLID", "width": 7,
                           "path": [["CIRCLE", 20, 30, 10]]}, "mechanical")]
        ir = self.extract(board, fp)
        self.assertEqual(len(ir["nonplated_through_holes"]), 1)
        hole = ir["nonplated_through_holes"][0]
        self.assertAlmostEqual(hole["diameter_mm"], 20 * geometry.MIL)
        self.assertAlmostEqual(hole["center_mm"][0], 530 * geometry.MIL)
        self.assertAlmostEqual(hole["center_mm"][1], 420 * geometry.MIL)
        self.assertFalse(any(p["provenance"]["id"] == "mechanical" for p in ir["primitive_provenance"]))

    def test_exact_copper_interlayer_label_is_not_assumed_dielectric(self):
        board, fp = fixture()
        board = self.replace(board, "LAYER_PHYS", lambda b: b.update(material="COPPER") if b["thickness"] == 10 else None)
        ir = self.extract(board, fp)
        self.assertFalse(ir["coverage"]["stackup_complete"])
        self.assertTrue(any(d["code"] == "STACKUP_MATERIAL_CONTRADICTION" for d in ir["diagnostics"]))

    def test_copper_circle_fill_includes_stroke_width(self):
        g = geometry.primitive_shape("FILL", {"fillStyle": "SOLID", "width": 4, "path": [["CIRCLE", 0, 0, 10]]})
        self.assertAlmostEqual(g.bounds[2] - g.bounds[0], 24)

    def test_prohibit_regions_are_preserved_without_subtracting_final_copper(self):
        board, fp = fixture()
        before = self.extract(board, fp)
        region = {"layerId": 101, "regionType": "PROHIBIT", "prohibitType": ["COPPER"],
                  "path": [0, 0, "L", 1000, 0, 1000, 800, 0, 800]}
        after = self.extract(board + [row("REGION", region, "keepout")], fp)
        self.assertEqual(after["copper_statistics"], before["copper_statistics"])
        self.assertEqual(len(after["constraints"]), 1)
        self.assertFalse(after["constraints"][0]["applied_to_geometry"])


if __name__ == "__main__":
    unittest.main()
