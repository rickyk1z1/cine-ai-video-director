"""Read-only, dependency-free checks of declared files, IDs and time ranges.

Does not start Blender, decode media, inspect prompts for artistic quality, or
prove upload status. See references/offline-handoff-check.md for the contract.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path, PureWindowsPath


class Audit:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.errors = []
        self.warnings = []

    def error(self, code, **evidence):
        self.errors.append({"code": code, **evidence})

    def warn(self, code, **evidence):
        self.warnings.append({"code": code, **evidence})

    def object(self, value, where):
        if not isinstance(value, dict):
            self.error("EXPECTED_OBJECT", where=where)
            return {}
        return value

    def array(self, value, where):
        if not isinstance(value, list):
            self.error("EXPECTED_ARRAY", where=where)
            return []
        return value

    def index(self, values, where, key="id"):
        indexed = {}
        for item in self.array(values, where):
            item = self.object(item, where)
            identifier = item.get(key)
            if not isinstance(identifier, str) or not identifier.strip():
                self.error("INVALID_ID", where=where, key=key)
            elif identifier in indexed:
                self.error("DUPLICATE_ID", where=where, id=identifier)
            else:
                indexed[identifier] = item
        return indexed

    def path(self, value, where, available=True):
        if not isinstance(value, str) or not value.strip():
            (self.error if available else self.warn)("MISSING_PATH", where=where)
            return None
        # Detect drive, UNC and rooted Windows paths even when run on Unix.
        portable = value.replace("\\", "/")
        if PureWindowsPath(value).drive or portable.startswith("/") or ":" in portable:
            self.error("NONPORTABLE_PATH", where=where, path=value)
            return None
        try:
            target = (self.root / portable).resolve()
        except (OSError, ValueError) as exc:
            self.error("INVALID_PATH", where=where, detail=str(exc))
            return None
        if not target.is_relative_to(self.root):
            self.error("PATH_OUTSIDE_PROJECT", where=where, path=value)
            return None
        if not target.is_file():
            (self.error if available else self.warn)("FILE_MISSING", where=where, path=value)
            return None
        if available and target.stat().st_size == 0:
            self.error("EMPTY_FILE", where=where, path=value)
        return target

    def read(self, path, where):
        target = self.path(path, where)
        if target is None:
            return {}
        try:
            return self.object(json.loads(target.read_text(encoding="utf-8-sig")), where)
        except (OSError, ValueError) as exc:
            self.error("INVALID_JSON", where=where, detail=str(exc))
            return {}

    def interval(self, value, where, integer=False):
        if (not isinstance(value, list) or len(value) != 2
                or not all(number(x, integer=integer) for x in value)
                or value[1] < value[0] or (not integer and value[1] == value[0])):
            self.error("INVALID_RANGE", where=where, value=value)
            return None
        return value

    def result(self):
        return {
            "status": "error" if self.errors else "needs_review" if self.warnings else "declared_checks_passed",
            "errors": self.errors, "warnings": self.warnings,
            "unverified": ["full_json_schema", "Blender_objects_and_animation", "media_decoding_and_metadata",
                           "actual_upload_bindings", "prompt_semantics_and_visual_quality", "nonlinear_time_mapping"],
        }


def number(value, integer=False):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and (not integer or isinstance(value, int)))


def reference(audit, value, known, where):
    if not isinstance(value, str) or value not in known:
        audit.error("UNKNOWN_REFERENCE", where=where, reference=value)


def check_scene(a, data, hardware=None):
    d = a.object(data, "scene-spec")
    scene = a.object(d.get("scene"), "scene")
    bounds = a.interval([scene.get("frame_start"), scene.get("frame_end")], "scene.frames", integer=True)
    if not number(scene.get("fps")) or scene["fps"] <= 0:
        a.error("INVALID_FPS", where="scene")
    assets = a.index(d.get("assets"), "assets")
    shots = a.index(d.get("shots"), "shots")
    events = a.index(d.get("events"), "events")
    ranges = {}
    cameras = {identifier for identifier, item in assets.items() if item.get("role") == "camera"}
    shot_cameras = {}
    for identifier, shot in shots.items():
        span = a.interval(shot.get("frame_range"), identifier, integer=True)
        if span:
            ranges[identifier] = span
            if bounds and not bounds[0] <= span[0] <= span[1] <= bounds[1]:
                a.error("SHOT_OUT_OF_RANGE", shot=identifier)
        camera = a.object(shot.get("camera"), identifier + ".camera")
        camera_id = camera.get("id")
        if isinstance(camera_id, str) and camera_id:
            cameras.add(camera_id)
            shot_cameras[identifier] = camera_id
        for link in a.array(shot.get("continuity_links", []), identifier + ".continuity_links"):
            reference(a, link, shots, identifier)
    ordered = sorted(ranges.items(), key=lambda item: item[1][0])
    for (left_id, left), (right_id, right) in zip(ordered, ordered[1:]):
        if left[1] >= right[0]:
            a.error("SHOT_OVERLAP", shots=[left_id, right_id])
        elif left[1] + 1 != right[0]:
            a.warn("SHOT_GAP", shots=[left_id, right_id])
    if not shots:
        a.error("NO_SHOTS")
    if bounds and ordered and (ordered[0][1][0] != bounds[0] or ordered[-1][1][1] != bounds[1]):
        a.warn("UNCOVERED_SCENE_BOUNDARY")
    sequence = a.object(d.get("sequence"), "sequence")
    if sequence.get("timeline_fps") != scene.get("fps"):
        a.warn("TIMELINE_FPS_MAPPING_UNVERIFIED")
    cuts = a.array(sequence.get("camera_cuts"), "camera_cuts")
    bound_shots = set()
    last_frame = None
    for cut in cuts:
        cut = a.object(cut, "camera_cut")
        identifier = cut.get("shot_id")
        reference(a, identifier, shots, "camera_cut.shot_id")
        reference(a, cut.get("camera_id"), cameras, "camera_cut.camera_id")
        frame, source = cut.get("edit_frame"), cut.get("source_frame")
        if not number(frame, integer=True) or not number(source, integer=True):
            a.error("INVALID_CUT_FRAME")
            continue
        if last_frame is not None and frame <= last_frame:
            a.error("UNORDERED_CUTS", frame=frame)
        last_frame = frame
        if bounds and not bounds[0] <= frame <= bounds[1]:
            a.error("CUT_OUT_OF_RANGE", frame=frame)
        if isinstance(identifier, str) and identifier in shots:
            bound_shots.add(identifier)
            if identifier in ranges and frame != ranges[identifier][0]:
                a.error("CUT_SHOT_START_MISMATCH", shot=identifier)
            if identifier in shot_cameras and cut.get("camera_id") != shot_cameras[identifier]:
                a.error("CUT_CAMERA_MISMATCH", shot=identifier)
        if source != frame:
            a.warn("SOURCE_EDIT_MAPPING_UNVERIFIED", frame=frame, source_frame=source)
    for identifier in shots.keys() - bound_shots:
        a.error("MISSING_SHOT_CAMERA_BINDING", shot=identifier)
    for identifier, event in events.items():
        reference(a, event.get("target"), assets, identifier + ".target")
        frame = event.get("frame")
        if not number(frame, integer=True) or (bounds and not bounds[0] <= frame <= bounds[1]):
            a.error("EVENT_OUT_OF_RANGE", event=identifier, frame=frame)
    continuity = a.object(d.get("continuity"), "continuity")
    for link in a.array(continuity.get("links"), "continuity.links"):
        link = a.object(link, "continuity.link")
        for direction in ("from", "to"):
            identifier = link.get(direction + "_shot")
            reference(a, identifier, shots, "continuity." + direction)
            frame = link.get(direction + "_frame")
            span = ranges.get(identifier) if isinstance(identifier, str) else None
            if not number(frame, integer=True) or (span and not span[0] <= frame <= span[1]):
                a.error("CONTINUITY_FRAME_OUT_OF_RANGE", direction=direction, frame=frame)
    if d.get("schema_version") == "1.1":
        budgets = a.object(d.get("budgets"), "budgets")
        perf = a.object(d.get("performance"), "performance")
        for old, new in (("visible_triangles", "expanded_visible_triangles"), ("objects", "base_objects")):
            if not number(budgets.get(old), integer=True) or budgets.get(old) != budgets.get(new):
                a.error("BUDGET_ALIAS_MISMATCH", fields=[old, new])
        profile_id = budgets.get("hardware_profile_id")
        if not isinstance(profile_id, str) or not profile_id or profile_id != perf.get("hardware_profile_id"):
            a.error("HARDWARE_PROFILE_MISMATCH")
        if hardware is not None and profile_id != hardware.get("profile_id"):
            a.error("HARDWARE_FILE_PROFILE_MISMATCH")
    # Check only explicit file fields, not symbolic asset library refs or Curve paths.
    file_keys = {"manifest_ref", "source_ref", "scene_spec_ref", "hardware_profile_ref", "image_path"}
    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in file_keys and isinstance(value, str) and value:
                    a.path(value, key)
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(d)


def check_package(a, data):
    d = a.object(data, "package")
    refs = a.index(d.get("references"), "references")
    units = a.index(d.get("generation_units"), "generation_units", key="unit_id")
    labels = {}
    ready_characters = set()
    for identifier, item in refs.items():
        available = item.get("available")
        if not isinstance(available, bool):
            a.error("INVALID_AVAILABILITY", reference=identifier)
            available = False
        if not available:
            a.warn("REFERENCE_PENDING", reference=identifier)
        target = a.path(item.get("path"), identifier, available=available)
        if item.get("kind") not in {"video", "image", "audio"}:
            a.error("INVALID_REFERENCE_KIND", reference=identifier)
        placeholder = False
        if target and item.get("kind") == "image":
            with target.open("rb") as stream:
                placeholder = b"BlenderAIPrevisPlaceholder\x00true" in stream.read(65536)
            if available and placeholder:
                a.error("PLACEHOLDER_AS_ASSET", reference=identifier)
        if item.get("binding_status") != "bound":
            a.warn("BINDING_PENDING", reference=identifier)
        else:
            label = item.get("label")
            if not isinstance(label, str) or not label.strip():
                a.error("MISSING_BOUND_LABEL", reference=identifier)
            elif label in labels:
                a.error("DUPLICATE_BOUND_LABEL", references=[labels[label], identifier])
            else:
                labels[label] = identifier
        duration = item.get("duration_seconds")
        if duration is not None and (not number(duration) or duration <= 0):
            a.error("INVALID_REFERENCE_DURATION", reference=identifier)
        if item.get("role") == "character_appearance":
            asset_ids = a.array(item.get("asset_ids", []), identifier + ".asset_ids")
            if available and target and target.stat().st_size and not placeholder and item.get("kind") == "image":
                ready_characters.update(x for x in asset_ids if isinstance(x, str))
    if not units:
        a.error("NO_GENERATION_UNITS")
    for identifier, unit in units.items():
        duration = unit.get("duration_seconds")
        if not number(duration) or duration <= 0:
            a.error("INVALID_UNIT_DURATION", unit=identifier)
        if unit.get("time_basis") != "local":
            a.warn("TIME_BASIS_UNVERIFIED", unit=identifier)
        if not isinstance(unit.get("prompt"), str) or not unit["prompt"].strip():
            a.error("MISSING_PROMPT", unit=identifier)
        unit_refs = a.array(unit.get("reference_ids"), identifier + ".reference_ids")
        for ref_id in unit_refs:
            reference(a, ref_id, refs, identifier)
        source_id = unit.get("source_reference_id")
        if source_id is not None or "source_range_seconds" in unit:
            reference(a, source_id, refs, identifier + ".source_reference_id")
            if source_id not in unit_refs:
                a.error("SOURCE_NOT_IN_UNIT_REFERENCES", unit=identifier)
            span = a.interval(unit.get("source_range_seconds"), identifier + ".source_range_seconds")
            source = refs.get(source_id, {}) if isinstance(source_id, str) else {}
            if source and source.get("kind") != "video":
                a.error("SOURCE_REFERENCE_NOT_VIDEO", unit=identifier)
            source_duration = source.get("duration_seconds")
            if span:
                if span[0] < 0 or (number(source_duration) and span[1] > source_duration + 1e-6):
                    a.error("SOURCE_RANGE_OUT_OF_BOUNDS", unit=identifier)
                if source_duration is None:
                    a.warn("SOURCE_DURATION_UNKNOWN", unit=identifier)
                mapping = unit.get("time_mapping", "one_to_one")
                if mapping != "one_to_one":
                    a.warn("TIME_MAPPING_UNVERIFIED", unit=identifier, mapping=mapping)
                elif number(duration) and not math.isclose(span[1] - span[0], duration, abs_tol=1e-6):
                    a.error("UNIT_SOURCE_DURATION_MISMATCH", unit=identifier)
    for character_id in a.array(d.get("required_character_ids", []), "required_character_ids"):
        if not isinstance(character_id, str) or character_id not in ready_characters:
            a.warn("CHARACTER_IMAGE_PENDING", character_id=character_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--scene-spec", help="Path relative to project root")
    parser.add_argument("--package", help="JSON package relative to project root")
    parser.add_argument("--hardware-profile", help="Optional hardware JSON relative to project root")
    args = parser.parse_args()
    if not args.scene_spec and not args.package:
        parser.error("provide --scene-spec and/or --package")
    if args.hardware_profile and not args.scene_spec:
        parser.error("--hardware-profile requires --scene-spec")
    a = Audit(args.project_root)
    try:
        if args.scene_spec:
            hardware = a.read(args.hardware_profile, "hardware-profile") if args.hardware_profile else None
            check_scene(a, a.read(args.scene_spec, "scene-spec"), hardware)
        if args.package:
            check_package(a, a.read(args.package, "package"))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        a.error("CHECK_INCOMPLETE", exception=type(exc).__name__, detail=str(exc))
    result = a.result()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["errors"] or result["warnings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
