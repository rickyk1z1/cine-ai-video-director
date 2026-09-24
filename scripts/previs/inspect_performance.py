"""Read-only Blender performance inventory for an official MCP code tool.

Execute this file's text in Blender; consume the top-level ``result`` dictionary.
No operators, frame changes, file writes, mesh conversion or data edits are used.
Evaluation can still cost time. Counts describe the current dependency graph,
not playback FPS or a promise of render/viewport performance.
"""

import math
import time

import bpy
from mathutils import Vector


MAX_INSTANCE_RECORDS = 250_000
MAX_SCAN_SECONDS = 12.0
MAX_GROUP_VISITS = 2_048
MAX_GROUP_NODES = 100_000
MAX_GROUP_DEPTH = 32
MAX_REALIZE_PATHS = 256


def _nominal_triangles(mesh):
    # An n-gon nominally triangulates to n - 2 triangles. This does not force
    # tessellation and does not assert that degenerate polygons render fully.
    return max(0, len(mesh.loops) - 2 * len(mesh.polygons))


def _local_corners(obj):
    try:
        values = tuple(tuple(float(v) for v in corner) for corner in obj.bound_box)
        if len(values) != 8 or all(corner == (-1.0, -1.0, -1.0) for corner in values):
            return None
        if not all(math.isfinite(v) for corner in values for v in corner):
            return None
        return tuple(Vector(corner) for corner in values)
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        return None


def _frustum(scene, depsgraph):
    camera = scene.camera
    if camera is None:
        return None, {"status": "unavailable", "reason": "no_active_scene_camera"}
    details = {"name": camera.name, "type": camera.data.type}
    if camera.data.type not in {"PERSP", "ORTHO"}:
        details.update(status="unsupported", reason="panoramic_or_custom_camera")
        return None, details
    try:
        camera_eval = camera.evaluated_get(depsgraph)
        render = scene.render
        # Resolution percentage does not change aspect ratio or the frustum.
        projection = camera_eval.calc_matrix_camera(
            depsgraph,
            x=max(1, render.resolution_x),
            y=max(1, render.resolution_y),
            scale_x=render.pixel_aspect_x,
            scale_y=render.pixel_aspect_y,
        )
        # Camera object scaling is not a lens zoom in Blender.
        clip_from_world = projection @ camera_eval.matrix_world.normalized().inverted()
        rows = [Vector(tuple(row)) for row in clip_from_world]
        planes = []
        for axis in range(3):
            for sign in (1.0, -1.0):
                plane = rows[3] + sign * rows[axis]
                normal_length = Vector(plane[:3]).length
                if normal_length <= 1e-12:
                    raise ValueError("degenerate_camera_frustum")
                planes.append((Vector(plane[:3]) / normal_length, plane[3] / normal_length))
        details.update(
            status="estimated",
            method="perspective_or_orthographic_six_planes_against_world_bounding_sphere",
            clip_start=camera.data.clip_start,
            clip_end=camera.data.clip_end,
            render_border_ignored=True,
        )
        return planes, details
    except (AttributeError, ReferenceError, RuntimeError, ValueError, ZeroDivisionError) as exc:
        details.update(status="unavailable", reason=str(exc))
        return None, details


def _sphere_intersects(corners, matrix_world, planes):
    if corners is None:
        return True  # Unknown bounds must not cause a false cull.
    world = [matrix_world @ corner for corner in corners]
    center = sum(world, Vector((0.0, 0.0, 0.0))) / 8.0
    radius = max((corner - center).length for corner in world)
    if not math.isfinite(radius) or not all(math.isfinite(v) for v in center):
        return True
    return all(normal.dot(center) + distance >= -radius - 1e-5 for normal, distance in planes)


