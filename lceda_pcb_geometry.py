"""Geometry backend for the explicit observed-export-v1 PCB dialect.

All raw-format interpretation belongs here, never in downstream consumers.
Only candidate, cached copper is reconstructed. No fill regeneration, native
project loading, fabrication acceptance or thermal solver is provided.
"""
import collections
import math

import shapely
from shapely import affinity, make_valid
from shapely.geometry import GeometryCollection, LineString, Point, Polygon, box, mapping
from shapely.ops import unary_union

from lceda_pcb import (SCHEMA_VERSION, fail, finite, id_parts, meta, provenance,
                       record_id, records)

MIL = 0.0254
CACHE = 0.254
TOLERANCE_MM = 0.0002
PROFILE = "observed-export-v1"
COPPER_TYPES = {"TOP", "BOTTOM", "SIGNAL"}
GEOMETRIC = {"LINE", "ARC", "CARC", "FILL", "TEARDROP", "POLY"}
NON_GEOMETRIC = {"META", "CANVAS", "LAYER", "LAYER_PHYS", "ACTIVE_LAYER", "DELETE_DOC",
                 "ATTR", "PAD_NET", "NET", "PRIMITIVE", "PREFERENCE", "SILK_OPTS", "GROUP",
                 "RULE", "RULE_TEMPLATE", "RULE_SELECTOR", "PANELIZE", "ITEM_ORDER", "PROP",
                 "ELE_PLACEHOLDER", "STRING", "TEXT", "DIMENSION", "OBJ", "FONT", "FONTSTYLE"}


def _sagitta_angle(radius_mm, tolerance_mm=TOLERANCE_MM):
    # acos(1-t/r) loses all precision for large radii; the half-angle form
    # remains stable. Refuse excessive work before allocating coordinate lists.
    ratio = min(1.0, tolerance_mm / (2 * radius_mm))
    if ratio <= 0:
        fail("GEOMETRY_LIMIT", "Curve radius exceeds the supported numeric range")
    return 2 * math.asin(math.sqrt(ratio))


def number(body, field, default=None, **kwargs):
    return finite(body.get(field, default), field, **kwargs)


def _quad_segments(radius, scale=MIL, tolerance_mm=TOLERANCE_MM):
    radius_mm = radius * scale
    if radius_mm <= tolerance_mm:
        return 12
    count = max(12, math.ceil(math.pi / (4 * _sagitta_angle(radius_mm, tolerance_mm))))
    if count > 100_000:
        fail("GEOMETRY_LIMIT", "Circle requires too many subdivisions")
    return count


def circle(x, y, radius, scale=MIL, tolerance_mm=TOLERANCE_MM):
    finite(radius, "radius", positive=True)
    return Point(x, y).buffer(radius, quad_segs=_quad_segments(radius, scale, tolerance_mm))


def arc_points(start, end, angle, scale=MIL, tolerance_mm=TOLERANCE_MM):
    """Signed CCW sweep; sample with bounded chord sagitta in output millimetres."""
    for value in (*start, *end, angle):
        finite(value, "arc coordinate/angle")
    if abs(angle) >= 360:
        fail("UNSUPPORTED_ARC", "Endpoint arcs require an absolute sweep below 360 degrees")
    if abs(angle) < 1e-10:
        return [tuple(start), tuple(end)]
    dx, dy = end[0] - start[0], end[1] - start[1]
    if math.hypot(dx, dy) < 1e-10:
        fail("UNSUPPORTED_ARC", "Coincident endpoint arcs are ambiguous")
    theta = math.radians(angle)
    factor = 1 / (2 * math.tan(theta / 2))
    cx, cy = (start[0] + end[0]) / 2 - dy * factor, (start[1] + end[1]) / 2 + dx * factor
    radius = math.hypot(start[0] - cx, start[1] - cy)
    first = math.atan2(start[1] - cy, start[0] - cx)
    max_step = (2 * _sagitta_angle(radius * scale, tolerance_mm)
                if radius * scale > tolerance_mm else math.pi / 4)
    count = max(2, math.ceil(abs(theta) / min(max_step, math.pi / 12)))
    if count > 100_000:
        fail("GEOMETRY_LIMIT", "Arc requires too many subdivisions")
    points = [(cx + radius * math.cos(first + theta * i / count),
               cy + radius * math.sin(first + theta * i / count)) for i in range(count + 1)]
    points[0], points[-1] = tuple(start), tuple(end)
    return points


