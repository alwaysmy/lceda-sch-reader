#!/usr/bin/env python3
"""Opt-in, read-only PCB export reader. Existing SCH APIs are not modified.

The archive/replay layer uses only the standard library. Geometry is loaded
only by ``extract`` and requires Shapely 2. This is an exported EPRO2/EPRU
reader, not a native EPRJ3 reader or a copper pour/thermal simulation engine.
"""

import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import zipfile

SCHEMA_VERSION = "lceda-pcb-ir/1"
INVENTORY_SCHEMA_VERSION = "lceda-pcb-inventory/1"
ERROR_SCHEMA_VERSION = "lceda-pcb-error/1"
REPLAY_POLICIES = ("auto", "segment-ticket", "ticket-client")
MAX_INPUT_BYTES = 256 * 1024 * 1024


class PCBError(ValueError):
    """A bounded format/geometry failure suitable for a machine-readable CLI."""

    def __init__(self, code, message, **context):
        super().__init__(message)
        self.code = code
        self.context = context

    def as_dict(self):
        return {"code": self.code, "severity": "error", "message": str(self),
                "context": self.context, "affects_completeness": True}


def fail(code, message, **context):
    raise PCBError(code, message, **context)


def finite(value, field, *, positive=False, nonnegative=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value)):
        fail("INVALID_NUMBER", f"{field} must be a finite number", field=field)
    if positive and value <= 0 or nonnegative and value < 0:
        fail("INVALID_NUMBER", f"{field} has an invalid sign", field=field)
    return value


def _json(text, context):
    def parse_float(value):
        result = float(value)
        if not math.isfinite(result):
            fail("NONFINITE_JSON", "JSON numeric overflow is not supported", **context)
        return result
    try:
        return json.loads(text, parse_float=parse_float, parse_constant=lambda x: fail(
            "NONFINITE_JSON", "JSON contains a nonfinite number", **context))
    except (json.JSONDecodeError, UnicodeError) as exc:
        fail("INVALID_JSON", str(exc), **context)


def records(doc, kind):
    return [r for r in doc["records"] if r["header"]["type"] == kind]


def meta(doc):
    rows = records(doc, "META")
    if len(rows) > 1:
        fail("AMBIGUOUS_META", "Document has multiple META identities",
             document=doc["head"]["uuid"])
    result = rows[0]["data"] if rows else {}
    for field in ("title", "board"):
        if result.get(field) is not None and not isinstance(result[field], str):
            fail("INVALID_META", "Document title/board identity must be text or null", field=field)
    return result


def record_id(record):
    return record["header"].get("id", record["header"]["type"])


def id_parts(record, kind, lengths):
    ident = record_id(record)
    parts = _json(ident, {"record": ident}) if isinstance(ident, str) else ident
    if not isinstance(parts, list) or len(parts) not in lengths or parts[0] != kind:
        fail("INVALID_COMPOSITE_ID", f"Invalid {kind} composite id", record=ident)
    return parts


def provenance(record):
    return {"id": record_id(record), "type": record["header"]["type"],
            "line": record["line"], "segment": record["segment"],
            "ticket": record["header"].get("ticket", 0),
            "client": record["client"]}


def _choose(rows, policy):
    if policy == "segment-ticket":
        return max(rows, key=lambda r: (r["segment"], r["header"]["ticket"], r["line"]))
    ticket = max(r["header"]["ticket"] for r in rows)
    rows = [r for r in rows if r["header"]["ticket"] == ticket]
    client = min(r["client"] for r in rows)
    return max((r for r in rows if r["client"] == client), key=lambda r: r["line"])