def _realize_inventory(objects):
    findings = []
    cycles = []
    visits = 0
    nodes_seen = 0
    truncated = False
    for obj in objects:
        for modifier in obj.modifiers:
            if modifier.type != "NODES" or modifier.node_group is None:
                continue
            root_path = [obj.name, modifier.name, modifier.node_group.name]
            stack = [(modifier.node_group, root_path, frozenset(), 0)]
            while stack:
                group, path, ancestors, depth = stack.pop()
                pointer = group.as_pointer()
                if pointer in ancestors:
                    if len(cycles) < 16:
                        cycles.append(path)
                    continue
                if visits >= MAX_GROUP_VISITS or nodes_seen >= MAX_GROUP_NODES or depth > MAX_GROUP_DEPTH:
                    truncated = True
                    stack.clear()
                    break
                visits += 1
                lineage = ancestors | {pointer}
                for node in group.nodes:
                    nodes_seen += 1
                    if nodes_seen > MAX_GROUP_NODES:
                        truncated = True
                        break
                    if node.bl_idname == "GeometryNodeRealizeInstances":
                        if len(findings) < MAX_REALIZE_PATHS:
                            findings.append({
                                "object": obj.name,
                                "modifier": modifier.name,
                                "path": path + [node.name],
                                "node_muted": bool(node.mute),
                                "modifier_viewport_enabled": bool(modifier.show_viewport),
                                "modifier_render_enabled": bool(modifier.show_render),
                            })
                        else:
                            truncated = True
                    child = getattr(node, "node_tree", None)
                    if node.type == "GROUP" and child is not None:
                        stack.append((child, path + [node.name, child.name], lineage, depth + 1))
                if nodes_seen >= MAX_GROUP_NODES:
                    stack.clear()
            if visits >= MAX_GROUP_VISITS or nodes_seen >= MAX_GROUP_NODES:
                break
        if visits >= MAX_GROUP_VISITS or nodes_seen >= MAX_GROUP_NODES:
            break
    return {
        "scope": "geometry_nodes_modifiers_on_current_view_layer_base_objects",
        "paths": findings,
        "cycles_skipped": cycles,
        "groups_visited_including_repeated_paths": visits,
        "nodes_visited_including_repeated_paths": nodes_seen,
        "truncated": truncated,
        "interpretation": "Node presence is a review flag; muted or disconnected branches may not execute.",
    }


def _viewport_inventory():
    viewports = []
    manager = bpy.context.window_manager
    for window_index, window in enumerate(manager.windows if manager else []):
        if window.screen is None:
            continue
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            region_3d = getattr(space, "region_3d", None)
            viewports.append({
                "window_index": window_index,
                "scene": window.scene.name,
                "view_layer": window.view_layer.name,
                "width_px": region.width if region else area.width,
                "height_px": region.height if region else area.height,
                "shading": space.shading.type,
                "view_perspective": region_3d.view_perspective if region_3d else None,
                "overlays": bool(space.overlay.show_overlays),
                "local_view": space.local_view is not None,
            })
    return viewports


