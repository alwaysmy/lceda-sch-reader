#!/usr/bin/env python3
"""Optional, read-only comparison of PCB IR with explicitly supplied exports.

Install requirements-pcb-validation.txt separately. No core-reader imports or
implicit file discovery, origin fitting, clipping to the board, or IR promotion.
Copper comparison uses the IR's hole-subtracted copper and removes those SAME
IR holes from Gerber flashes. Drill geometry is then independently compared.

Supported drill roles describe COMPLETE sets: all-through, plated-through and
nonplated-through. all-through cannot be combined with either split role. Via
subsets, blind/buried drill spans and duplicate files are deliberately rejected.
Geometry comparison does not prove drill operation counts or plating material.

"complete" describes comparison coverage, not manufacturing verification.
Digests bind the exact supplied bytes and parameters; they cannot prove the
exports belong to the same real board/revision or were generated officially.
Invalid export topology fails by default. --repair-invalid explicitly permits
audited GEOS linework repairs; any applied repair forces partial status.
"""

import argparse
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import warnings


SCHEMA_VERSION = "lceda-pcb-export-comparison/1"
DRILL_ROLES = {"all-through", "plated-through", "nonplated-through"}
MAX_FILE_BYTES = 256 * 1024 * 1024


class ComparisonError(ValueError):
    """Fail closed on ambiguous, unsupported or empty input."""


def _dependencies():
    # Lazy imports keep --help and importing this optional script lightweight.
    if sys.version_info < (3, 12):
        raise ComparisonError("Manufacturing comparison requires Python >=3.12 (gerbonara 1.6.3); core geometry supports >=3.10")
    global shapely, gp, go, MM, GerberFile, ExcellonFile
    global Point, LineString, Polygon, GeometryCollection, box, shape, unary_union, affinity
    try:
        import shapely
        from shapely import affinity
        from shapely.geometry import Point, LineString, Polygon, GeometryCollection, box, shape
        from shapely.ops import unary_union
        from gerbonara import GerberFile, ExcellonFile
        from gerbonara import graphic_primitives as gp, graphic_objects as go
        from gerbonara.utils import MM
    except ImportError as exc:
        raise ComparisonError("Install optional requirements-pcb-validation.txt") from exc
    if int(shapely.__version__.split(".")[0]) < 2:
        raise ComparisonError("Shapely 2 is required")


