"""Derive a lightweight cylinder/sphere proxy specification; no Blender required."""
from __future__ import annotations

import argparse
import json
import math

PRESETS = {"adult": (0.20, 0.24), "child": (0.25, 0.26)}
JOINT_FRACTIONS = (0.0, 0.29, 0.58, 0.79, 1.0)


def derive(height, preset="adult", head_ratio=None, body_ratio=None,
           height_source="production_estimate"):
    if preset not in {*PRESETS, "custom"}:
        raise ValueError("Unknown preset.")
    if preset == "custom" and (head_ratio is None or body_ratio is None):
        raise ValueError("Custom preset needs both head_ratio and body_ratio.")
    default_head, default_body = PRESETS.get(preset, (None, None))
    head_ratio = default_head if head_ratio is None else head_ratio
    body_ratio = default_body if body_ratio is None else body_ratio
    height, head_ratio, body_ratio = map(float, (height, head_ratio, body_ratio))
    if not all(math.isfinite(v) for v in (height, head_ratio, body_ratio)):
        raise ValueError("Dimensions must be finite.")
    if height <= 0 or body_ratio <= 0 or not 0 < head_ratio < 1:
        raise ValueError("Height/body ratio must be positive; head ratio must be between 0 and 1.")
    if height_source not in {"user_setting", "reference_derived", "production_estimate"}:
        raise ValueError("Unknown height source.")
    head = height * head_ratio
    length = height - head
    width = height * body_ratio
    joints = [length * f for f in JOINT_FRACTIONS]
    r = lambda value: round(value, 6)
    return {
        "rule_version": "3.1", "units": "m", "preset": preset,
        "height_source": height_source,
        "character_geometry": "cylinder_and_sphere",
        "character_motion_scope": "root_and_simple_bend",
        "total_height_m": r(height), "head_ratio": head_ratio,
        "body_ratio": body_ratio, "body_length_m": r(length),
        "body_diameter_m": r(width), "body_radius_m": r(width / 2),
        "body_center_z_m": r(length / 2), "head_diameter_m": r(head),
        "head_radius_m": r(head / 2), "head_center_z_m": r(length + head / 2),
        "root_origin": "bottom_center_on_support_surface", "forward_axis": "Y", "up_axis": "Z",
        "visible_mesh_count": 2,
        "geometry": {"body_radial_segments": 16, "body_height_intervals": 40,
                     "body_rings": 41, "body_vertices": 16 * 41,
                     "head_segments": 16, "head_rings": 8},
        "bend_rig": {
            "bone_count": 4, "bone_names": ["Lower", "Upper", "TorsoLower", "TorsoUpper"],
            "joint_z_m": [r(v) for v in joints],
            "weight_transition_half_width_m": r(min(.07 * length, .4 * min(b-a for a,b in zip(joints,joints[1:])))),
            "head_follows": "TorsoUpper", "independent_head_acting": False,
            "static_stage": "bound_rest_pose_without_animation_keys",
        },
        "validation_scope": "parameter_math_only; no model or pose has been created or tested",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--height", required=True, type=float)
    parser.add_argument("--preset", choices=["adult", "child", "custom"], default="adult")
    parser.add_argument("--head-ratio", type=float)
    parser.add_argument("--body-ratio", type=float)
    parser.add_argument("--height-source", choices=["user_setting", "reference_derived", "production_estimate"], default="production_estimate")
    args = parser.parse_args()
    try:
        result = derive(args.height, args.preset, args.head_ratio, args.body_ratio, args.height_source)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
