"""Run only in an unsaved, factory-startup Blender background process.

Example:
  blender --background --factory-startup --python-exit-code 1 --python this_file.py

Creates isolated in-memory scenes. Never saves a blend or contacts MCP.
"""

import copy
import json
from pathlib import Path
import time
import unittest

import bpy
from mathutils import Vector


if not bpy.app.background or bpy.data.filepath:
    raise RuntimeError("Tests require an unsaved Blender background process.")


VALIDATOR_PATH = Path(__file__).with_name("validate_previs_fast.py")
VALIDATOR_CODE = compile(VALIDATOR_PATH.read_text(encoding="utf-8"), str(VALIDATOR_PATH), "exec")


class FastValidatorTests(unittest.TestCase):
    def setUp(self):
        self.original_scene = bpy.context.window.scene
        self.scene = bpy.data.scenes.new("TEST_FAST_VALIDATOR")
        bpy.context.window.scene = self.scene
        self.scene.unit_settings.system = "METRIC"
        self.scene.unit_settings.scale_length = 1.0
        self.scene.frame_start = 1
        self.scene.frame_end = 24
        self.scene.render.fps = 24
        self.scene.render.resolution_x = 1280
        self.scene.render.resolution_y = 720
        self.created_data = []

        path_data = bpy.data.curves.new("TEST_PATH_DATA", "CURVE")
        self.created_data.append(path_data)
        path_data.dimensions = "3D"
        path_data.use_path = True
        spline = path_data.splines.new("POLY")
        spline.points.add(1)
        spline.points[0].co = (-1.0, 0.0, 0.0, 1.0)
        spline.points[1].co = (1.0, 0.0, 0.0, 1.0)
        self.path = self.add_object("CRV_PATH_TEST", path_data)
        self.root = self.add_object("CHR_TEST_ROOT")
        self.follow = self.root.constraints.new("FOLLOW_PATH")
        self.follow.target = self.path
        self.follow.use_fixed_location = True
        self.follow.use_curve_follow = False
        for frame, progress in ((1, 0.25), (24, 0.75)):
            self.follow.offset_factor = progress
            self.follow.keyframe_insert("offset_factor", frame=frame)

        self.head = self.add_object("CHR_TEST_HEAD_POINT")
        self.head.parent = self.root
        self.head.location = (0.0, 0.0, 1.7)
        self.torso = self.add_object("CHR_TEST_TORSO_POINT")
        self.torso.parent = self.root
        self.torso.location = (0.0, 0.0, 0.8)

        self.camera = self.add_camera("CAM_TEST", (0.0, -10.0, 2.0), (0.0, 0.0, 1.0))
        self.scene.camera = self.camera
        marker = self.scene.timeline_markers.new("SHOT_001", frame=1)
        marker.camera = self.camera

        mesh = bpy.data.meshes.new("TEST_WALL_DATA")
        self.created_data.append(mesh)
        mesh.from_pydata(
            [(x, y, z) for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)],
            [],
            [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)],
        )
        mesh.update()
        self.wall = self.add_object("COL_TEST_WALL", mesh)
        self.wall.location = (4.0, 0.0, 1.5)
        self.wall.scale = (0.3, 6.0, 3.0)

        self.request = {
            "mode": "fast",
            "revision_id": "test-r1",
            "max_seconds": 10.0,
            "sample_frames": [1, 12, 24],
            "max_samples": 12,
            "active_camera_strategy": "single_scene_markers",
            "characters": [{
                "id": "TEST_CHAR",
                "root": self.root.name,
                "path": self.path.name,
                "collision_radius_m": 0.3,
                "subject_points": [self.head.name, self.torso.name],
            }],
            "shots": [{
                "id": "TEST_SHOT",
                "frame_range": [1, 24],
                "camera": self.camera.name,
                "subject": "TEST_CHAR",
            }],
            "collision_objects": [self.wall.name],
            "camera_cuts": [{"frame": 1, "camera": self.camera.name}],
        }
        self.scene.frame_set(1)
        bpy.context.view_layer.update()

    def tearDown(self):
        test_objects = list(self.scene.objects)
        actions = set()
        for obj in test_objects:
            if obj.animation_data:
                if obj.animation_data.action:
                    actions.add(obj.animation_data.action)
                for track in obj.animation_data.nla_tracks:
                    actions.update(strip.action for strip in track.strips if strip.action)
        bpy.context.window.scene = self.original_scene
        bpy.data.scenes.remove(self.scene)
        for obj in test_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        for action in actions:
            if action.users == 0:
                bpy.data.actions.remove(action)
        for data in self.created_data:
            if data.users == 0:
                if isinstance(data, bpy.types.Camera):
                    bpy.data.cameras.remove(data)
                elif isinstance(data, bpy.types.Curve):
                    bpy.data.curves.remove(data)
                elif isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)

    def add_object(self, name, data=None):
        obj = bpy.data.objects.new(name, data)
        self.scene.collection.objects.link(obj)
        return obj

    def add_camera(self, name, location, target):
        data = bpy.data.cameras.new(name + "_DATA")
        self.created_data.append(data)
        data.lens = 45.0
        data.clip_end = 100.0
        camera = self.add_object(name, data)
        camera.location = location
        camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
        return camera

    def validate(self, request=None):
        self.scene["previs_validation_request"] = json.dumps(self.request if request is None else request)
        bpy.context.view_layer.update()
        namespace = {"__name__": "__previs_regression__"}
        exec(VALIDATOR_CODE, namespace)
        result = namespace["result"]
        self.assertNotIn("VALIDATOR_EXECUTION_FAILED", self.codes(result, "errors"), result)
        return result

    @staticmethod
    def codes(result, category):
        return {issue["code"] for issue in result[category]}

    def add_location_action(self):
        self.root.keyframe_insert("location", index=0, frame=1)
        self.root.keyframe_insert("location", index=0, frame=24)
        action = self.root.animation_data.action
        self.assertTrue(action.layers, "Test must exercise layered Actions.")
        self.assertIsNotNone(self.root.animation_data.action_slot)
        return action, self.root.animation_data.action_slot

    def test_valid_declared_scene(self):
        result = self.validate()
        self.assertEqual(result["errors"], [], result)
        self.assertEqual(result["warnings"], [], result)
        self.assertEqual(result["status"], "sampled_checks_passed")
        self.assertEqual(result["sample_frames"], [1, 12, 24])
        self.assertNotIn("proxy_collision", result["unverified"])
        self.assertNotIn("subject_framing", result["unverified"])

    def test_character_collision_and_subject_outside_frame(self):
        self.wall.location.x = 0.0
        self.wall.scale.x = 2.0
        self.head.location.x = 100.0
        result = self.validate()
        self.assertIn("CHARACTER_PROXY_COLLISION", self.codes(result, "errors"))
        self.assertIn("SUBJECT_OUTSIDE_SAFE_REGION", self.codes(result, "errors"))

    def test_layered_location_action_conflict(self):
        self.add_location_action()
        self.assertIn("ROOT_LOCATION_FCURVE", self.codes(self.validate(), "errors"))

    def test_nla_location_action_conflict(self):
        action, slot = self.add_location_action()
        track = self.root.animation_data.nla_tracks.new()
        strip = track.strips.new("TEST_LOCATION_NLA", 1, action)
        strip.action_slot = slot
        self.root.animation_data.action = None
        self.assertIsNone(self.root.animation_data.action)
        self.assertIn("ROOT_LOCATION_FCURVE", self.codes(self.validate(), "errors"))

    def test_location_driver_conflict(self):
        self.root.driver_add("location", 0).driver.expression = "0.0"
        self.assertIn("ROOT_LOCATION_FCURVE", self.codes(self.validate(), "errors"))

    def test_missing_shot_camera_does_not_fallback(self):
        self.request["shots"][0]["camera"] = "CAM_DOES_NOT_EXIST"
        self.assertIsNotNone(self.scene.camera)
        self.assertIn("MISSING_SHOT_CAMERA", self.codes(self.validate(), "errors"))

    def test_explicit_sample_limit(self):
        self.request["sample_frames"] = list(range(1, 25))
        self.request["max_samples"] = 3
        result = self.validate()
        self.assertLessEqual(len(result["planned_sample_frames"]), 3)
        self.assertLessEqual(result["sample_count"], 3)
        self.assertIn("SAMPLE_LIMIT_REACHED", self.codes(result, "warnings"))
        self.assertIn("requested_sampling_coverage", result["unverified"])

    def test_anchor_sample_limit_and_huge_shot_range(self):
        self.request.pop("sample_frames")
        self.request["max_samples"] = 3
        self.request["risk_frames"] = list(range(1, 25))
        self.request["shots"][0]["frame_range"] = [-1000000000, 1000000000]
        result = self.validate()
        self.assertLessEqual(len(result["planned_sample_frames"]), 3)
        self.assertLessEqual(result["sample_count"], 3)
        self.assertTrue(all(1 <= frame <= 24 for frame in result["sample_frames"]))
        self.assertIn("ANCHOR_LIMIT_REACHED", self.codes(result, "warnings"))

    def test_missing_proxy_and_subject_points_are_unverified(self):
        self.request["collision_objects"] = []
        self.request["characters"][0]["subject_points"] = []
        result = self.validate()
        self.assertIn("proxy_collision", result["unverified"])
        self.assertIn("subject_framing", result["unverified"])
        self.assertIn("NO_COLLISION_PROXIES", self.codes(result, "warnings"))
        self.assertIn("NO_SUBJECT_POINTS", self.codes(result, "warnings"))

    def test_missing_subject_entry_is_unverified(self):
        self.request["shots"][0]["subject"] = "UNKNOWN_CHARACTER"
        result = self.validate()
        self.assertIn("NO_SHOT_SUBJECT", self.codes(result, "warnings"))
        self.assertIn("subject_framing", result["unverified"])

    def test_restore_frame_subframe_and_active_camera(self):
        original_camera = self.add_camera("CAM_RESTORE", (2.0, -10.0, 2.0), (0.0, 0.0, 1.0))
        self.scene.frame_set(9, subframe=0.375)
        self.scene.camera = original_camera
        self.validate()
        self.assertEqual(self.scene.frame_current, 9)
        self.assertAlmostEqual(self.scene.frame_subframe, 0.375)
        self.assertEqual(self.scene.camera, original_camera)


if __name__ == "__main__":
    started = time.perf_counter()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FastValidatorTests)
    outcome = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({
        "blender_version": bpy.app.version_string,
        "tests_run": outcome.testsRun,
        "failures": len(outcome.failures),
        "errors": len(outcome.errors),
        "test_wall_seconds": round(time.perf_counter() - started, 3),
        "saved_blend": bool(bpy.data.filepath),
    }))
    if not outcome.wasSuccessful():
        raise RuntimeError("Fast previs validator regression tests failed.")