def ring(path, scale=MIL, tolerance_mm=TOLERANCE_MM):
    if not isinstance(path, list) or not path:
        fail("INVALID_PATH", "Polygon ring must be a nonempty list")
    if path[0] == "R":
        if len(path) != 7:
            fail("UNSUPPORTED_RECT_PATH", "Profile requires [R,x,y,width,height,angle,radius]")
        _, x, y, width, height, angle, radius = path
        for v in (x, y, angle):
            finite(v, "rectangle coordinate/angle")
        for v in (width, height):
            finite(v, "rectangle dimension", positive=True)
        finite(radius, "rectangle radius", nonnegative=True)
        if radius > min(width, height) / 2:
            fail("INVALID_RADIUS", "Rectangle path radius exceeds half the shorter side")
        geometry = box(x + radius, y - height + radius, x + width - radius, y - radius)
        if radius:
            geometry = geometry.buffer(radius, quad_segs=_quad_segments(radius, scale, tolerance_mm))
        return list(affinity.rotate(geometry, angle, origin=(x, y)).exterior.coords)
    if path[0] == "CIRCLE":
        if len(path) != 4:
            fail("INVALID_PATH", "CIRCLE requires a centre and radius")
        _, x, y, radius = path
        finite(x, "circle x"); finite(y, "circle y")
        return list(circle(x, y, radius, scale, tolerance_mm).exterior.coords)
    if len(path) < 6:
        fail("INVALID_PATH", "Polygon path has too few coordinates")
    for value in path[:2]:
        finite(value, "path start")
    points = [(path[0], path[1])]
    i, command = 2, "L"
    while i < len(path):
        if isinstance(path[i], str):
            command = path[i]
            if command not in ("L", "ARC", "CARC"):
                fail("UNSUPPORTED_PATH_TOKEN", "Unknown path token", token=command)
            i += 1
            if i == len(path):
                fail("INVALID_PATH", "Path ends with a command and no coordinates")
        count = 2 if command == "L" else 3
        values = path[i:i + count]
        if len(values) != count:
            fail("INVALID_PATH", "Incomplete path coordinates")
        for value in values:
            finite(value, "path coordinate")
        if command == "L":
            points.append(tuple(values))
        else:
            points.extend(arc_points(points[-1], values[1:], values[0], scale, tolerance_mm)[1:])
        i += count
    # These paths occur only in explicitly polygonal contexts. Copper POLY
    # objects (which may instead be open strokes) are rejected elsewhere.
    if math.dist(points[0], points[-1]) <= 1e-9:
        points[-1] = points[0]
    else:
        points.append(points[0])
    if len(set(points)) < 3:
        fail("INVALID_PATH", "Polygon needs three distinct vertices")
    return points


def polygon(path, scale=MIL, tolerance_mm=TOLERANCE_MM):
    if not isinstance(path, list) or not path:
        fail("INVALID_PATH", "Missing polygon path")
    paths = path if isinstance(path[0], list) else [path]
    return Polygon(ring(paths[0], scale, tolerance_mm), [ring(p, scale, tolerance_mm) for p in paths[1:]])


def _capsule(width, height):
    if width == height:
        return circle(0, 0, width / 2)
    if width > height:
        return LineString([(-(width - height) / 2, 0), ((width - height) / 2, 0)]).buffer(
            height / 2, quad_segs=_quad_segments(height / 2))
    return LineString([(0, -(height - width) / 2), (0, (height - width) / 2)]).buffer(
        width / 2, quad_segs=_quad_segments(width / 2))


def pad_shape(body):
    if body.get("specialPad"):
        fail("UNSUPPORTED_PAD", "Per-layer specialPad overrides are unsupported")
    pad = body.get("defaultPad")
    if not isinstance(pad, dict):
        fail("INVALID_PAD", "PAD requires defaultPad")
    kind = pad.get("padType")
    if kind == "POLYGON":
        # This observed encoder stores an already rotated/positioned local path.
        # The older POLY dialect has different offsets and is not accepted.
        return polygon(pad.get("path"))
    width, height = number(pad, "width", positive=True), number(pad, "height", positive=True)
    if kind == "RECT":
        percent = number(pad, "radius", 0, nonnegative=True)
        if percent > 100:
            fail("INVALID_RADIUS", "RECT pad roundness must be in 0..100 percent")
        radius = min(width, height) * percent / 200
        if radius == min(width, height) / 2:
            geometry = _capsule(width, height)
        else:
            geometry = box(-width / 2 + radius, -height / 2 + radius,
                           width / 2 - radius, height / 2 - radius)
            if radius:
                geometry = geometry.buffer(radius, quad_segs=_quad_segments(radius))
    elif kind == "ELLIPSE":
        if abs(width - height) > 1e-8:
            fail("UNSUPPORTED_PAD", "Noncircular ELLIPSE needs dialect-specific verification")
        geometry = circle(0, 0, width / 2)
    elif kind in ("OVAL", "ROUND"):
        geometry = _capsule(width, height)
    else:
        fail("UNSUPPORTED_PAD", "Unsupported pad shape in observed profile", pad_type=kind)
    geometry = affinity.rotate(geometry, number(body, "padAngle", 0), origin=(0, 0))
    return affinity.translate(geometry, number(body, "centerX"), number(body, "centerY"))


def hole_shape(body):
    hole = body.get("hole")
    if hole is None:
        return None
    if not isinstance(hole, dict):
        fail("INVALID_HOLE", "PAD hole must be an object or null")
    width, height = number(hole, "width", positive=True), number(hole, "height", positive=True)
    if hole.get("holeType") == "ROUND":
        # Observed encoder: height is diameter; width can retain a stale slot value.
        geometry = circle(0, 0, height / 2)
    elif hole.get("holeType") == "SLOT":
        geometry = _capsule(width, height)
    else:
        fail("UNSUPPORTED_HOLE", "Unsupported hole shape", hole_type=hole.get("holeType"))
    geometry = affinity.rotate(geometry, number(body, "relativeAngle", 0) if body.get("relativeAngle") is not None else 0, origin=(0, 0))
    geometry = affinity.translate(geometry, number(body, "padOffsetX", 0), number(body, "padOffsetY", 0))
    geometry = affinity.rotate(geometry, number(body, "padAngle", 0), origin=(0, 0))
    return affinity.translate(geometry, number(body, "centerX"), number(body, "centerY"))


def transform(geometry, component, bottom=False):
    if bottom:
        geometry = affinity.scale(geometry, 1, -1, origin=(0, 0))
    geometry = affinity.rotate(geometry, number(component, "angle", 0), origin=(0, 0))
    return affinity.translate(geometry, number(component, "x"), number(component, "y"))