def load_project(path, replay_policy="auto", max_input_bytes=MAX_INPUT_BYTES):
    """Replay exported records without extracting any archive member to disk.

    ``auto`` accepts only final states on which the legacy segment/ticket and
    exported ticket/client policies agree. It never infers a dialect from the
    extension or CANVAS display units. Conflicting equal logical ranks fail.
    """
    if replay_policy not in REPLAY_POLICIES:
        fail("INVALID_REPLAY_POLICY", "Unknown replay policy", policy=replay_policy)
    path = Path(path)
    if path.stat().st_size > max_input_bytes:
        fail("INPUT_TOO_LARGE", "Input exceeds the configured byte limit")
    raw = path.read_bytes()
    member = None
    source_format = "epru-export"
    if zipfile.is_zipfile(io.BytesIO(raw)):
        source_format = "epro2-export"
        # Decode precisely the byte snapshot whose digest is recorded, even if
        # an external process replaces the source path during this query.
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = [i for i in archive.infolist() if i.filename.lower().endswith(".epru")]
            if len(members) != 1:
                fail("AMBIGUOUS_ARCHIVE", "Expected exactly one exported EPRU member",
                     epru_members=len(members))
            info = members[0]
            if info.file_size > max_input_bytes:
                fail("INPUT_TOO_LARGE", "Uncompressed EPRU exceeds the configured byte limit")
            if info.flag_bits & 1:
                fail("ENCRYPTED_ARCHIVE", "Encrypted ZIP members are not supported")
            member = info.filename
            payload = archive.read(info)
    else:
        payload = raw
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeError:
        fail("UNSUPPORTED_FORMAT", "Expected an exported EPRO2 ZIP or UTF-8 EPRU log")
    decoder = json.JSONDecoder()
    documents = {}
    current = None
    line_count = 0
    for line_no, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        line_count += 1
        line = line.lstrip()
        try:
            head, end = decoder.raw_decode(line)
        except ValueError:
            fail("UNSUPPORTED_FORMAT", "Expected EPRU header||payload records; native EPRJ3 is unsupported",
                 line=line_no)
        if not isinstance(head, dict) or not isinstance(head.get("type"), str):
            fail("INVALID_HEADER", "EPRU record header must contain a type", line=line_no)
        if line[end:end + 2] != "||":
            fail("INVALID_SEPARATOR", "EPRU record is missing ||", line=line_no)
        ticket = head.get("ticket", 0)
        if isinstance(ticket, bool) or not isinstance(ticket, int) or ticket < 0:
            fail("INVALID_TICKET", "ticket must be a nonnegative integer", line=line_no)
        head = _json(line[:end], {"line": line_no})
        head = dict(head, ticket=ticket)
        body_text = line[end + 2:]
        if body_text.endswith("|"):
            body_text = body_text[:-1]
        body = _json(body_text, {"line": line_no}) if body_text.strip() else None
        if body == "":
            body = None
        if body is not None and not isinstance(body, dict):
            fail("INVALID_BODY", "EPRU payload must be an object or tombstone", line=line_no)
        if head["type"] == "DOCHEAD":
            if not body or not isinstance(body.get("uuid"), str) or not isinstance(body.get("docType"), str):
                fail("INVALID_DOCHEAD", "DOCHEAD requires uuid and docType", line=line_no)
            key = body["docType"], body["uuid"]
            current = documents.setdefault(key, {"head": body, "segments": [], "history": {}})
            client = body.get("client", "")
            if not isinstance(client, str):
                fail("INVALID_CLIENT", "DOCHEAD client must be text", line=line_no)
            current["segments"].append({"line": line_no, "client": client,
                                        "version": body.get("version"),
                                        "edit_version": body.get("editVersion"),
                                        "update_time": body.get("updateTime")})
            continue
        if current is None:
            fail("MISSING_DOCHEAD", "Record appears before a DOCHEAD", line=line_no)
        ident = head.get("id", head["type"])
        if not isinstance(ident, str):
            fail("INVALID_RECORD_ID", "EPRU record id must be text", line=line_no)
        row = {"header": head, "data": body, "line": line_no,
               "segment": len(current["segments"]) - 1,
               "client": current["segments"][-1]["client"]}
        current["history"].setdefault((head["type"], ident), []).append(row)
    if not documents:
        fail("NO_DOCUMENTS", "No exported documents found")
    conflicts = 0
    disagreements = []
    for key, doc in documents.items():
        winners = []
        state_provenance = []
        tombstones = 0
        for identity, history in doc.pop("history").items():
            conflicts += len(history) - 1
            a, b = _choose(history, "segment-ticket"), _choose(history, "ticket-client")
            winner = b if replay_policy == "ticket-client" else a
            if a["data"] != b["data"]:
                disagreements.append({"document": key[1], "type": identity[0], "id": identity[1],
                                      "segment_ticket": provenance(a), "ticket_client": provenance(b)})
            # Same logical rank with different bodies is irreducibly ambiguous.
            policies = ("segment-ticket", "ticket-client") if replay_policy == "auto" else (replay_policy,)
            for policy in policies:
                selected = a if policy == "segment-ticket" else b
                rank_peers = [r for r in history if r["header"]["ticket"] == selected["header"]["ticket"]
                              and (r["segment"] == selected["segment"] if policy == "segment-ticket"
                                   else r["client"] == selected["client"])]
                if any(r["data"] != selected["data"] for r in rank_peers):
                    fail("CONFLICTING_EQUAL_RANK", "Different record bodies have the same logical rank",
                         document=key[1], record=identity[1], policy=policy)
            if winner["data"] is None:
                tombstones += 1
                state_provenance.append({**provenance(winner), "state": "tombstone"})
            else:
                winners.append(winner)
                if identity[0] == "DELETE_DOC":
                    state_provenance.append({**provenance(winner), "state": "document_delete",
                                             "is_delete": winner["data"].get("isDelete")})
        doc["records"] = sorted(winners, key=lambda r: r["line"])
        doc["tombstones"] = tombstones
        doc["state_provenance"] = state_provenance
        deletion = records(doc, "DELETE_DOC")
        if len(deletion) > 1:
            fail("AMBIGUOUS_DELETE_STATE", "Multiple document deletion identities", document=key[1])
        if deletion and not isinstance(deletion[0]["data"].get("isDelete"), bool):
            fail("INVALID_DELETE_STATE", "DELETE_DOC isDelete must be boolean", document=key[1])
        doc["deleted"] = bool(deletion and deletion[0]["data"]["isDelete"])
    if replay_policy == "auto" and disagreements:
        fail("AMBIGUOUS_REPLAY_POLICY", "Replay policies disagree; choose an explicit policy after verifying the export dialect",
             conflict_count=len(disagreements), examples=disagreements[:10])
    return {"documents": documents, "source": {
        "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
        "format": source_format, "archive_member": member,
        "line_count": line_count, "superseded_records": conflicts,
        "replay_policy": replay_policy,
        "replay_policy_agreement": not disagreements,
        "replay_disagreements": disagreements,
        "native_eprj3_supported": False}}


