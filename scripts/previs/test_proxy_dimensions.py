"""Parameter invariants only; never starts Blender or edits a user project."""
import math
import unittest
from derive_proxy_dimensions import derive


class ProxyDimensionsTests(unittest.TestCase):
    def test_adult_total_height_and_tangent_head(self):
        p = derive(1.75, height_source="user_setting")
        self.assertEqual(p["body_length_m"], 1.4)
        self.assertEqual(p["body_diameter_m"], .42)
        self.assertEqual(p["head_diameter_m"], .35)
        self.assertAlmostEqual(p["head_center_z_m"]-p["head_radius_m"], p["body_length_m"])
        self.assertAlmostEqual(p["head_center_z_m"]+p["head_radius_m"], 1.75)

    def test_child_is_not_adult_height_or_proportions(self):
        child, adult = derive(1.15, "child"), derive(1.15)
        self.assertEqual(child["body_diameter_m"], .299)
        self.assertEqual(child["head_diameter_m"], .2875)
        self.assertGreater(child["head_ratio"], adult["head_ratio"])
        self.assertAlmostEqual(child["body_length_m"]+child["head_diameter_m"], 1.15)

    def test_custom_shape_and_scale_keep_rig_budget(self):
        for height in (.4, 2.4, 12):
            p = derive(height, "custom", .16, .28)
            self.assertAlmostEqual(p["body_length_m"]+p["head_diameter_m"], height)
            self.assertEqual(p["visible_mesh_count"], 2)
            self.assertEqual(p["geometry"]["body_vertices"], 656)
            self.assertEqual(p["bend_rig"]["bone_count"], 4)
            joints = p["bend_rig"]["joint_z_m"]
            self.assertEqual(len(joints), 5)
            self.assertEqual(joints[0], 0)
            self.assertEqual(joints[-1], p["body_length_m"])
            self.assertTrue(all(a < b for a,b in zip(joints,joints[1:])))

    def test_invalid_physical_inputs_fail(self):
        for height in (0, -1, math.inf, math.nan):
            with self.assertRaises(ValueError): derive(height)
        for head, body in ((0,.2),(1,.2),(-.1,.2),(.2,0),(.2,-.1),(.2,math.inf)):
            with self.assertRaises(ValueError): derive(1.75, "custom", head, body)
        with self.assertRaises(ValueError): derive(1.75, "custom")
        with self.assertRaises(ValueError): derive(1.75, "unknown")


if __name__ == "__main__":
    unittest.main()