def primitive_shape(kind, body):
    if kind in ("LINE", "ARC", "CARC"):
        start = number(body, "startX"), number(body, "startY")
        end = number(body, "endX"), number(body, "endY")
        width = number(body, "width", positive=True)
        budget = TOLERANCE_MM if kind == "LINE" else TOLERANCE_MM / 2
        points = [start, end] if kind == "LINE" else arc_points(start, end, number(body, "angle"), tolerance_mm=budget)
        return LineString(points).buffer(width / 2, quad_segs=_quad_segments(width / 2, tolerance_mm=budget))
    if kind == "FILL" and body.get("fillStyle") not in ("SOLID", 0):
        fail("UNSUPPORTED_FILL", "Only solid FILL is supported")
    if kind == "FILL":
        path = body.get("path")
        paths = path if isinstance(path, list) and path and isinstance(path[0], list) else [path]
        if paths and isinstance(paths[0], list) and paths[0] and paths[0][0] == "CIRCLE":
            if len(paths) != 1 or len(paths[0]) != 4:
                fail("UNSUPPORTED_CIRCLE_FILL", "Circular FILL requires one simple CIRCLE path")
            _, x, y, radius = paths[0]
            finite(x, "circle fill x"); finite(y, "circle fill y")
            finite(radius, "circle fill radius", positive=True)
            width = number(body, "width", nonnegative=True)
            # Verified modern manufacturing encoder flashes diameter 2r+width.
            # This differs from circular MULTI Slot Region/NPTH (diameter 2r).
            return circle(x, y, radius + width / 2)
    if kind in ("FILL", "TEARDROP"):
        return polygon(body.get("path"))
    fail("UNSUPPORTED_COPPER_GEOMETRY", "Copper POLY/open strokes are not reconstructed", kind=kind)


def layer_config(doc):
    layers = {}
    for record in records(doc, "LAYER"):
        ident = id_parts(record, "LAYER", {2})[1]
        if isinstance(ident, bool) or not isinstance(ident, int):
            fail("INVALID_LAYER", "Observed-profile layer IDs must be integers")
        if ident in layers:
            fail("DUPLICATE_LAYER", "Multiple LAYER records resolve to the same ID", layer=ident)
        body = record["data"]
        if "layerId" in body and body["layerId"] != ident:
            fail("INVALID_LAYER", "Layer payload and composite ID disagree", layer=ident)
        if not isinstance(body.get("use"), bool):
            fail("UNSUPPORTED_LAYER_DIALECT", "Observed-profile LAYER requires boolean use", layer=ident)
        layers[ident] = body
    if not layers:
        fail("MISSING_LAYERS", "No observed-profile layer configuration")
    return layers


def stackup(pcb, configs, diagnostics):
    copper = {ident for ident, body in configs.items() if body.get("use") and body.get("layerType") in COPPER_TYPES}
    active_planes = [ident for ident, body in configs.items() if body.get("use") and body.get("layerType") == "PLANE"]
    if active_planes:
        fail("UNSUPPORTED_PLANE_LAYER", "Negative plane-layer semantics require a separate profile", layers=active_planes)
    def only(kind):
        found = [ident for ident in copper if configs[ident].get("layerType") == kind]
        if len(found) != 1:
            fail("INVALID_COPPER_LAYERS", "Exactly one active top and bottom copper layer is required", kind=kind)
        return found[0]
    top, bottom = only("TOP"), only("BOTTOM")
    physical = []
    seen_ids, seen_z = set(), set()
    for record in records(pcb, "LAYER_PHYS"):
        ident = id_parts(record, "LAYER_PHYS", {2})[1]
        if isinstance(ident, bool) or not isinstance(ident, int) or ident in seen_ids:
            fail("INVALID_STACKUP", "Physical layer IDs must be unique integers")
        seen_ids.add(ident)
        body = record["data"]
        thickness = number(body, "thickness", nonnegative=True)
        if thickness == 0:
            continue
        order = number(body, "zIndex")
        if order in seen_z:
            fail("INVALID_STACKUP", "Positive-thickness physical layers share zIndex")
        seen_z.add(order)
        if ident in configs and configs[ident].get("layerType") in COPPER_TYPES and ident not in copper:
            fail("INVALID_STACKUP", "Inactive copper has positive declared thickness", layer=ident)
        physical.append((order, ident, body, record))
    physical.sort(key=lambda entry: entry[0])
    physical_copper = [ident for _, ident, _, _ in physical if ident in copper]
    complete = set(physical_copper) == copper
    if (top in physical_copper and physical_copper[0] != top
            or bottom in physical_copper and physical_copper[-1] != bottom):
        fail("INVALID_STACKUP", "Physical copper order must start at TOP and end at BOTTOM")
    if not complete:
        diagnostics.append({"code": "INCOMPLETE_STACKUP", "severity": "warning", "affects_completeness": True,
                            "message": "Copper thickness/order missing; no synthetic stackup was inserted"})
    if complete:
        # Every adjacent copper pair requires a positive non-copper separation.
        last_copper = None
        for index, (_, ident, _, _) in enumerate(physical):
            if ident in copper:
                if last_copper is not None and index == last_copper + 1:
                    complete = False
                last_copper = index
        if any(ident not in copper and str(body.get("material", "")).strip().upper() == "COPPER"
               for _, ident, body, _ in physical):
            complete = False
            diagnostics.append({"code": "STACKUP_MATERIAL_CONTRADICTION", "severity": "warning", "affects_completeness": True,
                                "message": "An unclassified interlayer is explicitly labelled COPPER; no dielectric role is assumed"})
        if not complete:
            diagnostics.append({"code": "MISSING_DIELECTRIC_STACKUP", "severity": "warning", "affects_completeness": True,
                                "message": "Adjacent copper layers lack a declared dielectric separation"})
    order = physical_copper if complete else None
    layers, z = [], 0
    for _, ident, body, record in physical:
        layer = {"id": ident, "name": configs.get(ident, {}).get("layerName"),
                 "kind": "copper" if ident in copper else "interlayer_or_coating",
                 "material_label": body.get("material"), "thickness_mm": body["thickness"] * MIL,
                 "z_depth_mm": z if complete else None, "declared_z_index": body["zIndex"],
                 "thermal_conductivity_W_mK": None,
                 "provenance": provenance(record)}
        z += layer["thickness_mm"]
        layers.append(layer)
    return {"layers": layers, "copper_order": order, "active_copper_layers": sorted(copper),
            "active_copper_layers_order": "numeric IDs only; not physical sequence",
            "total_thickness_mm": z if complete else None,
            "declared_not_measured": True}, complete, top, bottom