def list_pcbs(project):
    from collections import Counter
    return [{"uuid": uuid, "title": meta(doc).get("title"),
             "board_uuid": meta(doc).get("board"),
             "records": dict(Counter(r["header"]["type"] for r in doc["records"])),
             "segments": len(doc["segments"]), "tombstones": doc["tombstones"]}
            for (kind, uuid), doc in project["documents"].items()
            if kind == "PCB" and not doc["deleted"]]


def select_pcb(project, selector=None):
    candidates = list_pcbs(project)
    if selector is not None:
        exact = [p for p in candidates if p["uuid"] == selector]
        candidates = exact or [p for p in candidates if p["title"] == selector]
    if len(candidates) != 1:
        fail("PCB_SELECTION_REQUIRED", "Select exactly one active PCB by UUID (titles must be unique)",
             selector=selector, candidates=[p["uuid"] for p in candidates])
    return project["documents"]["PCB", candidates[0]["uuid"]]


def extract_pcb(project, selector=None, *, profile, repair_invalid=False, include_primitives=False):
    """Return the standalone PCB IR; importing this function needs no geometry package."""
    if profile != "observed-export-v1":
        fail("UNSUPPORTED_GEOMETRY_PROFILE", "Choose an explicitly supported export dialect")
    try:
        from lceda_pcb_geometry import extract
    except ImportError as exc:
        fail("OPTIONAL_DEPENDENCY_MISSING", "PCB geometry requires Shapely 2; install requirements-pcb.txt",
             dependency=str(exc))
    try:
        return extract(project, select_pcb(project, selector),
                       repair_invalid=repair_invalid, include_primitives=include_primitives)
    except PCBError:
        raise
    except (KeyError, TypeError, IndexError) as exc:
        fail("MALFORMED_GEOMETRY_RECORD", "Geometry record does not match the selected export profile",
             detail=str(exc))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Exported .epro2 ZIP or plain .epru")
    parser.add_argument("--replay-policy", choices=REPLAY_POLICIES, default="auto")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List active PCBs without geometry dependencies")
    extract = sub.add_parser("extract", help="Extract candidate copper geometry and declared stackup")
    extract.add_argument("--profile", required=True, choices=("observed-export-v1",),
                         help="Explicitly select the observed modern export dialect; not generic V3")
    extract.add_argument("--pcb", help="PCB UUID, or an unambiguous title")
    extract.add_argument("--repair-invalid", action="store_true", help="Allow audited polygon repair; result remains incomplete")
    extract.add_argument("--include-primitives", action="store_true", help="Include per-primitive copper polygons for provenance")
    extract.add_argument("--require-stackup", action="store_true")
    extract.add_argument("--strict", action="store_true", help="Exit 3 if geometry or declared stackup is incomplete; not manufacturing acceptance")
    extract.add_argument("-o", "--output", help="Write one IR JSON file; existing files are not overwritten")
    args = parser.parse_args(argv)
    try:
        if args.command == "extract" and args.output and Path(args.output).exists():
            fail("OUTPUT_EXISTS", "Choose a new output path; existing files are not overwritten")
        project = load_project(args.input, args.replay_policy)
        if args.command == "list":
            result = {"schema_version": INVENTORY_SCHEMA_VERSION, "source": project["source"], "pcbs": list_pcbs(project)}
        else:
            result = extract_pcb(project, args.pcb, profile=args.profile, repair_invalid=args.repair_invalid,
                                 include_primitives=args.include_primitives)
            if args.require_stackup and not result["coverage"]["stackup_complete"]:
                fail("STACKUP_REQUIRED", "A complete declared stackup is required")
            if args.output:
                with Path(args.output).open("x", encoding="utf-8") as handle:
                    json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
                    handle.write("\n")
                print(json.dumps({"output": str(Path(args.output)), "schema_version": SCHEMA_VERSION,
                                  "pcb_uuid": result["pcb"]["uuid"], "coverage": result["coverage"],
                                  "diagnostics": result["diagnostics"]}, ensure_ascii=False))
                return 3 if args.strict and not result["coverage"]["complete"] else 0
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 3 if args.command == "extract" and args.strict and not result["coverage"]["complete"] else 0
    except PCBError as exc:
        print(json.dumps({"schema_version": ERROR_SCHEMA_VERSION, "status": "failed", "data": None,
                          "diagnostics": [exc.as_dict()]}, ensure_ascii=False))
        return 2
    except (OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({"schema_version": ERROR_SCHEMA_VERSION, "status": "failed", "data": None,
                          "diagnostics": [PCBError("INPUT_OUTPUT_ERROR", str(exc)).as_dict()]}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
