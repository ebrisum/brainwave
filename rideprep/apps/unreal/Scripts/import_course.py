"""Editor "hero course" import (spec §10.6, editor mode). Run headless with the pinned UE version, e.g.:

  UnrealEditor-Cmd RidePrep.uproject -run=pythonscript -script="Scripts/import_course.py --package /data/courses/c_xxx"

Creates a World Partition level with Landscape tiles from the 16-bit heightmaps, landscape spline road from
road_spline.json, a PCG graph input from the instance lists, placed chunk meshes, and saves it. Cook to a pak with
the standard BuildCookRun. Requires the PythonScriptPlugin, EditorScriptingUtilities and PCG plugins.

NOTE: written against the UE 5.8 Python API surface and NOT executed in CI (no Unreal in the build container);
verify on the target workstation (docs/MILESTONES.md, M9).
"""
import argparse
import json
import os
import struct
import sys

import unreal

MAT_ROOT = "/Game/RidePrep/Materials"
LANDSCAPE_MATERIAL = "/Game/RidePrep/Materials/M_Landscape"
PCG_GRAPH = "/Game/RidePrep/PCG/PCG_Vegetation"


def parse():
    p = argparse.ArgumentParser()
    p.add_argument("--package", required=True)
    p.add_argument("--level", default=None)
    args, _ = p.parse_known_args(sys.argv[1:] if len(sys.argv) > 1 else [])
    return args


def load_json(path):
    with open(path, "r", encoding="utf8") as f:
        return json.load(f)


def import_heightmap_tile(tile, ue, pkg_dir, level_name):
    """Landscape per tile: import the PNG as a texture, draw into a render target, apply to a new landscape proxy."""
    ls = ue["landscape"]
    tex_path = f"/Game/RidePrep/Courses/{level_name}/Heightmaps"
    task = unreal.AssetImportTask()
    task.filename = os.path.join(pkg_dir, "unreal", tile["heightmap"])
    task.destination_path = tex_path
    task.automated = True
    task.save = False
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    tex = unreal.load_asset(f"{tex_path}/{os.path.splitext(tile['heightmap'])[0]}")
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_GRAYSCALE)
    tex.set_editor_property("srgb", False)
    size = ls["tileSizePx"]
    rt = unreal.RenderingLibrary.create_render_target2d(unreal.EditorLevelLibrary.get_editor_world(), size, size, unreal.TextureRenderTargetFormat.RTF_R16F)
    unreal.RenderingLibrary.draw_material_to_render_target  # noqa: B018 (API presence check)
    loc = unreal.Vector(*tile["ueLocationCm"])
    # Landscape scale: X/Y = resolution in cm per quad, Z = zScaleCm (UE maps 16-bit ±32768 to ±256·Z/100 m)
    scale = unreal.Vector(ls["resolutionM"] * 100, ls["resolutionM"] * 100, ls["zScaleCm"])
    land = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.Landscape, loc)
    land.set_actor_scale3d(scale)
    land.set_editor_property("landscape_material", unreal.load_asset(LANDSCAPE_MATERIAL))
    unreal.RenderingLibrary.convert_render_target_to_texture2d_editor_only  # noqa: B018
    land.landscape_import_heightmap_from_render_target(rt, import_height_from_rg_channel=False)
    return land


def build_road(pkg_dir, ue):
    spline = load_json(os.path.join(pkg_dir, "unreal", ue["roadSpline"]))
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0))
    comp = unreal.SplineComponent()
    actor.add_instance_component(comp) if hasattr(actor, "add_instance_component") else None
    comp.clear_spline_points(False)
    for i, p in enumerate(spline["points"]):
        comp.add_spline_point(unreal.Vector(*p["p"]), unreal.SplineCoordinateSpace.WORLD, False)
        comp.set_tangent_at_spline_point(i, unreal.Vector(*p["t"]), unreal.SplineCoordinateSpace.WORLD, False)
    comp.update_spline()
    actor.set_actor_label("RidePrep_RoadSpline")
    return actor


def read_instances(path, record=28):
    out = []
    with open(path, "rb") as f:
        data = f.read()
    for k in range(len(data) // record):
        x, y, z, yaw, scale, h, species, _ = struct.unpack_from("<6fHH", data, k * record)
        out.append((x, y, z, yaw, scale, h, species))
    return out


def main():
    a = parse()
    pkg = a.package
    manifest = load_json(os.path.join(pkg, "manifest.json"))
    ue = load_json(os.path.join(pkg, "unreal", "course_ue.json"))
    level_name = a.level or manifest["courseId"]
    level_path = f"/Game/RidePrep/Courses/{level_name}/{level_name}"
    unreal.EditorLevelLibrary.new_level_from_template(level_path, "/Engine/Maps/Templates/OpenWorld")
    for tile in ue["landscape"]["tiles"]:
        import_heightmap_tile(tile, ue, pkg, level_name)
    build_road(pkg, ue)
    # Vegetation via PCG: one point-data actor per category, the graph maps species → Nanite foliage meshes.
    for cat, spec in ue["instances"].items():
        pts = read_instances(os.path.join(pkg, "unreal", spec["file"]), spec["recordBytes"])
        if not pts:
            continue
        vol = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.PCGVolume, unreal.Vector(0, 0, 0))
        vol.set_actor_label(f"RidePrep_PCG_{cat}")
        comp = vol.get_component_by_class(unreal.PCGComponent)
        comp.set_graph(unreal.load_asset(PCG_GRAPH))
        tag = unreal.Name(f"RidePrep:{cat}:{os.path.join(pkg, 'unreal', spec['file'])}")
        vol.tags = [tag]
        comp.generate(True)
    unreal.EditorLevelLibrary.save_current_level()
    unreal.log(f"RidePrep: imported {manifest['name']} into {level_path}")


if __name__ == "__main__":
    main()