def extract(project, pcb, *, repair_invalid=False, include_primitives=False):
    diagnostics, cache_audit, primitives, constraints = [], [], [], []
    configs = layer_config(pcb)
    stack, stack_complete, top, bottom = stackup(pcb, configs, diagnostics)
    copper_order = stack["copper_order"] or stack["active_copper_layers"]
    copper = set(copper_order)
    geometry_by_layer = {layer: [] for layer in copper_order}
    repairs = []
    def clean(geometry, source):
        if not geometry.is_valid:
            if not repair_invalid:
                fail("INVALID_POLYGON", "Invalid polygon requires explicit --repair-invalid and independent review", source=source)
            before = geometry.area
            geometry = make_valid(geometry)
            repairs.append({"source": source, "code": "POLYGON_REPAIRED", "area_before_mm2": before,
                            "area_after_mm2": geometry.area, "area_delta_mm2": geometry.area - before})
        if geometry.geom_type == "GeometryCollection":
            nonpolygon = [g.geom_type for g in geometry.geoms if g.geom_type not in ("Polygon", "MultiPolygon")]
            if nonpolygon:
                if not repair_invalid:
                    fail("NONPOLYGON_GEOMETRY", "Unexpected non-polygon geometry", source=source)
                repairs.append({"source": source, "code": "NONPOLYGON_REMNANTS_EXCLUDED", "types": nonpolygon})
            geometry = unary_union([g for g in geometry.geoms if g.geom_type in ("Polygon", "MultiPolygon")])
        if not geometry.is_empty and geometry.geom_type not in ("Polygon", "MultiPolygon"):
            fail("NONPOLYGON_GEOMETRY", "Expected polygonal geometry", source=source)
        return geometry
    def mm(geometry, scale=MIL):
        return affinity.scale(geometry, scale, scale, origin=(0, 0))
    def add(layer, geometry, kind, record, net=None, component=None, scale=MIL):
        if layer not in copper:
            fail("INVALID_COPPER_LAYER", "Primitive maps to an inactive or non-copper layer", layer=layer)
        geometry = clean(mm(geometry, scale), record_id(record))
        if geometry.is_empty:
            fail("EMPTY_COPPER_PRIMITIVE", "Copper primitive is empty", record=record_id(record))
        geometry_by_layer[layer].append(geometry)
        item = {"kind": kind, "layer": layer, "net": net, "component_id": component,
                "area_before_union_mm2": geometry.area, "provenance": provenance(record)}
        if include_primitives:
            item["geometry"] = mapping(geometry)
        primitives.append(item)

    outline_layers = {i for i, b in configs.items() if b.get("use") and b.get("layerType") == "OUTLINE"}
    outline_records = [r for r in pcb["records"] if r["data"].get("layerId") in outline_layers
                       and r["header"]["type"] not in ("LAYER", "ACTIVE_LAYER")]
    if len(outline_records) != 1 or outline_records[0]["header"]["type"] != "POLY" or outline_records[0]["data"].get("polyType") != "BOARD_OUTLINE":
        fail("UNSUPPORTED_BOARD_OUTLINE", "Require one explicit BOARD_OUTLINE polygon; polygon holes are supported")
    outline = clean(mm(polygon(outline_records[0]["data"].get("path"))), record_id(outline_records[0]))
    if outline.is_empty or outline.area <= 0:
        fail("INVALID_BOARD_OUTLINE", "Board outline has no area")

    holes, hole_entities, vias, pads, components, plated_holes, nonplated_holes = [], [], [], [], [], [], []
    padnets, used_padnets = {}, set()
    for record in records(pcb, "PAD_NET"):
        parts = id_parts(record, "PAD_NET", {3, 4})
        key = tuple(parts[1:])
        if any(not isinstance(part, str) for part in key) or key in padnets:
            fail("INVALID_PAD_NET", "Pad-net identity must be unique text components")
        net = record["data"].get("padNet")
        if not isinstance(net, str):
            fail("INVALID_PAD_NET", "padNet must explicitly contain a string (empty means unassigned)")
        padnets[key] = (net, record)

    def net_of(body):
        net = body.get("netName")
        if net is not None and not isinstance(net, str):
            fail("INVALID_NET", "netName must be text or absent")
        return net
    def add_constraint(record, layer, component=None, component_id=None, is_bottom=False):
        body = record["data"]
        if body.get("regionType") != "PROHIBIT":
            fail("UNSUPPORTED_REGION", "Only verified PROHIBIT constraint regions are supported", record=record_id(record))
        flags = body.get("prohibitType")
        if not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags):
            fail("INVALID_REGION", "PROHIBIT region requires explicit prohibitType strings")
        geometry = polygon(body.get("path"))
        if component is not None:
            geometry = transform(geometry, component, is_bottom)
        constraints.append({"region_type": "PROHIBIT", "prohibit_types": flags,
                            "copper_layers": list(copper_order) if layer == "multi" else ([layer] if layer in copper else []),
                            "component_id": component_id, "geometry": mapping(clean(mm(geometry), record_id(record))),
                            "provenance": provenance(record), "applied_to_geometry": False,
                            "meaning": "constraint metadata; existing final copper cache already reflects its export state"})
    def add_circular_cutout(record, component=None, component_id=None, is_bottom=False):
        body = record["data"]
        path = body.get("path")
        if isinstance(path, list) and len(path) == 1 and isinstance(path[0], list):
            path = path[0]
        if (body.get("fillStyle") != "SOLID" or not isinstance(path, list)
                or len(path) != 4 or path[0] != "CIRCLE"):
            fail("UNSUPPORTED_MULTI_CUTOUT", "Only verified circular SOLID MULTI-layer FILL cutouts are supported",
                 record=record_id(record))
        geometry = polygon(path)
        if component is not None:
            geometry = transform(geometry, component, is_bottom)
        geometry = clean(mm(geometry), record_id(record))
        holes.append(geometry)
        item = {"id": f"{component_id}/{record_id(record)}" if component_id else record_id(record),
                "kind": "nonplated_fill", "component_id": component_id, "net": None, "plated": False,
                "start_layer": top, "end_layer": bottom, "geometry": mapping(geometry),
                "center_mm": [geometry.centroid.x, geometry.centroid.y], "diameter_mm": 2 * path[3] * MIL,
                "plating_thickness_mm": None, "provenance": provenance(record),
                "interpretation": "observed decoder maps solid MULTI FILL to material-removing Slot Region; circle diameter excludes display width"}
        nonplated_holes.append(item)
        hole_entities.append(item)
    def add_pad(record, layer, component=None, component_id=None, component_ref=None, is_bottom=False):
        body = record["data"]
        ident = record_id(record)
        num = body.get("num")
        if not isinstance(num, str):
            fail("INVALID_PAD", "Observed-profile pad number must be text", record=ident)
        net, net_source = net_of(body), None
        if component_id is not None:
            exact, fallback = (component_id, num, ident), (component_id, num)
            key = exact if exact in padnets else fallback
            if key in padnets:
                net, net_record = padnets[key]
                used_padnets.add(key)
                net_source = provenance(net_record)
            else:
                net = None
                diagnostics.append({"code": "MISSING_PAD_NET", "severity": "warning", "affects_completeness": True,
                                    "component": component_id, "pad": ident,
                                    "message": "No PAD_NET assignment; retained null rather than guessing a net"})
        geometry = pad_shape(body)
        hole = hole_shape(body)
        if component is not None:
            geometry = transform(geometry, component, is_bottom)
            if hole is not None:
                hole = transform(hole, component, is_bottom)
        layers = list(copper_order) if layer == "multi" else [layer]
        unused = body.get("unusedInnerLayers", [])
        if not isinstance(unused, list) or any(x not in copper - {top, bottom} for x in unused):
            fail("INVALID_UNUSED_LAYERS", "unusedInnerLayers must reference active inner copper")
        layers = [x for x in layers if x not in unused]
        plated = body.get("plated")
        if hole is not None:
            if layer != "multi" or not isinstance(plated, bool):
                fail("UNSUPPORTED_HOLE_SPAN", "Only explicit through-board pad holes with a boolean plated flag are supported")
            hole_mm = clean(mm(hole), ident)
            holes.append(hole_mm)
            item = {"id": f"{component_id}/{ident}" if component_id else ident,
                    "kind": "plated_pad" if plated else "nonplated_pad",
                    "component_id": component_id, "net": net, "plated": plated,
                    "start_layer": top, "end_layer": bottom,
                    "geometry": mapping(hole_mm), "plating_thickness_mm": None,
                    "provenance": provenance(record)}
            if plated:
                plated_holes.append(item)
            else:
                nonplated_holes.append(item)
            hole_entities.append(item)
        for target in layers:
            add(target, geometry, "PAD", record, net, component_id)
        center = Point(number(body, "centerX"), number(body, "centerY"))
        if component is not None:
            center = transform(center, component, is_bottom)
        pads.append({"id": ident, "component_id": component_id, "component_ref": component_ref,
                     "number": num, "net": net, "net_provenance": net_source,
                     "center_mm": [center.x * MIL, center.y * MIL], "layers": layers,
                     "plated": plated, "has_hole": hole is not None,
                     "geometry": mapping(clean(mm(geometry), ident)), "provenance": provenance(record)})

    multi_layers = {i for i, b in configs.items() if b.get("layerType") == "MULTI" and b.get("use")}
    def board_pad_layer(layer):
        if layer in multi_layers:
            return "multi"
        if layer in copper:
            return layer
        fail("UNSUPPORTED_PAD_LAYER", "PAD must be on copper or MULTI", layer=layer)
    for record in pcb["records"]:
        body, kind = record["data"], record["header"]["type"]
        layer = body.get("layerId")
        if body.get("partitionId") not in (None, ""):
            fail("UNSUPPORTED_PARTITION", "Partitioned geometry requires its own frame and stackup", record=record_id(record))
        if kind == "PRIMITIVE" and set(body) - {"display", "pick"}:
            fail("UNSUPPORTED_PRIMITIVE_OVERRIDE", "Unknown primitive overrides may affect geometry", record=record_id(record))
        if kind == "PROP" and set(body) - {"color"}:
            fail("UNSUPPORTED_PRIMITIVE_OVERRIDE", "Unknown PROP fields may affect geometry", record=record_id(record))
        if "layerId" in body and layer not in configs:
            fail("MISSING_PRIMITIVE_LAYER", "Layer-bearing record references an absent layer", kind=kind, record=record_id(record))
        if kind in GEOMETRIC | {"PAD", "POUR", "COMPONENT", "REGION"} and layer not in configs:
            fail("MISSING_PRIMITIVE_LAYER", "Geometric record references an absent layer", kind=kind, record=record_id(record))
        if kind == "PANELIZE" and body.get("on"):
            fail("UNSUPPORTED_PANELIZATION", "Active panelization requires a separate manufacturing-geometry backend")
        if kind not in NON_GEOMETRIC | GEOMETRIC | {"PAD", "VIA", "POUR", "POURED", "COMPONENT", "REGION"}:
            fail("UNSUPPORTED_RECORD", "Unclassified PCB record cannot be silently excluded", kind=kind, record=record_id(record))
        if kind == "REGION":
            add_constraint(record, "multi" if layer in multi_layers else layer)
            continue
        if layer in multi_layers and kind not in ("PAD", "FILL", "LAYER", "ACTIVE_LAYER"):
            fail("UNSUPPORTED_MULTI_GEOMETRY", "Unclassified board MULTI-layer geometry", kind=kind, record=record_id(record))
        if kind == "FILL" and layer in multi_layers:
            add_circular_cutout(record)
        elif kind == "PAD":
            add_pad(record, board_pad_layer(layer))
        elif kind == "VIA":
            if body.get("viaType") != "NORMAL" or body.get("ruleName") or any(k in body for k in ("startLayer", "endLayer", "startLayerId", "endLayerId")):
                fail("UNSUPPORTED_VIA_SPAN", "Only NORMAL full-span vias without rule-specific spans are supported", record=record_id(record))
            x, y = number(body, "centerX"), number(body, "centerY")
            drill, diameter = number(body, "holeDiameter", positive=True), number(body, "viaDiameter", positive=True)
            if diameter <= drill:
                fail("INVALID_VIA", "Via diameter must exceed its drill diameter")
            unused = body.get("unusedInnerLayers", [])
            if not isinstance(unused, list) or any(x not in copper - {top, bottom} for x in unused):
                fail("INVALID_UNUSED_LAYERS", "Via unused layers must be active inner copper")
            hole = mm(circle(x, y, drill / 2))
            holes.append(hole)
            hole_entities.append({"id": record_id(record), "kind": "via", "component_id": None,
                                  "net": net_of(body), "plated": True, "start_layer": top, "end_layer": bottom,
                                  "geometry": mapping(hole), "plating_thickness_mm": None,
                                  "provenance": provenance(record)})
            for target in copper_order:
                if target not in unused:
                    add(target, circle(x, y, diameter / 2), "VIA", record, net_of(body))
            vias.append({"id": record_id(record), "center_mm": [x * MIL, y * MIL],
                         "drill_mm": drill * MIL, "diameter_mm": diameter * MIL,
                         "start_layer": top, "end_layer": bottom,
                         "copper_layers": [l for l in copper_order if l not in unused],
                         "net": net_of(body), "plated": True, "plating_thickness_mm": None,
                         "hole_geometry": mapping(hole), "provenance": provenance(record)})
        elif kind in ("HOLE", "BOARD_CUTOUT"):
            fail("UNSUPPORTED_HOLE", "Standalone hole/cutout variant needs explicit support", kind=kind)
        elif kind in GEOMETRIC and layer in copper:
            add(layer, primitive_shape(kind, body), kind, record, net_of(body))
        elif layer in copper and kind not in ("POUR", "COMPONENT", "LAYER", "ACTIVE_LAYER"):
            fail("UNSUPPORTED_COPPER_GEOMETRY", "Unclassified copper-layer record", kind=kind, record=record_id(record))

    owners = {record_id(r): r for r in records(pcb, "POUR")}
    matched_owners = set()
    for record in records(pcb, "POURED"):
        owner_id = id_parts(record, "POURED", {2})[1]
        owner = owners.get(owner_id)
        audit = {"owner_id": owner_id, "owner_active": owner is not None, "provenance": provenance(record)}
        cache_audit.append(audit)
        if owner is None:
            diagnostics.append({"code": "ORPHAN_CACHE_IGNORED", "severity": "info", "affects_completeness": False,
                                "message": "POURED cache has no active POUR owner and is excluded", "cache_id": record_id(record)})
            continue
        if owner_id in matched_owners:
            fail("AMBIGUOUS_POUR_CACHE", "Multiple cache identities reference one POUR", owner=owner_id)
        matched_owners.add(owner_id)
        body, cached = owner["data"], record["data"]
        if body.get("layerId") not in copper:
            fail("INVALID_POUR_LAYER", "Active POUR owner is not on active copper", owner=owner_id)
        owner_rank = (owner["segment"], owner["header"]["ticket"])
        cache_rank = (record["segment"], record["header"]["ticket"])
        older = (record["header"]["ticket"] < owner["header"]["ticket"] if project["source"]["replay_policy"] == "ticket-client" else cache_rank < owner_rank)
        if older:
            fail("STALE_POUR_CACHE", "POURED cache predates its active owner; regenerate/export copper", owner=owner_id)
        pour_type = body.get("pourType")
        if not isinstance(pour_type, dict) or pour_type.get("pourType") != "SOLID":
            fail("UNSUPPORTED_POUR", "Only the observed solid POUR cache profile is supported")
        stroke = number(pour_type, "fineness", nonnegative=True) * MIL
        fills = cached.get("pourFill")
        if not isinstance(fills, list):
            fail("UNSUPPORTED_CACHE_DIALECT", "Observed profile requires POURED.pourFill array")
        audit.update({"owner_provenance": provenance(owner), "layer": body["layerId"],
                      "net": net_of(body), "fill_count": len(fills), "contour_stroke_mm": stroke,
                      "freshness": "not_proven_by_tickets"})
        for fill in fills:
            if not isinstance(fill, dict) or fill.get("fill") is not True or fill.get("strokeWidth", 0) != 0:
                fail("UNSUPPORTED_CACHE_FILL", "Only filled zero-stroke cache contours are supported")
            budget = TOLERANCE_MM / 2 if stroke else TOLERANCE_MM
            geometry = clean(mm(polygon(fill.get("path"), CACHE, budget), CACHE), record_id(record))
            if stroke:
                geometry = geometry.buffer(stroke / 2, quad_segs=_quad_segments(stroke / 2, 1, budget), join_style="round")
            add(body["layerId"], geometry, "POURED", record, net_of(body), scale=1)
    missing = set(owners) - matched_owners
    if missing:
        fail("MISSING_POUR_CACHE", "Active POUR boundaries are not final copper; export/regenerate missing POURED caches", owners=sorted(missing))

    attributes = collections.defaultdict(dict)
    for record in records(pcb, "ATTR"):
        body = record["data"]
        if isinstance(body.get("parentId"), str) and isinstance(body.get("key"), str):
            attributes[body["parentId"]][body["key"]] = body.get("value")
    for record in records(pcb, "COMPONENT"):
        body, cid = record["data"], record_id(record)
        if body.get("layerId") not in (top, bottom):
            fail("UNSUPPORTED_COMPONENT_LAYER", "Component must be on TOP or BOTTOM copper", component=cid)
        inline = body.get("attrs", {})
        if not isinstance(inline, dict):
            fail("INVALID_COMPONENT", "Component attrs must be an object")
        attrs = {**inline, **attributes[cid]}
        footprint_id = attrs.get("Footprint")
        footprint = project["documents"].get(("FOOTPRINT", footprint_id)) if isinstance(footprint_id, str) else None
        if footprint is None or footprint["deleted"]:
            fail("MISSING_FOOTPRINT", "Active component references an absent/deleted footprint", component=cid)
        for canvas in records(footprint, "CANVAS"):
            if number(canvas["data"], "originX", 0) != 0 or number(canvas["data"], "originY", 0) != 0:
                fail("UNSUPPORTED_FOOTPRINT_ORIGIN", "Nonzero footprint CANVAS origin needs independent convention verification", component=cid)
        fp_layers = layer_config(footprint)
        is_bottom = body["layerId"] == bottom
        def mapped_layer(ident):
            config = fp_layers.get(ident)
            if config is None:
                fail("MISSING_FOOTPRINT_LAYER", "Footprint primitive has no layer configuration", layer=ident)
            kind = config.get("layerType")
            if kind in COPPER_TYPES | {"MULTI", "PLANE"} and not config.get("use"):
                fail("INACTIVE_FOOTPRINT_LAYER", "Footprint geometry on an inactive copper/MULTI layer is ambiguous", layer=ident)
            if kind == "TOP":
                return bottom if is_bottom else top
            if kind == "BOTTOM":
                return top if is_bottom else bottom
            if kind == "MULTI":
                return "multi"
            if kind in ("SIGNAL", "PLANE"):
                fail("UNSUPPORTED_FOOTPRINT_INNER_LAYER", "Footprint inner-layer mapping is not assumed")
            return None
        bounds = []
        for fp_record in footprint["records"]:
            fb, kind = fp_record["data"], fp_record["header"]["type"]
            if fb.get("partitionId") not in (None, ""):
                fail("UNSUPPORTED_PARTITION", "Partitioned footprint geometry is unsupported", component=cid)
            if kind == "PRIMITIVE" and set(fb) - {"display", "pick"} or kind == "PROP" and set(fb) - {"color"}:
                fail("UNSUPPORTED_PRIMITIVE_OVERRIDE", "Unknown footprint overrides may affect geometry", component=cid)
            if kind not in NON_GEOMETRIC | GEOMETRIC | {"PAD", "VIA", "HOLE", "BOARD_CUTOUT", "REGION"}:
                fail("UNSUPPORTED_FOOTPRINT_RECORD", "Unclassified footprint record cannot be silently excluded", kind=kind, component=cid)
            if kind in ("VIA", "HOLE", "BOARD_CUTOUT"):
                fail("UNSUPPORTED_FOOTPRINT_HOLE", "Footprint via/standalone hole requires span-specific support", component=cid)
            if kind in GEOMETRIC | {"PAD", "REGION"} and "layerId" not in fb:
                fail("MISSING_PRIMITIVE_LAYER", "Footprint geometric record has no layer", kind=kind, component=cid)
            if kind in ("LAYER", "ACTIVE_LAYER") or "layerId" not in fb:
                continue
            target = mapped_layer(fb["layerId"])
            if kind == "REGION":
                add_constraint(fp_record, target, body, cid, is_bottom)
            elif kind == "FILL" and target == "multi":
                add_circular_cutout(fp_record, body, cid, is_bottom)
            elif kind == "PAD":
                if target is None:
                    fail("UNSUPPORTED_PAD_LAYER", "Footprint PAD is not on copper/MULTI")
                add_pad(fp_record, target, body, cid, attrs.get("Designator"), is_bottom)
                bounds.append(mm(transform(pad_shape(fb), body, is_bottom)))
            elif target is not None:
                if kind not in GEOMETRIC or target == "multi":
                    fail("UNSUPPORTED_FOOTPRINT_COPPER", "Unclassified footprint copper geometry", kind=kind, component=cid)
                add(target, transform(primitive_shape(kind, fb), body, is_bottom), "FOOTPRINT_" + kind,
                    fp_record, net_of(fb), cid)
        components.append({"id": cid, "reference": attrs.get("Designator"), "footprint_uuid": footprint_id,
                           "side": "bottom" if is_bottom else "top", "layer": body["layerId"],
                           "angle_deg": number(body, "angle", 0),
                           "center_mm": [number(body, "x") * MIL, number(body, "y") * MIL],
                           "pad_bounds_mm": list(unary_union(bounds).bounds) if bounds else None,
                           "bounds_kind": "copper pads, not package body", "provenance": provenance(record)})
    unused_padnets = set(padnets) - used_padnets
    if unused_padnets:
        diagnostics.append({"code": "UNUSED_PAD_NET_RECORDS", "severity": "warning", "affects_completeness": True,
                            "message": "PAD_NET records did not match an extracted pad (including superseded number-only mappings)",
                            "count": len(unused_padnets)})
    hole_union = unary_union(holes)
    features = [{"type": "Feature", "properties": {"kind": kind, "units": "mm"}, "geometry": mapping(geometry)}
                for kind, geometry in (("board", outline), ("substrate", outline.difference(hole_union)), ("drill_holes", hole_union))]
    statistics = []
    for layer in copper_order:
        geometry = unary_union(geometry_by_layer[layer]).intersection(outline).difference(hole_union)
        features.append({"type": "Feature", "properties": {"kind": "copper", "layer": layer, "units": "mm",
                                                              "status": "candidate_unverified"}, "geometry": mapping(geometry)})
        statistics.append({"layer": layer, "area_mm2": geometry.area, "board_fraction": geometry.area / outline.area,
                           "primitive_count": len(geometry_by_layer[layer])})
    if repairs:
        diagnostics.append({"code": "GEOMETRY_REPAIRS_APPLIED", "severity": "warning", "affects_completeness": True,
                            "message": "Topology repairs were explicitly allowed; review each repair and compare official exports",
                            "count": len(repairs)})
    complete = stack_complete and not any(d["affects_completeness"] for d in diagnostics)
    return {"schema_version": SCHEMA_VERSION, "status": "candidate", "units": "mm",
            "pcb": {"uuid": pcb["head"]["uuid"], "title": meta(pcb).get("title"), "board_uuid": meta(pcb).get("board")},
            "source": project["source"], "profile": PROFILE,
            "document_provenance": {"segments": pcb["segments"], "state_changes": pcb["state_provenance"]},
            "coordinate_frame": {"x": "right", "y": "up", "z": "depth into board", "origin": "exported PCB coordinates; CANVAS display origin is not applied"},
            "conventions": {"pcb_and_footprint_unit_mm": MIL, "poured_cache_unit_mm": CACHE,
                            "bottom_transform": "mirror local Y, then rotate CCW, then translate",
                            "round_hole_diameter_field": "height", "polygon_pad_path": "already positioned in footprint-local coordinates",
                            "solid_pour_envelope": "cache fill plus owner fineness/2 round boundary buffer",
                            "circular_multi_fill": "nonplated through-board material removal, not copper",
                            "circular_copper_fill": "filled circle diameter includes width: 2*radius + width",
                            "prohibit_regions": "constraints only; do not subtract their boundaries from final cached copper",
                            "maximum_curve_sagitta_mm": TOLERANCE_MM, "shapely_version": shapely.__version__},
            "coverage": {"complete": complete, "stackup_complete": stack_complete, "geometry_complete": not repairs,
                         "scope": "supported selected-PCB geometry and declared stackup only",
                         "manufacturing_verified": False, "net_connectivity_verified": False},
            "stackup": stack, "components": components, "pads": pads, "vias": vias,
            "plated_through_holes": plated_holes, "nonplated_through_holes": nonplated_holes,
            "holes": hole_entities, "primitive_provenance": primitives,
            "constraints": constraints,
            "geometry": {"type": "FeatureCollection", "features": features}, "copper_statistics": statistics,
            "poured_cache_audit": cache_audit, "geometry_repairs": repairs, "diagnostics": diagnostics,
            "validation": {"official_export_comparison": "not_run", "cache_freshness": "not_proven",
                           "required": ["compare same selected PCB and revision against official regenerated copper and drill exports",
                                        "bind comparison evidence to this IR and export digests"]},
            "unknowns": ["actual fabricated stackup and materials", "component power and package thermal interfaces",
                         "via/hole plating thickness", "airflow, enclosure, mounting and boundary conditions"]}
