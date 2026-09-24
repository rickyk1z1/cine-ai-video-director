"""Lightweight regression tests; no Blender, network or user project writes."""
import ast
import copy
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace as NS
import unittest

HERE = Path(__file__).resolve().parent


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


handoff = load_script("validate_handoff")


def fast_functions():
    path = HERE / "validate_previs_fast.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    # Load actual production functions, excluding bpy imports and result=_validate().
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 or (isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) and t.id.isupper() for t in node.targets))]
    scope = {"math": math, "json": json, "time": time}
    exec(compile(tree, str(path), "exec"), scope)
    return scope


def curve(path="location"):
    return NS(data_path=path)


def slot():
    value = NS()
    value.as_pointer = lambda: id(value)
    return value


def action(channelbag=None, legacy=None):
    value = NS(name="Action", fcurves=legacy or [], layers=[])
    value.as_pointer = lambda: id(value)
    if channelbag is not None:
        value.layers = [NS(strips=[NS(type="KEYFRAME", channelbag=channelbag)])]
    return value


def root(action_value=None, slot_value=None):
    return NS(name="CHR_A_root", parent=None, constraints=[],
              animation_data=NS(action=action_value, action_slot=slot_value, nla_tracks=[], drivers=[]))


class FastLogicTests(unittest.TestCase):
    def setUp(self):
        self.scope = fast_functions()
        self.warnings = []

    def read(self, obj):
        return self.scope["_action_location_fcurves"](obj, self.warnings)

    def paths(self, obj, entry, objects=None):
        lookup = {obj.name: obj, **(objects or {})}
        self.scope["_object"] = lookup.get
        errors, checks = [], []
        self.scope["_validate_paths"]([{"root": obj.name, **entry}], {}, errors, self.warnings, checks)
        return [x["code"] for x in errors], checks

    def test_legacy_action_and_drivers(self):
        obj = root(action(legacy=[curve(), curve("rotation_euler")]))
        obj.animation_data.drivers = [curve()]
        self.assertEqual(self.read(obj), ["location", "location"])
        self.assertEqual(self.warnings, [])

    def test_layered_action_reads_owner_slot(self):
        owner_slot = slot()
        seen = []
        obj = root(action(lambda value: seen.append(value) or NS(fcurves=[curve()])), owner_slot)
        self.assertEqual(self.read(obj), ["location"])
        self.assertEqual(seen, [owner_slot])
        self.assertEqual(self.warnings, [])

    def test_channelbag_failure_is_unknown_not_empty_success(self):
        def fail(_):
            raise RuntimeError("Channelbag not readable")
        self.assertEqual(self.read(root(action(fail), slot())), [])
        self.assertEqual(self.warnings[0]["code"], "ANIMATION_DATA_UNREADABLE")
        self.assertEqual(self.warnings[0]["scope"], "root_motion_sources")

    def test_missing_layered_slot_warns(self):
        self.read(root(action(lambda _: NS(fcurves=[]))))
        self.assertEqual(self.warnings[0]["code"], "ANIMATION_DATA_UNREADABLE")

    def test_empty_channelbag_is_valid_empty_data(self):
        self.assertEqual(self.read(root(action(lambda _: None), slot())), [])
        self.assertEqual(self.warnings, [])

    def test_nla_uses_its_own_slot(self):
        active, nla = slot(), slot()
        seen = []
        shared = action(lambda value: seen.append(value) or NS(fcurves=[curve()] if value is nla else []))
        obj = root(shared, active)
        obj.animation_data.nla_tracks = [NS(strips=[NS(action=shared, action_slot=nla)])]
        self.assertEqual(self.read(obj), ["location"])
        self.assertEqual(seen, [active, nla])

    def test_nla_missing_slot_does_not_fall_back_to_active_slot(self):
        obj = root(None, slot())
        obj.animation_data.nla_tracks = [NS(strips=[NS(action=action(lambda _: None), action_slot=None)])]
        self.read(obj)
        self.assertEqual(self.warnings[0]["code"], "ANIMATION_DATA_UNREADABLE")

    def test_unreadable_animation_container_warns(self):
        obj = root()
        obj.animation_data.nla_tracks = None
        self.assertEqual(self.read(obj), [])
        self.assertEqual(self.warnings[0]["code"], "ANIMATION_DATA_UNREADABLE")

    def test_parent_mode_allows_carrier_location_animation(self):
        obj, carrier = root(), root(action(legacy=[curve()]))
        carrier.name = "PRP_carrier"
        obj.parent = carrier
        errors, checks = self.paths(obj, {"motion_owner": "parent", "parent": carrier.name}, {carrier.name: carrier})
        self.assertEqual(errors, [])
        self.assertEqual(checks[0]["scope"], "binding_and_root_location_only")

    def test_parent_mode_rejects_duplicate_motion_and_wrong_parent(self):
        obj, carrier = root(action(legacy=[curve()])), root()
        carrier.name = "PRP_carrier"
        obj.constraints = [NS(type="FOLLOW_PATH")]
        errors, _ = self.paths(obj, {"motion_owner": "parent", "parent": carrier.name}, {carrier.name: carrier})
        self.assertEqual(set(errors), {"PARENT_TARGET_MISMATCH", "PARENT_WITH_FOLLOW_PATH", "ROOT_LOCATION_FCURVE"})

    def test_curve_mode_rejects_root_and_parent_location(self):
        obj = root(action(legacy=[curve()]))
        obj.parent = root(action(legacy=[curve()]))
        path = NS(name="CRV_PATH_A", type="CURVE")
        obj.constraints = [NS(type="FOLLOW_PATH", mute=False, influence=1.0, target=path)]
        errors, _ = self.paths(obj, {"path": path.name}, {path.name: path})
        self.assertEqual(set(errors), {"ROOT_LOCATION_FCURVE", "PARENT_LOCATION_FCURVE"})

    def test_static_and_unsupported_modes(self):
        obj = root()
        errors, checks = self.paths(obj, {"motion_owner": "static"})
        self.assertEqual(errors, [])
        self.assertEqual(checks[0]["status"], "not_applicable")
        errors, _ = self.paths(obj, {"motion_owner": "custom_event"})
        self.assertEqual(errors, [])
        self.assertEqual(self.warnings[0]["code"], "UNSUPPORTED_MOTION_OWNER")

    def test_unknown_scope_reaches_top_level_unverified(self):
        obj = root()
        scene = NS(name="fixture", frame_current=1, frame_subframe=0, camera=None,
                   frame_set=lambda *args, **kwargs: None)
        self.scope.update({
            "bpy": NS(context=NS(scene=scene, evaluated_depsgraph_get=lambda: None)),
            "_request": lambda scene, warnings: {"characters": [{"root": obj.name, "motion_owner": "unsupported"}]},
            "_object": lambda name: obj if name == obj.name else None,
            "_validate_scene_basics": lambda *args: {}, "_validate_cuts": lambda *args: None,
            "_collision_proxies": lambda *args: [], "_shot_frames": lambda *args: [],
            "_validate_camera_motion": lambda *args: None,
        })
        result = self.scope["_validate"]()
        self.assertIn("root_motion_sources", result["unverified"])
        self.assertEqual(result["status"], "needs_review")


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.audit = handoff.Audit(self.root)
        self.scene = json.loads((HERE.parents[1] / "references/production-detail/minimal-scene-spec.json").read_text(encoding="utf-8"))
        # File existence tests deliberately do not claim media decoding.
        (self.root / "video.mp4").write_bytes(b"nonempty media fixture; decoding outside scope")
        (self.root / "person.png").write_bytes(b"nonempty image fixture; decoding outside scope")
        self.package = {
            "required_character_ids": ["CHR_A"],
            "references": [
                {"id": "V1", "kind": "video", "path": "video.mp4", "available": True,
                 "duration_seconds": 5, "binding_status": "bound", "label": "@video1"},
                {"id": "I1", "kind": "image", "role": "character_appearance", "asset_ids": ["CHR_A"],
                 "path": "person.png", "available": True, "binding_status": "bound", "label": "@image1"}],
            "generation_units": [{"unit_id": "U1", "duration_seconds": 5, "time_basis": "local",
                "reference_ids": ["V1", "I1"], "source_reference_id": "V1", "source_range_seconds": [0, 5],
                "prompt": "Complete fixture prompt"}]}

    def codes(self, bucket="errors"):
        return {item["code"] for item in getattr(self.audit, bucket)}

    def test_minimal_scene_has_consistent_references(self):
        handoff.check_scene(self.audit, self.scene)
        self.assertEqual(self.audit.errors + self.audit.warnings, [])

    def test_duplicate_id_and_dangling_shot_reference(self):
        self.scene["assets"].append(copy.deepcopy(self.scene["assets"][0]))
        self.scene["shots"][0]["continuity_links"] = ["SH_020"]
        handoff.check_scene(self.audit, self.scene)
        self.assertTrue({"DUPLICATE_ID", "UNKNOWN_REFERENCE"} <= self.codes())

    def test_cut_and_event_out_of_range(self):
        self.scene["events"] = [{"id": "E1", "target": "PRP_product", "frame": 121}]
        self.scene["sequence"]["camera_cuts"][0]["edit_frame"] = 130
        handoff.check_scene(self.audit, self.scene)
        self.assertTrue({"EVENT_OUT_OF_RANGE", "CUT_OUT_OF_RANGE", "CUT_SHOT_START_MISMATCH"} <= self.codes())

    def test_budget_and_hardware_aliases(self):
        self.scene["budgets"]["objects"] += 1
        handoff.check_scene(self.audit, self.scene, hardware={"profile_id": "other"})
        self.assertTrue({"BUDGET_ALIAS_MISMATCH", "HARDWARE_FILE_PROFILE_MISMATCH"} <= self.codes())

    def test_time_remap_warns_instead_of_claiming_valid(self):
        self.scene["sequence"]["camera_cuts"][0]["source_frame"] = 10
        handoff.check_scene(self.audit, self.scene)
        self.assertIn("SOURCE_EDIT_MAPPING_UNVERIFIED", self.codes("warnings"))

    def test_valid_declared_package_keeps_capability_limits(self):
        handoff.check_package(self.audit, self.package)
        self.assertEqual(self.audit.errors + self.audit.warnings, [])
        self.assertIn("media_decoding_and_metadata", self.audit.result()["unverified"])

    def test_missing_character_does_not_hide_text_completion(self):
        self.package["references"][1].update(available=False, path=None, binding_status="planned")
        handoff.check_package(self.audit, self.package)
        self.assertTrue({"REFERENCE_PENDING", "CHARACTER_IMAGE_PENDING", "BINDING_PENDING"} <= self.codes("warnings"))
        self.assertNotIn("MISSING_PROMPT", self.codes())

    def test_placeholder_is_not_character_asset(self):
        (self.root / "person.png").write_bytes(b"\x89PNG\r\n\x1a\nBlenderAIPrevisPlaceholder\x00true")
        handoff.check_package(self.audit, self.package)
        self.assertIn("PLACEHOLDER_AS_ASSET", self.codes())
        self.assertIn("CHARACTER_IMAGE_PENDING", self.codes("warnings"))

    def test_unknown_reference_and_reused_bound_label(self):
        self.package["generation_units"][0]["reference_ids"].append("NO_IMAGE")
        self.package["references"][1]["label"] = "@video1"
        handoff.check_package(self.audit, self.package)
        self.assertTrue({"UNKNOWN_REFERENCE", "DUPLICATE_BOUND_LABEL"} <= self.codes())

    def test_source_range_and_unit_duration(self):
        self.package["generation_units"][0]["source_range_seconds"] = [4, 10]
        handoff.check_package(self.audit, self.package)
        self.assertTrue({"SOURCE_RANGE_OUT_OF_BOUNDS", "UNIT_SOURCE_DURATION_MISMATCH"} <= self.codes())

    def test_absolute_and_traversal_paths_are_rejected(self):
        for value in ("../outside.png", "C:/Users/person.png", "/tmp/a", "\\\\server\\image.png"):
            self.audit.path(value, "fixture")
        self.assertEqual(len(self.audit.errors), 4)
        self.assertTrue({"NONPORTABLE_PATH", "PATH_OUTSIDE_PROJECT"} <= self.codes())

    def test_malformed_scene_fields_report_errors(self):
        handoff.check_scene(self.audit, {"scene": [], "assets": {}, "shots": [], "events": [],
                                      "sequence": {}, "continuity": {"links": []}})
        self.assertTrue({"EXPECTED_OBJECT", "EXPECTED_ARRAY", "NO_SHOTS"} <= self.codes())

    def test_unbound_text_only_package_has_no_forced_character(self):
        handoff.check_package(self.audit, {"required_character_ids": [], "references": [], "generation_units": [
            {"unit_id": "U1", "duration_seconds": 5, "time_basis": "local", "reference_ids": [], "prompt": "Text only"}]})
        self.assertEqual(self.audit.errors + self.audit.warnings, [])


if __name__ == "__main__":
    unittest.main()