def _inspect():
    started = time.perf_counter()
    scene = bpy.context.scene
    view_layer = bpy.context.view_layer
    base_objects = list(view_layer.objects)
    issues = []
    source_meshes = {}
    visible_base_count = 0
    for obj in base_objects:
        try:
            visible_base_count += int(obj.visible_get(view_layer=view_layer))
        except (RuntimeError, TypeError):
            issues.append("visible_get_failed:" + obj.name)
        if obj.type == "MESH" and obj.data is not None:
            source_meshes.setdefault(obj.data.as_pointer(), obj.data)

    gn = _realize_inventory(base_objects)
    acquire_start = time.perf_counter()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph_acquire_ms = (time.perf_counter() - acquire_start) * 1000.0
    planes, camera = _frustum(scene, depsgraph)
    cache = {}
    instance_count = 0
    base_record_count = 0
    record_count = 0
    mesh_record_count = 0
    non_mesh_records = {}
    all_triangles = 0
    in_frustum_triangles = 0
    in_frustum_mesh_records = 0
    unavailable_bounds = 0
    complete = True
    stopped_reason = None
    scan_started = time.perf_counter()
    for item in depsgraph.object_instances:
        if record_count >= MAX_INSTANCE_RECORDS:
            complete, stopped_reason = False, "instance_record_limit"
            break
        if record_count % 256 == 0 and time.perf_counter() - scan_started >= MAX_SCAN_SECONDS:
            complete, stopped_reason = False, "instance_scan_time_limit"
            break
        record_count += 1
        is_instance = bool(item.is_instance)
        instance_count += int(is_instance)
        base_record_count += int(not is_instance)
        # Never filter instances by the hidden state of their source object.
        evaluated_object = item.object
        if evaluated_object.type != "MESH" or evaluated_object.data is None:
            non_mesh_records[evaluated_object.type] = non_mesh_records.get(evaluated_object.type, 0) + 1
            continue
        mesh_record_count += 1
        mesh = evaluated_object.data
        pointer = mesh.as_pointer()
        if pointer not in cache:
            cache[pointer] = {
                "triangles": _nominal_triangles(mesh),
                "corners": _local_corners(evaluated_object),
                "mesh": mesh.name,
                "object_example": evaluated_object.name,
                "record_count": 0,
            }
        cached = cache[pointer]
        cached["record_count"] += 1
        triangles = cached["triangles"]
        all_triangles += triangles
        if cached["corners"] is None:
            unavailable_bounds += 1
        if planes is not None and _sphere_intersects(cached["corners"], item.matrix_world, planes):
            in_frustum_triangles += triangles
            in_frustum_mesh_records += 1
    scan_ms = (time.perf_counter() - scan_started) * 1000.0
    if not complete:
        issues.append("INCOMPLETE_INSTANCE_SCAN:" + stopped_reason)
    if gn["truncated"]:
        issues.append("INCOMPLETE_GEOMETRY_NODES_SCAN")

    largest = sorted(cache.values(), key=lambda entry: entry["triangles"] * entry["record_count"], reverse=True)[:12]
    fps_base = float(scene.render.fps_base)
    return {
        "schema_version": "1.1",
        "inspection": "read_only_current_frame",
        "blender_version": bpy.app.version_string,
        "scene": scene.name,
        "view_layer": view_layer.name,
        "frame": scene.frame_current,
        "engine": scene.render.engine,
        "timeline_fps": scene.render.fps / fps_base if fps_base else None,
        "render_resolution": {
            "width": scene.render.resolution_x,
            "height": scene.render.resolution_y,
            "percentage": scene.render.resolution_percentage,
        },
        "counts": {
            "bpy_data_objects_all_scenes": len(bpy.data.objects),
            "view_layer_base_objects": len(base_objects),
            "view_layer_visible_base_objects": visible_base_count,
            "view_layer_unique_source_meshes": len(source_meshes),
            "view_layer_unique_source_nominal_triangles": sum(_nominal_triangles(mesh) for mesh in source_meshes.values()),
            "depsgraph_records_scanned": record_count,
            "depsgraph_base_records_scanned": base_record_count,
            "logical_instance_records_scanned": instance_count,
            "mesh_records_scanned": mesh_record_count,
            "non_mesh_records_scanned_by_type": non_mesh_records,
            "evaluated_unique_meshes_scanned": len(cache),
            "evaluated_unique_nominal_triangles_scanned": sum(entry["triangles"] for entry in cache.values()),
        },
        "geometry_estimates": {
            "status": "estimated" if complete else "partial_not_an_upper_bound",
            "mesh_only": True,
            "instance_scan_complete": complete,
            "stopped_reason": stopped_reason,
            "expanded_evaluated_mesh_triangles_scanned": all_triangles,
            "expanded_evaluated_mesh_triangle_upper_bound": all_triangles if complete else None,
            "camera_mesh_triangle_upper_bound": in_frustum_triangles if complete and planes is not None else None,
            "camera_mesh_triangles_scanned": in_frustum_triangles if planes is not None else None,
            "camera_mesh_records_scanned": in_frustum_mesh_records if planes is not None else None,
            "mesh_records_with_unknown_bounds": unavailable_bounds,
            "camera": camera,
            "largest_evaluated_mesh_contributors": [
                {"mesh": entry["mesh"], "object_example": entry["object_example"],
                 "source_nominal_triangles": entry["triangles"], "evaluated_records": entry["record_count"],
                 "expanded_nominal_triangles_scanned": entry["triangles"] * entry["record_count"]}
                for entry in largest
            ],
        },
        "geometry_nodes": gn,
        "viewports": _viewport_inventory(),
        "timings": {
            "depsgraph_acquire_wall_ms": round(depsgraph_acquire_ms, 3),
            "instance_inspection_wall_ms": round(scan_ms, 3),
            "inspection_wall_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "viewport_fps": None,
            "viewport_smoothness": "unverified",
        },
        "limits": {
            "max_instance_records": MAX_INSTANCE_RECORDS,
            "max_instance_scan_seconds": MAX_SCAN_SECONDS,
            "max_group_visits": MAX_GROUP_VISITS,
            "max_group_nodes": MAX_GROUP_NODES,
        },
        "issues": issues,
        "limitations": [
            "Only the current viewport dependency graph and current frame are inspected; render-time settings can differ.",
            "Triangle counts use polygon-loop n-2 estimates without mesh conversion or forced tessellation.",
            "Expanded sums count each dependency-graph mesh record and may conservatively include hidden emitters or duplicates.",
            "Bounding spheres conservatively test the active scene camera; no exact clipping, occlusion, alpha coverage, shadows or reflections are measured.",
            "Hair, curves, volumes, particles and other non-mesh geometry costs are unquantified; see non_mesh_records_scanned_by_type.",
            "A missing/unsupported camera leaves camera bounds null; total evaluated mesh estimates remain useful.",
            "No frame is advanced, no playback is timed, no VRAM is sampled and no viewport FPS is inferred.",
            "Dependency-graph acquisition may evaluate pending changes and take time; it does not change authored scene data.",
            "The instance scan has count/time guards; interrupted sums are partial, never complete upper bounds.",
            "Viewport local view and per-area visibility can differ from this view-layer inventory.",
        ],
    }


result = _inspect()