def _number(value, name, *, positive=False, fraction=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ComparisonError(f"{name} must be finite")
    if positive and value <= 0:
        raise ComparisonError(f"{name} must be positive")
    if fraction and not 0 <= value <= 1:
        raise ComparisonError(f"{name} must be between 0 and 1")
    return value


def _polygonal(geometry, name, *, allow_empty=False):
    if geometry.is_empty:
        if allow_empty:
            return geometry
        raise ComparisonError(f"{name} is empty")
    if (geometry.geom_type not in ("Polygon", "MultiPolygon") or not geometry.is_valid
            or not all(math.isfinite(x) for x in geometry.bounds)
            or not math.isfinite(geometry.area) or geometry.area <= 0):
        raise ComparisonError(f"{name} is invalid or non-polygonal; no repair is applied")
    return geometry


def _steps(radius, tolerance, sweep=math.pi / 2):
    _number(radius, "curve radius", positive=True)
    step = min(math.pi / 12, 2 * math.acos(max(-1, min(1, 1 - tolerance / radius))))
    if step <= 0 or sweep / step > 200000:
        raise ComparisonError("Curve tolerance requires too many segments")
    return max(1, math.ceil(sweep / step))


def _export_polygonal(geometry, name, *, repair_invalid, repairs, source):
    """Explicit export-only repair, retaining the entire before/after audit."""
    if geometry.is_valid and geometry.geom_type in ("Polygon", "MultiPolygon"):
        return _polygonal(geometry, name)
    if not repair_invalid:
        return _polygonal(geometry, name)
    if repairs is None:
        raise ComparisonError("Explicit repair requires an audit destination")
    from shapely import make_valid, get_coordinates
    from shapely.geometry import mapping
    from shapely.validation import explain_validity
    if geometry.is_empty or any(not math.isfinite(float(v)) for point in get_coordinates(geometry) for v in point):
        raise ComparisonError("Empty/nonfinite export geometry cannot be repaired")
    repaired = make_valid(geometry, method="linework")
    polygons, discarded = [], []

    def split(value):
        if value.geom_type in ("Polygon", "MultiPolygon"):
            polygons.append(value)
        elif hasattr(value, "geoms"):
            for child in value.geoms:
                split(child)
        elif not value.is_empty:
            discarded.append(value)

    split(repaired)
    result = _polygonal(unary_union(polygons), f"Repaired {name}")
    remnants = GeometryCollection(discarded)
    repairs.append({"source": source, "method": "shapely.make_valid(method='linework'); polygonal union",
                    "reason": "invalid_topology" if not geometry.is_valid else "nonpolygonal_remnants",
                    "invalidity": explain_validity(geometry),
                    "area_before_mm2": geometry.area, "area_after_mm2": result.area,
                    "area_delta_mm2": result.area-geometry.area,
                    "type_before": geometry.geom_type, "type_after": result.geom_type,
                    "discarded_types": dict(Counter(g.geom_type for g in discarded)),
                    "before_wkb_sha256": hashlib.sha256(geometry.wkb).hexdigest(),
                    "after_wkb_sha256": hashlib.sha256(result.wkb).hexdigest(),
                    "geometry_before": mapping(geometry), "geometry_after": mapping(result),
                    "discarded_nonarea_geometry": mapping(remnants)})
    return result


def _linear_cutin_geometry(primitive):
    """Decode a narrow, exact Gerber cut-in contour, without topology repair.

    Ucamco 2026.05 section 4.10.3 permits reverse pairs of fully coincident
    horizontal OR vertical lines. All other boundaries must be simple,
    disjoint rings with consistent filled-side orientation. Only all-linear
    contours are handled here; arc-bearing invalid contours retain the
    existing explicit-repair boundary. No snapping or polygonization occurs.
    """
    segments = list(primitive.segments)
    if any(cw is not None or a == b for a, b, (cw, _) in segments):
        return None
    directed = Counter((tuple(a), tuple(b)) for a, b, _ in segments)
    if any(count != 1 for count in directed.values()):
        return None
    bridges = [(a, b) for a, b in directed if a < b and (b, a) in directed]
    if not bridges or len(bridges) > 10000:
        return None
    directions = {"horizontal" if a[1] == b[1] else "vertical" if a[0] == b[0] else "diagonal"
                  for a, b in bridges}
    if len(directions) != 1 or "diagonal" in directions:
        return None
    # Each cut-in end must attach to exactly one simple ring. A dangling
    # spike, a branching bridge or a shared boundary vertex is not decoded.
    endpoints = Counter(point for bridge in bridges for point in bridge)
    if any(count != 1 for count in endpoints.values()):
        return None
    remaining = [(a, b) for a, b in directed if (b, a) not in directed]
    outgoing, incoming = {}, set()
    for a, b in remaining:
        if a in outgoing or b in incoming:
            return None
        outgoing[a] = b
        incoming.add(b)
    if set(outgoing) != incoming:
        return None
    rings, membership = [], {}
    while outgoing:
        start = next(iter(outgoing))
        point, coordinates = start, [start]
        while True:
            if point not in outgoing:
                return None
            membership[point] = len(rings)
            point = outgoing.pop(point)
            coordinates.append(point)
            if point == start:
                break
        if len(coordinates) < 4:
            return None
        ring = Polygon(coordinates)
        if not ring.is_valid or ring.area <= 0:
            return None
        rings.append(ring)
    if len(bridges) != len(rings) - 1 or any(p not in membership for p in endpoints):
        return None
    from shapely.geometry import MultiPoint
    from shapely.strtree import STRtree
    boundaries = [ring.boundary for ring in rings]
    boundary_tree = STRtree(boundaries)
    for i, boundary in enumerate(boundaries):
        if any(int(j) != i for j in boundary_tree.query(boundary, predicate="intersects")):
            return None
    parent = list(range(len(rings)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in bridges:
        left, right = root(membership[a]), root(membership[b])
        if left == right:
            return None
        parent[left] = right
        bridge = LineString([a, b])
        touched = boundary_tree.query(bridge, predicate="intersects")
        intersection = bridge.intersection(unary_union([boundaries[int(i)] for i in touched]))
        if not intersection.equals(MultiPoint([a, b])):
            return None
    # Distinct axis-aligned cut-ins must not overlap or share a point.
    bridge_lines = [LineString([a, b]) for a, b in bridges]
    bridge_tree = STRtree(bridge_lines)
    if any(len(bridge_tree.query(line, predicate="intersects")) != 1 for line in bridge_lines):
        return None
    ring_tree = STRtree(rings)
    enclosing = [list(map(int, ring_tree.query(ring, predicate="within"))) for ring in rings]
    depths = [len(indices) - 1 for indices in enclosing]  # contains itself
    outer_signs = {ring.exterior.is_ccw for ring, depth in zip(rings, depths) if depth == 0}
    if len(outer_signs) != 1:
        return None
    outer_ccw = outer_signs.pop()
    if any(ring.exterior.is_ccw != (outer_ccw if depth % 2 == 0 else not outer_ccw)
           for ring, depth in zip(rings, depths)):
        return None
    areas = [Polygon(ring.exterior.coords,
                     [rings[j].exterior.coords for j in range(len(rings))
                      if depths[j] == depth + 1 and i in enclosing[j]])
             for i, (ring, depth) in enumerate(zip(rings, depths)) if depth % 2 == 0]
    result = unary_union(areas)
    if not result.is_valid or result.is_empty or result.geom_type not in ("Polygon", "MultiPolygon"):
        return None
    return result, {"method": "exact_linear_cutins", "specification": "Ucamco Gerber 2026.05 section 4.10.3",
                    "cutin_pairs": len(bridges), "simple_rings": len(rings),
                    "direction": next(iter(directions)), "snapping_applied": False,
                    "topology_repair_applied": False,
                    "decoded_wkb_sha256": hashlib.sha256(result.wkb).hexdigest()}


def primitive_geometry(primitive, tolerance_mm, *, repair_invalid=False, repairs=None, source=None,
                       contour_decodings=None):
    """Convert one gerbonara primitive; preserve its polarity at the caller."""
    _dependencies()
    _number(tolerance_mm, "curve tolerance", positive=True)
    p = primitive
    if isinstance(p, gp.Circle):
        result = Point(p.x, p.y).buffer(p.r, quad_segs=_steps(p.r, tolerance_mm))
    elif isinstance(p, gp.Line):
        _number(p.width, "line width", positive=True)
        result = LineString([(p.x1, p.y1), (p.x2, p.y2)]).buffer(
            p.width / 2, quad_segs=_steps(p.width / 2, tolerance_mm))
    elif isinstance(p, gp.Rectangle):
        _number(p.w, "rectangle width", positive=True)
        _number(p.h, "rectangle height", positive=True)
        # gerbonara 1.6.3 Rectangle.to_arc_poly has a rotated-vertex defect.
        result = affinity.rotate(box(p.x-p.w/2, p.y-p.h/2, p.x+p.w/2, p.y+p.h/2),
                                 -math.degrees(p.rotation), origin=(p.x, p.y))
    elif isinstance(p, gp.Arc):
        _number(p.width, "arc width", positive=True)
        radius = math.hypot(p.x1-p.cx, p.y1-p.cy)
        if radius == 0:
            result = Point(p.x1, p.y1).buffer(p.width/2, quad_segs=_steps(p.width/2, tolerance_mm))
        else:
            # 1.6.3 Arc.to_arc_poly reverses an endpoint cap. Sweep a sampled
            # centerline instead; split the error budget between line and caps.
            start = math.atan2(p.y1-p.cy, p.x1-p.cx)
            end = math.atan2(p.y2-p.cy, p.x2-p.cx)
            sweep = ((start-end) if p.clockwise else (end-start)) % (2*math.pi)
            if sweep == 0 and (p.x1, p.y1) == (p.x2, p.y2):
                sweep = 2*math.pi
            count = _steps(radius, tolerance_mm/2, sweep)
            points = [(p.x1, p.y1)]
            for i in range(1, count):
                angle = start + (-1 if p.clockwise else 1)*sweep*i/count
                points.append((p.cx+radius*math.cos(angle), p.cy+radius*math.sin(angle)))
            points.append((p.x2, p.y2))
            result = LineString(points).buffer(p.width/2, quad_segs=_steps(p.width/2, tolerance_mm/2))
    else:
        if not isinstance(p, gp.ArcPoly):
            raise ComparisonError(f"Unsupported Gerber primitive: {type(p).__name__}")
        points = []
        for (x1, y1), (x2, y2), (clockwise, (cx, cy)) in p.segments:
            if clockwise is None:
                points.extend([(x1, y1), (x2, y2)])
                continue
            radius = math.hypot(x1-cx, y1-cy)
            if radius == 0:
                points.extend([(x1, y1), (x2, y2)])
                continue
            start, end = math.atan2(y1-cy, x1-cx), math.atan2(y2-cy, x2-cx)
            sweep = ((start-end) if clockwise else (end-start)) % (2*math.pi)
            if sweep == 0 and (x1, y1) == (x2, y2):
                sweep = 2*math.pi
            steps = _steps(radius, tolerance_mm, sweep)
            points.append((x1, y1))
            for i in range(1, steps):
                angle = start + (-1 if clockwise else 1)*sweep*i/steps
                points.append((cx+radius*math.cos(angle), cy+radius*math.sin(angle)))
            points.append((x2, y2))
        if len(points) < 3:
            raise ComparisonError("Gerber region has fewer than three points")
        result = Polygon(points)
        if not result.is_valid and source and source.get("object_type") == "Region":
            decoded = _linear_cutin_geometry(p)
            if decoded is not None:
                result, audit = decoded
                if contour_decodings is not None:
                    contour_decodings.append({"source": source, **audit})
    return _export_polygonal(result, "Gerber primitive", repair_invalid=repair_invalid,
                             repairs=repairs, source=source or {"stage": "primitive"})


def _read(path):
    path = Path(path)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ComparisonError(f"Input exceeds {MAX_FILE_BYTES} bytes: {path.name}")
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raise ComparisonError(f"Input exceeds {MAX_FILE_BYTES} bytes: {path.name}")
    if not raw.strip():
        raise ComparisonError(f"Empty input: {path.name}")
    return raw, {"filename": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _parse_export(raw, filename, kind, expected_units):
    _dependencies()
    if expected_units not in ("mm", "inch"):
        raise ComparisonError(f"Explicit {kind} units must be mm or inch")
    text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    if kind == "gerber":
        units = re.findall(r"%MO(MM|IN)\*%", text)
        if not units or len(set(units)) != 1:
            raise ComparisonError("Gerber must declare one unambiguous MO unit")
        declared = {"MM": "mm", "IN": "inch"}[units[0]]
        if not re.search(r"%FS[LT][AI]X\d\dY\d\d\*%", text):
            raise ComparisonError("Gerber must declare an explicit FS coordinate format")
        if (not text.rstrip().endswith("M02*")
                or len(re.findall(r"(?:^|[\n*%])M02\*", text)) != 1):
            raise ComparisonError("Gerber must end with M02* (truncated/trailing data unsupported)")
        if re.search(r"%\s*(?:IPNEG|IF)", text):
            raise ComparisonError("Negative image polarity and included files are unsupported")
        # gerbonara 1.6.3 can replace an unfinished region at another G36,
        # or discard it at EOF. Check delimiters before information is lost.
        # G04 comments and parameter payloads are not bare G36/G37 commands.
        in_region = False
        for statement in text.split("*"):
            command = statement.strip().strip("%").strip()
            if command == "G36":
                if in_region:
                    raise ComparisonError("Nested Gerber region (G36 before G37)")
                in_region = True
            elif command == "G37":
                if not in_region:
                    raise ComparisonError("Gerber G37 outside a region")
                in_region = False
        if in_region:
            raise ComparisonError("Unterminated Gerber region (missing G37)")
        parser = GerberFile.from_string
    else:
        units = re.findall(r"^(METRIC|INCH)(?:,.*)?$", text, re.MULTILINE)
        if not units or len(set(units)) != 1:
            raise ComparisonError("Excellon must declare one unambiguous METRIC/INCH unit")
        declared = {"METRIC": "mm", "INCH": "inch"}[units[0]]
        if (text.rstrip().splitlines()[-1].strip() != "M30"
                or len(re.findall(r"^\s*M30\s*$", text, re.MULTILINE)) != 1):
            raise ComparisonError("Excellon must end with M30")
        parser = ExcellonFile.from_string
    if declared != expected_units:
        raise ComparisonError(f"{filename}: declared units {declared} differ from expected {expected_units}")
    # Gerbonara can otherwise ignore unrecognized statements. No adjacent tool
    # tables/includes are loaded: only these exact, digest-bound bytes are read.
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            parsed = parser(text, filename=filename)
    except (SyntaxError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ComparisonError(f"{filename}: unsupported or invalid export: {exc}") from exc
    recognized_warnings = []
    for warning in caught:
        message = str(warning.message)
        # The parser applies this explicit absolute-mode command correctly;
        # only its placement outside the header is deprecated. Retain the
        # warning as evidence instead of conflating it with ignored syntax.
        if (kind == "excellon" and warning.category is SyntaxWarning
                and re.search(r':\d+ "G90": G90 header statement found after end of header$', message)):
            recognized_warnings.append({"code": "EXCELLON_G90_AFTER_HEADER", "message": message,
                                        "handling": "Explicit absolute-coordinate mode applied by parser"})
        else:
            raise ComparisonError(f"{filename}: parser warning rejected: {message}")
    if not parsed.objects:
        raise ComparisonError(f"{filename}: export contains no objects")
    return parsed, declared, recognized_warnings


def gerber_geometry(raw, filename, *, expected_units, tolerance_mm, repair_invalid=False):
    """Compose aperture-local clear primitives, then apply object layer polarity."""
    parsed, units, parser_warnings = _parse_export(raw, filename, "gerber", expected_units)
    result, pending, counts, clear_count = GeometryCollection(), [], Counter(), 0
    repairs, contour_decodings = [], []
    for object_index, obj in enumerate(parsed.objects):
        # ArcPoly.segments silently adds a closing line. Region contours must
        # already close in the supplied file (Ucamco 4.10.1); never invent it.
        if isinstance(obj, go.Region) and (not obj.outline or obj.outline[0] != obj.outline[-1]):
            raise ComparisonError(f"{filename}: region contour is not explicitly closed")
        local = GeometryCollection()
        dark_object = copy.copy(obj)
        dark_object.polarity_dark = True
        primitives = list(dark_object.to_primitives(unit=MM))
        if not primitives:
            raise ComparisonError(f"{filename}: object has no supported primitives")
        for primitive_index, primitive in enumerate(primitives):
            counts[type(primitive).__name__] += 1
            source = {"filename": filename, "stage": "primitive", "object_index": object_index,
                      "primitive_index": primitive_index, "object_type": type(obj).__name__,
                      "primitive_type": type(primitive).__name__, "object_polarity_dark": obj.polarity_dark,
                      "primitive_polarity_dark": primitive.polarity_dark}
            geometry = primitive_geometry(primitive, tolerance_mm, repair_invalid=repair_invalid,
                                          repairs=repairs, source=source, contour_decodings=contour_decodings)
            # A macro's clear primitives affect only the current aperture.
            if primitive.polarity_dark:
                # Empty-union is an identity; avoiding it also avoids GEOS
                # generating a sub-ulp line remnant for near-touching rings.
                local = geometry if local.is_empty else local.union(geometry)
            else:
                local = local.difference(geometry)
        local = _export_polygonal(local, "Gerber object", repair_invalid=repair_invalid, repairs=repairs,
                                  source={"filename": filename, "stage": "aperture_composition", "object_index": object_index})
        if obj.polarity_dark:
            pending.append(local)
        else:
            result = unary_union([result, *pending]).difference(local)
            pending = []
            clear_count += 1
    result = _export_polygonal(unary_union([result, *pending]), "Gerber export", repair_invalid=repair_invalid,
                              repairs=repairs, source={"filename": filename, "stage": "layer_composition"})
    return result, {"objects": len(parsed.objects), "primitive_counts": dict(counts),
                    "clear_objects": clear_count, "declared_units": units,
                    "bounds_mm_before_translation": list(result.bounds), "geometry_repairs": repairs,
                    "contour_decodings": contour_decodings,
                    "parser_warnings": parser_warnings}


def drill_geometry(raw, filename, *, role, expected_units, tolerance_mm):
    parsed, units, parser_warnings = _parse_export(raw, filename, "excellon", expected_units)
    geometries, counts = [], Counter()
    for obj in parsed.objects:
        if not isinstance(obj, (go.Flash, go.Line, go.Arc)):
            raise ComparisonError(f"Unsupported Excellon object: {type(obj).__name__}")
        plated = getattr(obj.tool, "plated", None)
        if (role == "plated-through" and plated is False
                or role == "nonplated-through" and plated is True):
            raise ComparisonError(f"{filename}: tool plating contradicts explicit role {role}")
        counts[type(obj).__name__] += 1
        primitives = list(obj.to_primitives(unit=MM))
        if not primitives:
            raise ComparisonError("Excellon object has no supported primitives")
        for primitive in primitives:
            if not primitive.polarity_dark:
                raise ComparisonError("Clear Excellon primitives are unsupported")
            geometries.append(primitive_geometry(primitive, tolerance_mm))
    result = _polygonal(unary_union(geometries), "Excellon export")
    return result, {"objects": len(parsed.objects), "object_types": dict(counts),
                    "declared_units": units, "bounds_mm_before_translation": list(result.bounds),
                    "parser_warnings": parser_warnings}


def compare_geometry(expected, exported, *, max_xor_area_mm2, max_xor_fraction, min_overlap_fraction):
    """Full geometry XOR; no bounding-box, visual, or best-fit substitution."""
    _polygonal(expected, "Expected comparison geometry")
    _polygonal(exported, "Export comparison geometry")
    overlap = expected.intersection(exported).area
    union = expected.union(exported).area
    xor = expected.symmetric_difference(exported).area
    overlap_fraction = overlap / min(expected.area, exported.area)
    checks = {"positive_overlap": overlap > 0,
              "xor_area_within_threshold": xor <= max_xor_area_mm2,
              "xor_fraction_within_threshold": xor / union <= max_xor_fraction,
              "overlap_within_threshold": overlap_fraction >= min_overlap_fraction}
    return {"expected_area_mm2": expected.area, "export_area_mm2": exported.area,
            "intersection_area_mm2": overlap, "union_area_mm2": union,
            "xor_area_mm2": xor, "xor_over_union": xor / union,
            "overlap_over_smaller_area": overlap_fraction,
            "expected_only_mm2": expected.difference(exported).area,
            "export_only_mm2": exported.difference(expected).area,
            "checks": checks, "passed": all(checks.values())}


def _load_ir(raw):
    def invalid(value):
        raise ComparisonError(f"IR contains invalid JSON number: {value}")
    ir = json.loads(raw, parse_constant=invalid)
    if not isinstance(ir, dict) or ir.get("schema_version") != "lceda-pcb-ir/1":
        raise ComparisonError("Expected lceda-pcb-ir/1")
    if ir.get("units") != "mm":
        raise ComparisonError("IR units must explicitly be mm")
    source_hash = ir.get("source", {}).get("sha256")
    if not isinstance(source_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", source_hash):
        raise ComparisonError("IR must contain source.sha256")
    if not isinstance(ir.get("pcb", {}).get("uuid"), str) or not ir["pcb"]["uuid"]:
        raise ComparisonError("IR must identify the selected pcb.uuid")
    fc = ir.get("geometry", {})
    if fc.get("type") != "FeatureCollection" or not isinstance(fc.get("features"), list):
        raise ComparisonError("IR requires geometry FeatureCollection")
    shapes, copper = {}, {}
    for feature in fc["features"]:
        props = feature.get("properties", {})
        kind = props.get("kind")
        if kind not in ("board", "substrate", "drill_holes", "copper"):
            raise ComparisonError(f"Unknown IR geometry kind: {kind}")
        if props.get("units") != "mm":
            raise ComparisonError("Every IR feature must explicitly declare mm")
        geometry = _polygonal(shape(feature["geometry"]), f"IR {kind}", allow_empty=kind != "board")
        if kind == "copper":
            layer = props.get("layer")
            if isinstance(layer, bool) or not isinstance(layer, int) or layer in copper:
                raise ComparisonError("IR copper layers must be unique integer IDs")
            copper[layer] = geometry
        else:
            if kind in shapes:
                raise ComparisonError(f"Duplicate IR feature: {kind}")
            shapes[kind] = geometry
    if set(shapes) != {"board", "substrate", "drill_holes"} or not copper:
        raise ComparisonError("IR requires board, substrate, drill_holes and copper")
    # XY coverage uses the feature set. Physical copper order may be unknown;
    # that remains an IR completeness blocker rather than blocking comparison.
    stack = ir.get("stackup", {})
    for field in ("copper_order", "active_copper_layers"):
        declared = stack.get(field)
        if declared is not None and (not isinstance(declared, list)
                or any(isinstance(x, bool) or not isinstance(x, int) for x in declared)
                or len(declared) != len(copper) or set(declared) != set(copper)):
            raise ComparisonError(f"IR copper geometry disagrees with stackup.{field}")
    return ir, shapes, copper


def _drill_expectations(ir, all_holes):
    plated = []
    if "holes" in ir:
        geometries = []
        if not isinstance(ir["holes"], list):
            raise ComparisonError("IR holes must be a list")
        for hole in ir["holes"]:
            if not isinstance(hole.get("plated"), bool):
                raise ComparisonError("IR holes require explicit plated booleans for role comparison")
            geometry = _polygonal(shape(hole["geometry"]), "IR hole")
            geometries.append(geometry)
            if hole["plated"]:
                plated.append(geometry)
        if unary_union(geometries).symmetric_difference(all_holes).area > 0:
            raise ComparisonError("IR hole entities disagree with drill_holes geometry")
    else:
        if not isinstance(ir.get("vias"), list) or not isinstance(ir.get("plated_through_holes"), list):
            raise ComparisonError("Split drill roles require explicit hole entities")
        for via in ir["vias"]:
            plated.append(_polygonal(shape(via["hole_geometry"]), "IR via hole"))
        for hole in ir["plated_through_holes"]:
            plated.append(_polygonal(shape(hole["geometry"]), "IR plated hole"))
    plated = unary_union(plated)
    if plated.difference(all_holes).area > 0:
        raise ComparisonError("IR plated hole entities disagree with drill_holes geometry")
    return {"all-through": all_holes, "plated-through": plated,
            "nonplated-through": all_holes.difference(plated)}


def compare_exports(ir_path, copper_exports, *, drill_exports=None, gerber_units,
                    drill_units=None, offset_x_mm, offset_y_mm, tolerance_mm,
                    max_xor_area_mm2, max_xor_fraction, min_overlap_fraction, repair_invalid=False):
    """Compare exact files and return evidence without mutating the IR or inputs.

    copper_exports maps integer IR layer IDs to paths; drill_exports maps the
    complete-set roles documented above to paths. Missing layers/drill roles or
    incomplete IR coverage make the report partial even when supplied files pass.
    All numeric thresholds and the explicit export-to-IR translation are inputs.
    """
    _dependencies()
    if not isinstance(repair_invalid, bool):
        raise ComparisonError("repair_invalid must be a boolean")
    _number(offset_x_mm, "offset_x_mm")
    _number(offset_y_mm, "offset_y_mm")
    _number(tolerance_mm, "tolerance_mm", positive=True)
    _number(max_xor_area_mm2, "max_xor_area_mm2")
    if max_xor_area_mm2 < 0:
        raise ComparisonError("max_xor_area_mm2 must be nonnegative")
    _number(max_xor_fraction, "max_xor_fraction", fraction=True)
    _number(min_overlap_fraction, "min_overlap_fraction", positive=True, fraction=True)
    thresholds = {"max_xor_area_mm2": max_xor_area_mm2, "max_xor_fraction": max_xor_fraction,
                  "min_overlap_fraction": min_overlap_fraction}
    raw, ir_file = _read(ir_path)
    ir, shapes, copper = _load_ir(raw)
    if not copper_exports:
        raise ComparisonError("At least one explicit copper layer mapping is required")
    if any(isinstance(layer, bool) or not isinstance(layer, int) or layer not in copper for layer in copper_exports):
        raise ComparisonError("Unknown mapped copper layer; use exact IR integer layer IDs")
    drill_exports = drill_exports or {}
    roles = set(drill_exports)
    if not roles <= DRILL_ROLES or "all-through" in roles and len(roles) != 1:
        raise ComparisonError("Unsupported drill pairing; use all-through alone or disjoint plated/nonplated sets")
    if drill_exports and drill_units not in ("mm", "inch"):
        raise ComparisonError("Drill mappings require explicit drill_units")
    identities = set()
    exports, layer_results, drill_results, drill_shapes = [], [], [], []

    def file_input(path, kind, key):
        data, metadata = _read(path)
        identity = (kind, metadata["sha256"])
        # Identical copper content may legitimately appear on different layers.
        if kind == "excellon" and identity in identities:
            raise ComparisonError("Duplicate drill file content cannot be counted twice")
        identities.add(identity)
        metadata.update({"kind": kind, "layer" if kind == "gerber" else "role": key})
        exports.append(metadata)
        return data, metadata

    for layer, path in sorted(copper_exports.items()):
        data, metadata = file_input(path, "gerber", layer)
        exported, parser = gerber_geometry(data, metadata["filename"], expected_units=gerber_units,
                                           tolerance_mm=tolerance_mm, repair_invalid=repair_invalid)
        exported = affinity.translate(exported, offset_x_mm, offset_y_mm)
        exported = _export_polygonal(exported, "Translated Gerber export", repair_invalid=repair_invalid,
                                     repairs=parser["geometry_repairs"],
                                     source={"filename": metadata["filename"], "stage": "translation_to_ir_frame", "layer": layer})
        # Never clip to the board: off-board artwork is retained as discrepancy.
        exported = exported.difference(shapes["drill_holes"])
        exported = _export_polygonal(exported, "Hole-subtracted Gerber export", repair_invalid=repair_invalid,
                                     repairs=parser["geometry_repairs"],
                                     source={"filename": metadata["filename"], "stage": "drill_subtraction_in_ir_frame", "layer": layer})
        # The IR contract already subtracts holes from copper. Repeating that
        # operation can manufacture lower-dimensional floating-point remnants.
        expected = copper[layer]
        result = compare_geometry(expected, exported, **thresholds)
        result.update({"layer": layer, "parser": parser,
                       "export_outside_board_mm2": exported.difference(shapes["board"]).area})
        layer_results.append(result)
    expectations = ({"all-through": shapes["drill_holes"]} if roles == {"all-through"}
                    else _drill_expectations(ir, shapes["drill_holes"]) if roles else {})
    for role, path in sorted(drill_exports.items()):
        data, metadata = file_input(path, "excellon", role)
        exported, parser = drill_geometry(data, metadata["filename"], role=role,
                                          expected_units=drill_units, tolerance_mm=tolerance_mm)
        exported = affinity.translate(exported, offset_x_mm, offset_y_mm)
        if any(exported.intersection(other).area > 0 for other in drill_shapes):
            raise ComparisonError("Drill role files overlap; subset/duplicate pairing is unsupported")
        drill_shapes.append(exported)
        result = compare_geometry(expectations[role], exported, **thresholds)
        result.update({"role": role, "parser": parser})
        drill_results.append(result)
    missing_layers = sorted(set(copper) - set(copper_exports))
    missing_roles = []
    if not roles:
        missing_roles = ["all-through"]
    elif "all-through" not in roles:
        missing_roles = sorted(role for role in ("plated-through", "nonplated-through")
                               if role not in roles and not expectations[role].is_empty)
    blockers = []
    if missing_layers:
        blockers.append("uncompared_copper_layers")
    if missing_roles:
        blockers.append("uncompared_drill_roles")
    if ir.get("coverage", {}).get("complete") is not True:
        blockers.append("ir_coverage_incomplete")
    repair_count = sum(len(result["parser"]["geometry_repairs"]) for result in layer_results)
    if repair_count:
        blockers.append("export_geometry_repairs_applied")
    import gerbonara
    binding = {"ir": ir_file, "source_sha256_recorded_in_ir": ir["source"]["sha256"],
               "pcb_uuid": ir["pcb"]["uuid"], "exports": exports,
               "parameters": {"gerber_units": gerber_units, "drill_units": drill_units,
                              "export_to_ir_translation_mm": [offset_x_mm, offset_y_mm],
                              "maximum_curve_sagitta_mm": tolerance_mm, "thresholds": thresholds,
                              "repair_invalid": repair_invalid},
               "implementation": {"schema_version": SCHEMA_VERSION,
                                  "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                  "gerbonara": gerbonara.__version__, "shapely": shapely.__version__}}
    digest = hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return {"schema_version": SCHEMA_VERSION, "status": "partial" if blockers else "complete",
            "scope": "all declared copper geometry and through-hole geometry only; no outline, mask, plating or stackup verification",
            "comparison_passed": all(r["passed"] for r in layer_results + drill_results),
            "coverage": {"complete": not blockers, "missing_copper_layers": missing_layers,
                         "missing_drill_roles": missing_roles, "blockers": blockers},
            "manufacturing_verified": False, "ir_status_unchanged": ir.get("status"),
            "export_geometry_repair_count": repair_count,
            "evidence_sha256": digest, "binding": binding, "copper": layer_results, "drills": drill_results,
            "limitations": ["Digests bind supplied bytes, not real-board identity, revision correspondence or official export provenance.",
                            "No automatic alignment, clipping to board, implicit topology repair, cache freshness claim or IR promotion.",
                            "Explicit export topology repairs are audited under each copper parser and force partial status.",
                            "Copper uses the same IR drill subtraction on both sides; drill geometry must be checked independently.",
                            "Drill geometry comparison does not verify operation multiplicity, plating material or blind/buried spans.",
                            "Empty exports are rejected; absence of a drill file does not verify absence of holes."]}


def _mapping(values, *, integer_keys):
    result = {}
    for item in values:
        if "=" not in item:
            raise ComparisonError("Mappings must have KEY=FILE form")
        key, path = item.split("=", 1)
        if integer_keys:
            try:
                key = int(key)
            except ValueError as exc:
                raise ComparisonError("Copper mapping keys must be integer layer IDs") from exc
        if key in result or not path:
            raise ComparisonError("Duplicate mapping keys or empty paths are unsupported")
        result[key] = Path(path)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ir", required=True, type=Path)
    parser.add_argument("--copper", action="append", required=True, metavar="LAYER=GERBER")
    parser.add_argument("--drill", action="append", default=[], metavar="ROLE=EXCELLON")
    parser.add_argument("--gerber-units", required=True, choices=("mm", "inch"))
    parser.add_argument("--drill-units", choices=("mm", "inch"))
    parser.add_argument("--offset-x-mm", required=True, type=float)
    parser.add_argument("--offset-y-mm", required=True, type=float)
    parser.add_argument("--tolerance-mm", required=True, type=float)
    parser.add_argument("--max-xor-area-mm2", required=True, type=float)
    parser.add_argument("--max-xor-fraction", required=True, type=float)
    parser.add_argument("--min-overlap-fraction", required=True, type=float)
    parser.add_argument("--repair-invalid", action="store_true", help="Explicit audited export-only topology repair; applied repairs force partial status")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        copper = _mapping(args.copper, integer_keys=True)
        drills = _mapping(args.drill, integer_keys=False)
        inputs = [args.ir, *copper.values(), *drills.values()]
        if args.out and (args.out.resolve() in {p.resolve() for p in inputs}
                         or args.out.exists() and any(p.exists() and args.out.samefile(p) for p in inputs)):
            raise ComparisonError("Output must not overwrite an input file")
        result = compare_exports(args.ir, copper, drill_exports=drills, gerber_units=args.gerber_units,
                                 drill_units=args.drill_units, offset_x_mm=args.offset_x_mm, offset_y_mm=args.offset_y_mm,
                                 tolerance_mm=args.tolerance_mm, max_xor_area_mm2=args.max_xor_area_mm2,
                                 max_xor_fraction=args.max_xor_fraction, min_overlap_fraction=args.min_overlap_fraction,
                                 repair_invalid=args.repair_invalid)
        output = json.dumps(result, indent=2, allow_nan=False) + "\n"
        if args.out:
            args.out.write_text(output, encoding="utf-8")
        print(output, end="")
        return 0 if result["comparison_passed"] and result["coverage"]["complete"] else 1
    except (ComparisonError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(json.dumps({"schema_version": SCHEMA_VERSION, "status": "error", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
