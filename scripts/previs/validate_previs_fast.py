"""Incremental, read-only Blender previs validation for the official MCP code tool.

Execute this file's text in Blender and consume the top-level ``result`` value.
It reads a JSON object from ``scene["previs_validation_request"]``.  The request
selects the changed shots, character roots, collision proxies, and thresholds.
The script temporarily samples frames and restores the original frame; it does
not render, save, create objects, or change authored animation data.

This is a structural validator.  It reports data evidence for paths, camera
framing, proxy collisions, cuts, and motion spikes.  It does not replace
normal-speed viewing or a director's visual judgment.
"""

import json
import math
import time

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


REQUEST_PROPERTY = "previs_validation_request"
DEFAULT_STRIDE = 6
DEFAULT_MAX_SAMPLES = 96
DEFAULT_MAX_SECONDS = 3.0
SEMANTIC_PREFIXES = {
    "character": ("CHR_",),
    "path": ("CRV_PATH_",),
    "camera": ("CAM_",),
}


def _issue(items, code, **evidence):
    if len(items) >= 200:
        if items[-1]["code"] != "ISSUE_OUTPUT_LIMIT":
            items.append({"code": "ISSUE_OUTPUT_LIMIT", "omitted_count": 1})
        else:
            items[-1]["omitted_count"] += 1
        return
    if "frame" not in evidence and any(item == {"code": code, **evidence} for item in items):
        return
    items.append({"code": code, **evidence})


def _as_dict(value):
    if isinstance(value, dict):
        return value
    try:
        return dict(value)
    except (TypeError, ValueError):
        return {}


def _request(scene, warnings):
    raw = scene.get(REQUEST_PROPERTY)
    if raw is None:
        _issue(warnings, "MISSING_VALIDATION_REQUEST", property=REQUEST_PROPERTY)
        return {}
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            _issue(warnings, "INVALID_VALIDATION_REQUEST_JSON", detail=str(exc))
            return {}
    else:
        value = _as_dict(raw)
    if not isinstance(value, dict):
        _issue(warnings, "INVALID_VALIDATION_REQUEST", value_type=type(value).__name__)
        return {}
    for key in ("shots", "characters", "collision_objects", "risk_frames", "affected_shot_ids", "camera_cuts"):
        if not isinstance(value.get(key, []), list):
            _issue(warnings, "INVALID_REQUEST_LIST", field=key)
            value[key] = []
    selected = value.get("affected_shot_ids", [])
    if any(not isinstance(item, str) for item in selected):
        _issue(warnings, "INVALID_AFFECTED_SHOT_IDS")
        value["affected_shot_ids"] = [item for item in selected if isinstance(item, str)]
    shots = value.get("shots", [])
    if any(not isinstance(shot, dict) or not isinstance(shot.get("id"), str) for shot in shots):
        _issue(warnings, "INVALID_SHOT_CONFIGURATION")
        value["shots"] = [shot for shot in shots if isinstance(shot, dict) and isinstance(shot.get("id"), str)]
    return value


def _object(name):
    return bpy.data.objects.get(name) if isinstance(name, str) and name else None


def _frame_number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return int(value) if math.isfinite(value) and value.is_integer() else None


def _positive_integer(value, fallback, minimum=1):
    number = _frame_number(value)
    return number if number is not None and number >= minimum else fallback


def _semantic_prefixes(request, category):
    custom = _as_dict(request.get("semantic_prefixes", {})).get(category)
    if isinstance(custom, (list, tuple)):
        prefixes = tuple(item for item in custom if isinstance(item, str) and item)
        if prefixes:
            return prefixes
    return SEMANTIC_PREFIXES[category]


def _has_semantic_prefix(name, prefixes):
    return isinstance(name, str) and name.startswith(prefixes)


def _even_sample(sequence, maximum):
    if maximum <= 0:
        return []
    if len(sequence) <= maximum:
        return list(sequence)
    if maximum == 1:
        return [sequence[len(sequence) // 2]]
    return [sequence[round(index * (len(sequence) - 1) / (maximum - 1))] for index in range(maximum)]


def _bounded_frames(scene, frames, request, warnings):
    """Keep explicit and generated sampling within the same bounded contract."""
    in_range = set()
    for frame in frames:
        number = _frame_number(frame)
        if number is not None and scene.frame_start <= number <= scene.frame_end:
            in_range.add(number)
    in_range = sorted(in_range)
    maximum = _positive_integer(request.get("max_samples", DEFAULT_MAX_SAMPLES), DEFAULT_MAX_SAMPLES, minimum=3)
    if len(in_range) <= maximum:
        return in_range
    sampled = _even_sample(in_range, maximum)
    _issue(warnings, "SAMPLE_LIMIT_REACHED", requested=len(in_range), sampled=len(sampled), maximum=maximum)
    return sorted(set(sampled))


def _positive_float(value, fallback, warnings, code, **evidence):
    try:
        number = float(value)
        if math.isfinite(number) and number > 0.0:
            return number
    except (TypeError, ValueError):
        pass
    _issue(warnings, code, value=value, fallback=fallback, **evidence)
    return fallback


def _optional_positive_float(value, warnings, code, **evidence):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = None
    if number is not None and math.isfinite(number) and number > 0.0:
        return number
    _issue(warnings, code, value=value, **evidence)
    return None


def _nla_strips(strips):
    for strip in strips:
        yield strip
        yield from _nla_strips(getattr(strip, "strips", []))


def _action_location_fcurves(obj, warnings):
    try:
        return _read_action_location_fcurves(obj, warnings)
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
        _issue(warnings, "ANIMATION_DATA_UNREADABLE", object=getattr(obj, "name", None),
               detail=str(exc), scope="root_motion_sources")
        return []


def _read_action_location_fcurves(obj, warnings):
    if obj is None or obj.animation_data is None:
        return []
    animation_data = obj.animation_data
    actions = [(animation_data.action, getattr(animation_data, "action_slot", None))]
    for track in animation_data.nla_tracks:
        for strip in _nla_strips(track.strips):
            # An NLA strip can use a different slot from the active Action.
            actions.append((strip.action, getattr(strip, "action_slot", None)))
    data_paths = []
    seen_actions = set()
    for action, slot in actions:
        if action is None:
            continue
        # Blender 5.2 layered Actions keep F-curves in a strip Channelbag instead
        # of Action.fcurves. Keep the legacy path for older files and versions.
        try:
            slot_key = slot.as_pointer() if slot is not None else 0
            action_key = (action.as_pointer(), slot_key)
            if action_key in seen_actions:
                continue
            seen_actions.add(action_key)
            legacy_fcurves = getattr(action, "fcurves", None)
            if legacy_fcurves:
                data_paths.extend(curve.data_path for curve in legacy_fcurves if curve.data_path == "location")
            for layer in getattr(action, "layers", []):
                for strip in getattr(layer, "strips", []):
                    if getattr(strip, "type", None) != "KEYFRAME":
                        continue
                    try:
                        if slot is None:
                            raise ValueError("Layered Action has no readable slot for this owner")
                        channelbag = strip.channelbag(slot)
                        if channelbag is not None:
                            data_paths.extend(curve.data_path for curve in channelbag.fcurves if curve.data_path == "location")
                    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
                        _issue(warnings, "ANIMATION_DATA_UNREADABLE", object=obj.name,
                               action=getattr(action, "name", None), detail=str(exc), scope="root_motion_sources")
        except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
            _issue(warnings, "ANIMATION_DATA_UNREADABLE", object=obj.name,
                   action=getattr(action, "name", None), detail=str(exc), scope="root_motion_sources")
    try:
        data_paths.extend(curve.data_path for curve in animation_data.drivers if curve.data_path == "location")
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
        _issue(warnings, "ANIMATION_DATA_UNREADABLE", object=obj.name, detail=str(exc), scope="root_motion_sources")
    return data_paths


def _parent_location_animation(root, warnings):
    results = []
    current = root.parent if root is not None else None
    while current is not None:
        if _action_location_fcurves(current, warnings):
            results.append(current.name)
        current = current.parent
    return results


def _curve_constraint(root):
    if root is None:
        return []
    return [constraint for constraint in root.constraints if constraint.type == "FOLLOW_PATH"]


def _validate_scene_basics(scene, request, errors, warnings, checks):
    unit_settings = scene.unit_settings
    if unit_settings.system != "METRIC":
        _issue(errors, "SCENE_NOT_METRIC", unit_system=unit_settings.system)
    if not math.isfinite(unit_settings.scale_length) or unit_settings.scale_length <= 0.0:
        _issue(errors, "INVALID_UNIT_SCALE", scale_length=unit_settings.scale_length)
    elif not math.isclose(unit_settings.scale_length, 1.0, abs_tol=1e-6):
        _issue(errors, "UNSUPPORTED_UNIT_SCALE", scale_length=unit_settings.scale_length, required=1.0)

    active_camera = scene.camera
    if active_camera is None or active_camera.type != "CAMERA":
        _issue(errors, "INVALID_ACTIVE_CAMERA", camera=getattr(active_camera, "name", None))
    else:
        if not _has_semantic_prefix(active_camera.name, _semantic_prefixes(request, "camera")):
            _issue(warnings, "NONSEMANTIC_CAMERA_NAME", camera=active_camera.name)
        checks.append({"check": "active_camera", "camera": active_camera.name})

    marker_cameras = {}
    for marker in scene.timeline_markers:
        camera = getattr(marker, "camera", None)
        if marker.frame < scene.frame_start or marker.frame > scene.frame_end:
            _issue(warnings, "TIMELINE_MARKER_OUT_OF_RANGE", marker=marker.name, frame=marker.frame)
        if camera is None:
            continue
        if camera.type != "CAMERA":
            _issue(errors, "TIMELINE_MARKER_INVALID_CAMERA", marker=marker.name, camera=camera.name)
            continue
        marker_cameras.setdefault(marker.frame, set()).add(camera.name)
    if request.get("camera_cuts") and not marker_cameras and request.get("active_camera_strategy", "single_scene_markers") == "single_scene_markers":
        _issue(errors, "CAMERA_CUTS_WITHOUT_TIMELINE_MARKERS")
    checks.append({"check": "timeline_markers", "count": len(scene.timeline_markers), "camera_marker_count": sum(len(cameras) for cameras in marker_cameras.values())})
    return marker_cameras


def _bounds(obj_eval):
    try:
        corners = list(obj_eval.bound_box)
        if not corners or all(tuple(corner) == (-1.0, -1.0, -1.0) for corner in corners):
            return None
        points = [obj_eval.matrix_world @ Vector(corner) for corner in corners]
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        return None
    if len(points) != 8:
        return None
    return (
        Vector((min(point.x for point in points), min(point.y for point in points), min(point.z for point in points))),
        Vector((max(point.x for point in points), max(point.y for point in points), max(point.z for point in points))),
    )


def _sphere_intersects_bounds(center, radius, bounds):
    lower, upper = bounds
    closest = Vector((
        min(max(center.x, lower.x), upper.x),
        min(max(center.y, lower.y), upper.y),
        min(max(center.z, lower.z), upper.z),
    ))
    return (center - closest).length <= radius


def _point_for_reference(root, reference, depsgraph):
    target = _object(reference)
    if target is not None:
        return target.evaluated_get(depsgraph).matrix_world.translation, target.name
    return root.evaluated_get(depsgraph).matrix_world.translation, root.name


def _belongs_to(hit_object, root):
    current = hit_object
    while current is not None:
        if current == root:
            return True
        current = current.parent
    return False


def _shot_frames(scene, request, warnings):
    configured = request.get("sample_frames")
    if isinstance(configured, list):
        return _bounded_frames(scene, configured, request, warnings)

    stride = _positive_integer(request.get("sample_stride", DEFAULT_STRIDE), DEFAULT_STRIDE)
    selected = set(request.get("affected_shot_ids", []))
    frames = set()
    anchors = set()
    maximum = _positive_integer(request.get("max_samples", DEFAULT_MAX_SAMPLES), DEFAULT_MAX_SAMPLES, minimum=3)
    shots = request.get("shots", [])
    for shot in shots if isinstance(shots, list) else []:
        if not isinstance(shot, dict):
            continue
        shot_id = shot.get("id")
        if selected and shot_id not in selected:
            continue
        frame_range = shot.get("frame_range")
        if not isinstance(frame_range, (list, tuple)) or len(frame_range) != 2:
            _issue(warnings, "INVALID_SHOT_RANGE", shot_id=shot_id)
            continue
        start, end = _frame_number(frame_range[0]), _frame_number(frame_range[1])
        if start is None or end is None:
            _issue(warnings, "INVALID_SHOT_RANGE", shot_id=shot_id)
            continue
        if end < start:
            _issue(warnings, "REVERSED_SHOT_RANGE", shot_id=shot_id, frame_range=[start, end])
            continue
        start, end = max(start, scene.frame_start), min(end, scene.frame_end)
        if start > end:
            continue
        anchors.update({start, (start + end) // 2, end})
        regular = range(start, end + 1, stride)
        if len(regular) > maximum:
            _issue(warnings, "SAMPLE_LIMIT_REACHED", shot_id=shot_id, requested=len(regular), maximum=maximum)
        # range is lazy: a malformed million-frame shot must not allocate a million samples.
        frames.update(_even_sample(regular, maximum))

    risk_frames = request.get("risk_frames", [])
    for frame in risk_frames if isinstance(risk_frames, (list, tuple)) else []:
        number = _frame_number(frame)
        if number is not None:
            anchors.add(number)
    frames.update(anchors)
    if not frames:
        _issue(warnings, "NO_SHOT_SAMPLING_SCOPE", fallback="current_frame_only")
        return [scene.frame_current]

    in_range = sorted(frame for frame in frames if scene.frame_start <= frame <= scene.frame_end)
    if len(in_range) <= maximum:
        return in_range

    anchors = sorted(frame for frame in anchors if scene.frame_start <= frame <= scene.frame_end)
    if len(anchors) > maximum:
        sampled = _even_sample(anchors, maximum)
        _issue(warnings, "ANCHOR_LIMIT_REACHED", requested=len(anchors), maximum=maximum, omitted_frames=[frame for frame in anchors if frame not in sampled][:96])
        return sampled
    remaining = max(0, maximum - len(anchors))
    candidates = [frame for frame in in_range if frame not in anchors]
    sampled = sorted(set(anchors + _even_sample(candidates, remaining)))
    _issue(warnings, "SAMPLE_LIMIT_REACHED", requested=len(in_range), sampled=len(sampled), maximum=maximum)
    return sampled


def _shot_at_frame(shots, frame):
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        frame_range = shot.get("frame_range", [])
        if not isinstance(frame_range, (list, tuple)) or len(frame_range) != 2:
            continue
        start, end = _frame_number(frame_range[0]), _frame_number(frame_range[1])
        if start is not None and end is not None and start <= frame <= end:
            return shot
    return None


def _safe_region(shot, request):
    region = shot.get("safe_region", request.get("default_safe_region", {}))
    region = _as_dict(region)
    x = region.get("x", [0.05, 0.95])
    y = region.get("y", [0.05, 0.95])
    try:
        values = [float(x[0]), float(x[1]), float(y[0]), float(y[1])]
    except (IndexError, TypeError, ValueError):
        return 0.05, 0.95, 0.05, 0.95
    if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in values):
        return 0.05, 0.95, 0.05, 0.95
    min_x, max_x, min_y, max_y = values
    return (min_x, max_x, min_y, max_y) if min_x < max_x and min_y < max_y else (0.05, 0.95, 0.05, 0.95)


def _characters(request, warnings):
    entries = request.get("characters", [])
    if not isinstance(entries, list):
        _issue(warnings, "INVALID_CHARACTER_CONFIGURATION")
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _validate_paths(characters, request, errors, warnings, checks):
    for entry in characters:
        character_id = entry.get("id", entry.get("root"))
        root = _object(entry.get("root"))
        expected_path = _object(entry.get("path"))
        if root is None:
            _issue(errors, "MISSING_CHARACTER_ROOT", character_id=character_id, root=entry.get("root"))
            continue
        motion_owner = entry.get("motion_owner", "curve_follow_path")
        if entry.get("motion_scope") == "static" or motion_owner == "static":
            checks.append({"check": "curve_constraint", "character_id": character_id, "status": "not_applicable"})
            continue
        if not _has_semantic_prefix(root.name, _semantic_prefixes(request, "character")):
            _issue(warnings, "NONSEMANTIC_CHARACTER_NAME", character_id=character_id, root=root.name)
        if motion_owner == "parent":
            parent = _object(entry.get("parent"))
            if parent is None:
                _issue(errors, "MISSING_DECLARED_PARENT", character_id=character_id, parent=entry.get("parent"))
            elif root.parent != parent:
                _issue(errors, "PARENT_TARGET_MISMATCH", character_id=character_id,
                       expected=parent.name, actual=getattr(root.parent, "name", None))
            if _curve_constraint(root):
                _issue(errors, "PARENT_WITH_FOLLOW_PATH", character_id=character_id)
            if _action_location_fcurves(root, warnings):
                _issue(errors, "ROOT_LOCATION_FCURVE", character_id=character_id, root=root.name)
            checks.append({"check": "parent_motion_source", "character_id": character_id,
                           "parent": getattr(parent, "name", None), "scope": "binding_and_root_location_only"})
            continue
        if motion_owner != "curve_follow_path":
            _issue(warnings, "UNSUPPORTED_MOTION_OWNER", character_id=character_id,
                   motion_owner=motion_owner, scope="root_motion_sources")
            continue
        if expected_path is None:
            _issue(errors, "MISSING_DECLARED_PATH", character_id=character_id, path=entry.get("path"))
        elif not _has_semantic_prefix(expected_path.name, _semantic_prefixes(request, "path")):
            _issue(warnings, "NONSEMANTIC_PATH_NAME", character_id=character_id, path=expected_path.name)
        constraints = _curve_constraint(root)
        if len(constraints) != 1:
            _issue(errors, "FOLLOW_PATH_CONSTRAINT_COUNT", character_id=character_id, root=root.name, count=len(constraints))
        else:
            constraint = constraints[0]
            if constraint.mute or constraint.influence < 0.999:
                _issue(errors, "FOLLOW_PATH_DISABLED_OR_PARTIAL", character_id=character_id, mute=constraint.mute, influence=constraint.influence)
            if expected_path is not None and constraint.target != expected_path:
                _issue(errors, "FOLLOW_PATH_TARGET_MISMATCH", character_id=character_id, root=root.name, expected=expected_path.name, actual=getattr(constraint.target, "name", None))
            elif constraint.target is None:
                _issue(errors, "FOLLOW_PATH_TARGET_MISSING", character_id=character_id, root=root.name)
            elif constraint.target.type != "CURVE":
                _issue(errors, "FOLLOW_PATH_TARGET_NOT_CURVE", character_id=character_id, root=root.name, target=constraint.target.name)
        if expected_path is not None and expected_path.type != "CURVE":
            _issue(errors, "DECLARED_PATH_NOT_CURVE", character_id=character_id, path=expected_path.name)
        if _action_location_fcurves(root, warnings):
            _issue(errors, "ROOT_LOCATION_FCURVE", character_id=character_id, root=root.name)
        parent_animation = _parent_location_animation(root, warnings)
        if parent_animation:
            _issue(errors, "PARENT_LOCATION_FCURVE", character_id=character_id, parents=parent_animation)
        checks.append({"character_id": character_id, "root": root.name, "path": getattr(expected_path, "name", None), "check": "curve_constraint"})


def _collision_proxies(request, warnings):
    names = request.get("collision_objects", [])
    if not isinstance(names, list):
        _issue(warnings, "INVALID_COLLISION_OBJECTS")
        return []
    proxies = []
    for name in names:
        obj = _object(name)
        if obj is None:
            _issue(warnings, "MISSING_COLLISION_PROXY", object=name)
        elif obj.type not in {"MESH", "CURVE"}:
            _issue(warnings, "INVALID_COLLISION_PROXY_TYPE", object=name, type=obj.type)
        else:
            proxies.append(obj)
    if not proxies:
        _issue(warnings, "NO_COLLISION_PROXIES", status="unverified")
    return proxies


def _validate_frame(scene, depsgraph, frame, request, characters, proxies, errors, warnings, camera_history):
    scene.frame_set(frame)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bounds_by_name = {}
    for proxy in proxies:
        evaluated = proxy.evaluated_get(depsgraph)
        bounds = _bounds(evaluated)
        if bounds is None:
            _issue(warnings, "UNKNOWN_COLLISION_PROXY_BOUNDS", frame=frame, object=proxy.name)
        else:
            bounds_by_name[proxy.name] = bounds

    for entry in characters:
        character_id = entry.get("id", entry.get("root"))
        root = _object(entry.get("root"))
        if root is None:
            continue
        center = root.evaluated_get(depsgraph).matrix_world.translation
        radius = _positive_float(entry.get("collision_radius_m", 0.35), 0.35, warnings, "INVALID_CHARACTER_COLLISION_RADIUS", character_id=character_id)
        for name, bounds in bounds_by_name.items():
            if _sphere_intersects_bounds(center, radius, bounds):
                _issue(errors, "CHARACTER_PROXY_COLLISION", frame=frame, character_id=character_id, collision_object=name, method="sphere_vs_aabb_proxy")

    shots = request.get("shots", []) if isinstance(request.get("shots"), list) else []
    shot = _shot_at_frame(shots, frame)
    if shot is None:
        return
    camera = _object(shot.get("camera"))
    if camera is None or camera.type != "CAMERA":
        _issue(errors, "MISSING_SHOT_CAMERA", frame=frame, shot_id=shot.get("id"), camera=shot.get("camera"))
        return
    camera_eval = camera.evaluated_get(depsgraph)
    if request.get("active_camera_strategy", "single_scene_markers") == "single_scene_markers" and scene.camera != camera:
        _issue(errors, "ACTIVE_SHOT_CAMERA_MISMATCH", frame=frame, shot_id=shot.get("id"), expected=camera.name, actual=getattr(scene.camera, "name", None))

    camera_position = camera.evaluated_get(depsgraph).matrix_world.translation
    camera_radius = _positive_float(shot.get("camera_radius_m", request.get("camera_radius_m", 0.2)), 0.2, warnings, "INVALID_CAMERA_COLLISION_RADIUS", shot_id=shot.get("id"))
    for name, bounds in bounds_by_name.items():
        if _sphere_intersects_bounds(camera_position, camera_radius, bounds):
            _issue(errors, "CAMERA_PROXY_COLLISION", frame=frame, shot_id=shot.get("id"), collision_object=name, method="sphere_vs_aabb_proxy")

    character_id = shot.get("subject")
    entry = next((item for item in characters if item.get("id", item.get("root")) == character_id), None)
    if entry is not None:
        root = _object(entry.get("root"))
        if root is not None:
            references = shot.get("subject_points", entry.get("subject_points", []))
            if not isinstance(references, list) or not references:
                _issue(warnings, "NO_SUBJECT_POINTS", shot_id=shot.get("id"), status="unverified")
                references = []
            min_x, max_x, min_y, max_y = _safe_region(shot, request)
            for reference in references:
                if _object(reference) is None:
                    _issue(warnings, "MISSING_SUBJECT_POINT", shot_id=shot.get("id"), point=reference, status="unverified")
                    continue
                point, label = _point_for_reference(root, reference, depsgraph)
                projected = world_to_camera_view(scene, camera_eval, point)
                if projected.z <= 0.0 or not (min_x <= projected.x <= max_x and min_y <= projected.y <= max_y):
                    _issue(errors, "SUBJECT_OUTSIDE_SAFE_REGION", frame=frame, shot_id=shot.get("id"), subject=character_id, point=label, projected=[round(projected.x, 4), round(projected.y, 4), round(projected.z, 4)], safe_region={"x": [min_x, max_x], "y": [min_y, max_y]})
                elif not camera_eval.data.clip_start <= projected.z <= camera_eval.data.clip_end:
                    _issue(errors, "SUBJECT_OUTSIDE_CLIP_RANGE", frame=frame, shot_id=shot.get("id"), point=label, depth=round(projected.z, 4))
                if bool(shot.get("check_occlusion", request.get("check_occlusion", False))):
                    direction = point - camera_position
                    distance = direction.length
                    if distance > 1e-6:
                        hit, _, _, _, hit_object, _ = scene.ray_cast(depsgraph, camera_position, direction.normalized(), distance=distance)
                        if hit and hit_object is not None and not _belongs_to(hit_object, root):
                            _issue(warnings, "SUBJECT_RAY_OCCLUDED", frame=frame, shot_id=shot.get("id"), subject=character_id, point=label, occluder=hit_object.name)
    else:
        _issue(warnings, "NO_SHOT_SUBJECT", shot_id=shot.get("id"), subject=character_id, status="unverified")

    # Motion limits apply inside a shot; a hard cut is not a camera acceleration.
    camera_history.setdefault((shot.get("id"), camera.name), []).append((frame, camera_position.copy()))


def _validate_camera_motion(scene, request, history, warnings):
    fps_base = _positive_float(scene.render.fps_base, 1.0, warnings, "INVALID_FPS_BASE")
    fps = _positive_float(float(scene.render.fps) / fps_base, 24.0, warnings, "INVALID_SCENE_FPS")
    limits = _as_dict(request.get("motion_limits", {}))
    max_speed = _optional_positive_float(limits.get("camera_speed_mps"), warnings, "INVALID_MOTION_LIMIT", field="camera_speed_mps")
    max_accel = _optional_positive_float(limits.get("camera_accel_mps2"), warnings, "INVALID_MOTION_LIMIT", field="camera_accel_mps2")
    max_jerk = _optional_positive_float(limits.get("camera_jerk_mps3"), warnings, "INVALID_MOTION_LIMIT", field="camera_jerk_mps3")
    for (shot_id, camera_name), points in history.items():
        ordered = sorted(points)
        velocities = []
        accelerations = []
        for (frame_a, point_a), (frame_b, point_b) in zip(ordered, ordered[1:]):
            dt = (frame_b - frame_a) / fps
            if dt <= 0.0:
                continue
            velocity = (point_b - point_a) / dt
            velocities.append((frame_b, velocity, dt))
            if max_speed is not None and velocity.length > float(max_speed):
                _issue(warnings, "CAMERA_SPEED_LIMIT", frame=frame_b, shot_id=shot_id, camera=camera_name, speed_mps=round(velocity.length, 4), limit_mps=float(max_speed))
        for (frame_a, velocity_a, dt_a), (frame_b, velocity_b, dt_b) in zip(velocities, velocities[1:]):
            dt = max(1e-6, (dt_a + dt_b) * 0.5)
            acceleration = (velocity_b - velocity_a) / dt
            accelerations.append((frame_b, acceleration, dt))
            if max_accel is not None and acceleration.length > float(max_accel):
                _issue(warnings, "CAMERA_ACCEL_LIMIT", frame=frame_b, shot_id=shot_id, camera=camera_name, accel_mps2=round(acceleration.length, 4), limit_mps2=float(max_accel))
        for (frame_a, accel_a, dt_a), (frame_b, accel_b, dt_b) in zip(accelerations, accelerations[1:]):
            dt = max(1e-6, (dt_a + dt_b) * 0.5)
            jerk = (accel_b - accel_a) / dt
            if max_jerk is not None and jerk.length > float(max_jerk):
                _issue(warnings, "CAMERA_JERK_LIMIT", frame=frame_b, shot_id=shot_id, camera=camera_name, jerk_mps3=round(jerk.length, 4), limit_mps3=float(max_jerk))


def _validate_cuts(scene, request, marker_cameras, errors, warnings):
    cuts = request.get("camera_cuts", [])
    if not isinstance(cuts, list):
        return
    for cut in cuts:
        if not isinstance(cut, dict):
            _issue(warnings, "INVALID_CAMERA_CUT")
            continue
        frame = _frame_number(cut.get("frame"))
        camera = _object(cut.get("camera"))
        if frame is None:
            _issue(errors, "INVALID_CAMERA_CUT_FRAME", cut=cut)
        elif frame < scene.frame_start or frame > scene.frame_end:
            _issue(errors, "CAMERA_CUT_OUT_OF_RANGE", frame=frame, camera=cut.get("camera"))
        if camera is None or camera.type != "CAMERA":
            _issue(errors, "INVALID_CAMERA_CUT_CAMERA", frame=frame, camera=cut.get("camera"))
        elif request.get("active_camera_strategy", "single_scene_markers") == "single_scene_markers" and frame is not None and marker_cameras.get(frame, set()) != {camera.name}:
            _issue(errors, "CAMERA_CUT_MARKER_MISMATCH", frame=frame, camera=camera.name, marker_cameras=sorted(marker_cameras.get(frame, set())))


def _validate():
    started = time.perf_counter()
    scene = bpy.context.scene
    original_frame = scene.frame_current
    original_subframe = scene.frame_subframe
    original_camera = scene.camera
    errors = []
    warnings = []
    checks = []
    request = _request(scene, warnings)
    selected = set(request.get("affected_shot_ids", []))
    if selected:
        request["shots"] = [shot for shot in request.get("shots", []) if shot.get("id") in selected]
    if not request.get("shots"):
        _issue(warnings, "NO_SHOT_CONFIGURATION", status="unverified")
    max_seconds = _positive_float(request.get("max_seconds", DEFAULT_MAX_SECONDS), DEFAULT_MAX_SECONDS, warnings, "INVALID_TIME_BUDGET")
    characters = _characters(request, warnings)
    marker_cameras = _validate_scene_basics(scene, request, errors, warnings, checks)
    _validate_paths(characters, request, errors, warnings, checks)
    _validate_cuts(scene, request, marker_cameras, errors, warnings)
    proxies = _collision_proxies(request, warnings)
    frames = _shot_frames(scene, request, warnings)
    camera_history = {}
    completed_frames = []
    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for frame in frames:
            if time.perf_counter() - started >= max_seconds:
                _issue(warnings, "TIME_BUDGET_REACHED", max_seconds=max_seconds, completed=len(completed_frames), planned=len(frames))
                break
            _validate_frame(scene, depsgraph, frame, request, characters, proxies, errors, warnings, camera_history)
            completed_frames.append(frame)
        _validate_camera_motion(scene, request, camera_history, warnings)
    except Exception as exc:
        _issue(errors, "VALIDATOR_EXECUTION_FAILED", exception=type(exc).__name__, detail=str(exc))
    finally:
        scene.frame_set(original_frame, subframe=original_subframe)
        scene.camera = original_camera
    if not completed_frames:
        _issue(warnings, "NO_COMPLETED_SAMPLES", status="unverified")
    unverified = ["continuous_collision_between_samples", "full_character_body_clearance", "director_quality", "viewport_fps",
                  "full_event_time_mapping", "full_constraint_and_parent_motion_composition"]
    if any(item.get("scope") == "root_motion_sources" for item in warnings):
        unverified.append("root_motion_sources")
    if not proxies:
        unverified.append("proxy_collision")
    if any(item["code"] in {"NO_SUBJECT_POINTS", "MISSING_SUBJECT_POINT", "NO_SHOT_SUBJECT", "NO_COMPLETED_SAMPLES", "NO_SHOT_CONFIGURATION"} for item in warnings):
        unverified.append("subject_framing")
    if not request.get("check_occlusion") and not any(shot.get("check_occlusion") for shot in request.get("shots", [])):
        unverified.append("occlusion")
    if not request.get("motion_limits"):
        unverified.append("camera_motion_limits")
    if any(item["code"] in {"TIME_BUDGET_REACHED", "SAMPLE_LIMIT_REACHED", "ANCHOR_LIMIT_REACHED"} for item in warnings):
        unverified.append("requested_sampling_coverage")
    if any(item["code"] in {"MISSING_COLLISION_PROXY", "INVALID_COLLISION_PROXY_TYPE", "UNKNOWN_COLLISION_PROXY_BOUNDS"} for item in warnings):
        unverified.append("proxy_collision")
    if any(item["code"] == "INVALID_MOTION_LIMIT" for item in warnings):
        unverified.append("camera_motion_limits")
    return {
        "schema_version": "1.0",
        "inspection": "incremental_previs_data_validation",
        "mode": request.get("mode", "fast"),
        "revision_id": request.get("revision_id"),
        "scene": scene.name,
        "status": "error" if errors else "needs_review" if warnings else "sampled_checks_passed",
        "planned_sample_frames": frames,
        "sample_frames": completed_frames,
        "sample_count": len(completed_frames),
        "unverified": sorted(set(unverified)),
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "timings": {"validation_wall_ms": round((time.perf_counter() - started) * 1000.0, 3)},
        "limitations": [
            "Collision uses explicitly declared proxy objects and sphere-vs-AABB tests; it is a fast broad-phase check, not mesh-accurate collision.",
            "Screen visibility projects declared subject points; it does not prove semantic composition or full-body visibility unless those points are declared.",
            "Occlusion ray checks are optional and sample only declared points.",
            "The script does not render, measure viewport FPS, inspect limb performance, or replace normal-speed director review.",
        ],
    }


result = _validate()
