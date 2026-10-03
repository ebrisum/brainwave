"""Game-art "hero level" import (hybrid pipeline): gpx2course game package → World Partition level.

  UnrealEditor-Cmd RidePrep.uproject -run=pythonscript \
      -script="Scripts/import_game_level.py --package /data/courses/c_xxx [--overrides Config/RidePrepAssetOverrides.json]"

What it builds (all from <package>/game/index.json, written by `gpx2course game`):
  1. Kit: master materials M_RidePrepKit / M_RidePrepKit_Masked (created once), textures, one material instance per
     kit material id (UV scale = 1/tileM, roughness, tint) with a PhysMat per surface class, kit meshes with
     `<asset>__lod1` merged in as LOD1.
  2. Level: new World Partition level (OpenWorld template; its landscape is removed — terrain comes with the chunks).
  3. Chunks: g<id>.glb (uncompressed copies in game/unreal/) → static meshes with the kit material instances,
     complex-as-simple collision on terrain/roads/buildings, none on markings, Nanite on opaque meshes (`--no-nanite`:
     regular full-detail meshes, for GPUs without DirectX 12 SM6); one actor per mesh at the chunk origin
     (ENU → UE: X = E·100, Y = −N·100, Z = U·100), so World Partition streams them by cell.
  4. Instances: one ARidePrepInstanceActor per chunk with HISM per kit asset (without the C++ plugin — the Blueprint-only
     render project — a static mesh actor with HISM components added through the SubobjectDataSubsystem);
     `--overrides` maps kit asset ids to high-quality project assets (e.g. scanned Pinus pinea, cypress, olive) with
     optional yaw offset/scale.
  5. PCG: a PCG volume per chunk with the land-use mask (game/landuse/g<id>.png) as graph parameter for dense ground
     detail (grass, flowers, stones, shoulder gravel) — graph authored once in the project (see README).
  6. Sun: directional light set for the event start (manifest eventStart, NOAA solar position).
  7. Hero road (chunks built with `gpx2course game --hero`): h<id>.glb replaces the chunk's road/markings/defects/
     shoulder meshes with the dense Nanite carriageway (real potholes, cracks, patches, crumbled edges) and stone-relief
     gravel shoulders, whose Nanite fallback keeps every triangle (complex collision and renderers without Nanite get
     the real pothole floor); loose pebbles become HISM instances (culled at 60 m).
  8. Road-edge blending: one Runtime Virtual Texture over the corridor; roads, shoulders and verges draw into it and
     the terrain master material blends toward it with the RoadMask vertex colour (1 at the verge → 0 four metres
     out), so the road never looks like a sticker. Without RVT support the same mask blends toward the gravel layer.
  9. Road splines: an ARidePrepRoadSpline per chunk along the course road (tag "RidePrepRoad") for PCG graphs
     (exclusion zones, sampling along the edge).
 10. Rider: rider_road/rider_tt GLBs (tools/rider) → skeletal meshes + pedal/stand/coast clips (and *_rolling variants
     with turning wheels for Sequencer) in /Game/RidePrep/Rider; ARidePrepRider picks them up by path.
 11. Camera rails (`--rails auto|none|km:a-b,…`): Camera Rig Rails along the riding line (keep right, on the
     crowned/banked surface) at the start, every climb and every hero stretch — attach the rider and cameras in
     Sequencer and key "Current Position on Rail".

For the hand-off render project (tools/unreal_bundle.py) run Scripts/build_level.py instead: it finds Course/ and Rider/
in the project folder and calls this script.

Physical materials follow the brief: asphalt friction 0.8, gravel 0.4 (dust and rumble come from the surface type).

NOTE: written against the UE 5.5–5.8 Python API and NOT executed here (no Unreal in the build container). Each step
logs and continues on API differences; verify once on the target workstation.
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone

import unreal

ROOT = "/Game/RidePrep"
KIT_ROOT = f"{ROOT}/Kits"
PCG_GRAPH = f"{ROOT}/PCG/PCG_GroundDetail"
OPEN_WORLD_TEMPLATE = "/Engine/Maps/Templates/OpenWorld"
WHITE = "/Engine/EngineResources/WhiteSquareTexture"
FLAT_NORMAL = "/Engine/EngineMaterials/DefaultNormal"

# Kit material id → surface class (PhysMat). Friction is for contact feel/FX; speed comes from the physics model.
SURFACE = {
    "asphalt": "Asphalt", "asphalt_worn": "Asphalt", "marking_white": "Asphalt", "kerb": "Asphalt", "paving_porphyry": "Setts",
    "asphalt_patch": "Asphalt", "tar_seal": "Asphalt", "pothole": "Gravel", "stone": "Gravel", "shoulder_gravel": "Gravel",
    "gravel": "Gravel", "roof_flat": "Gravel", "grass_dry": "Grass", "grass_green": "Grass", "orchard_grass": "Grass", "wetland": "Grass",
    "stubble": "Soil", "soil_ploughed": "Soil", "vineyard_soil": "Soil", "forest_floor": "Soil", "urban_ground": "Soil", "sand": "Soil",
    "salt": "Soil", "crop_green": "Grass", "water": "Water", "saltpan_water": "Water", "metal_galvanised": "Metal", "plastic_barrier": "Metal",
}
PHYSMATS = {"Asphalt": (0.8, 1), "Setts": (0.7, 2), "Gravel": (0.4, 3), "Grass": (0.35, 4), "Soil": (0.45, 5), "Water": (0.1, 6), "Metal": (0.5, 7)}
RVT_DRAW_KINDS = ("road", "shoulder", "verge", "sideroads", "hero")  # meshes that write the roadside into the RVT
SOLID_ASSETS = ("guardrail", "race_barrier", "streetlight", "sign", "town_sign", "km_marker", "delineator", "campanile")
CULL_CM = {"vine_row_5m": 45000, "reeds": 25000, "flamingo": 30000, "delineator": 30000, "race_barrier_2m": 40000, "hedge_4m": 60000}

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary


def log(msg):
    unreal.log(f"[RidePrep] {msg}")


def warn(msg):
    unreal.log_warning(f"[RidePrep] {msg}")


def parse():
    p = argparse.ArgumentParser()
    p.add_argument("--package", required=True)
    p.add_argument("--level", default=None)
    p.add_argument("--overrides", default=None, help="JSON: {asset: {mesh: '/Game/..', yawDeg: 0, scale: 1}}")
    p.add_argument("--chunks", default=None, help="comma list of chunk ids (quick iteration)")
    p.add_argument("--no-pcg", action="store_true")
    p.add_argument("--no-hero", action="store_true", help="ignore hero road meshes even if the package has them")
    p.add_argument("--no-rvt", action="store_true")
    p.add_argument("--no-nanite", action="store_true", help="regular meshes only — for GPUs without DirectX 12 SM6, which "
                                                             "would draw the simplified Nanite fallback instead")
    p.add_argument("--rider-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "client", "public", "models"))
    p.add_argument("--rails", default="auto", help="camera rails along the riding line: 'auto' (start, climbs, hero stretches), 'none', "
                                                   "or route km ranges 'km:44-46.5,0-2'")
    a, _ = p.parse_known_args(sys.argv[1:])
    return a


def load_json(path):
    with open(path, "r", encoding="utf8") as f:
        return json.load(f)


# ---- import helpers ---------------------------------------------------------------------------------------------------


def import_files(files, dest, replace=True):
    tasks = []
    for f in files:
        t = unreal.AssetImportTask()
        t.filename = f
        t.destination_path = dest
        t.automated = True
        t.replace_existing = replace
        t.save = False
        tasks.append(t)
    asset_tools.import_asset_tasks(tasks)
    out = []
    for t in tasks:
        out += [unreal.load_asset(p) for p in t.get_editor_property("imported_object_paths")]
    return [o for o in out if o]


def ensure_dir(path):
    if not eal.does_directory_exist(path):
        eal.make_directory(path)


def create(name, path, cls, factory):
    full = f"{path}/{name}"
    if eal.does_asset_exist(full):
        return unreal.load_asset(full)
    return asset_tools.create_asset(name, path, cls, factory)


# ---- kit --------------------------------------------------------------------------------------------------------------


def master_material(name, masked, rvt_out=False):
    """BaseColor(tex)·Tint, Normal(tex), Roughness, Metallic; UV = TexCoord0 · UVScale (UVs are metres → 1/tileM).
    rvt_out: also write BaseColor/Roughness/world Normal to a Runtime Virtual Texture (only for primitives that draw
    into one — the roadside meshes)."""
    path = f"{ROOT}/Materials"
    ensure_dir(path)
    full = f"{path}/{name}"
    if eal.does_asset_exist(full):
        return unreal.load_asset(full)
    m = asset_tools.create_asset(name, path, unreal.Material, unreal.MaterialFactoryNew())
    if masked:
        m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
        m.set_editor_property("two_sided", True)
        m.set_editor_property("opacity_mask_clip_value", 0.4)
    tc = mel.create_material_expression(m, unreal.MaterialExpressionTextureCoordinate, -900, 0)
    uvs = mel.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -900, 150)
    uvs.set_editor_property("parameter_name", "UVScale")
    uvs.set_editor_property("default_value", unreal.LinearColor(1, 1, 0, 0))
    mask = mel.create_material_expression(m, unreal.MaterialExpressionComponentMask, -700, 150)
    mask.set_editor_property("r", True)
    mask.set_editor_property("g", True)
    mel.connect_material_expressions(uvs, "", mask, "")
    mul = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -550, 50)
    mel.connect_material_expressions(tc, "", mul, "A")
    mel.connect_material_expressions(mask, "", mul, "B")
    base = mel.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -350, -100)
    base.set_editor_property("parameter_name", "BaseColor")
    base.set_editor_property("texture", unreal.load_asset(WHITE))
    mel.connect_material_expressions(mul, "", base, "UVs")
    tint = mel.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -350, -250)
    tint.set_editor_property("parameter_name", "Tint")
    tint.set_editor_property("default_value", unreal.LinearColor(1, 1, 1, 1))
    bm = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -100, -150)
    mel.connect_material_expressions(base, "RGB", bm, "A")
    mel.connect_material_expressions(tint, "", bm, "B")
    mel.connect_material_property(bm, "", unreal.MaterialProperty.MP_BASE_COLOR)
    nrm = mel.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -350, 150)
    nrm.set_editor_property("parameter_name", "Normal")
    nrm.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    nrm.set_editor_property("texture", unreal.load_asset(FLAT_NORMAL))
    mel.connect_material_expressions(mul, "", nrm, "UVs")
    mel.connect_material_property(nrm, "RGB", unreal.MaterialProperty.MP_NORMAL)
    params = {}
    for i, (pname, default, prop) in enumerate((("Roughness", 0.9, unreal.MaterialProperty.MP_ROUGHNESS),
                                                ("Metallic", 0.0, unreal.MaterialProperty.MP_METALLIC))):
        s = mel.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -100, 250 + 120 * i)
        s.set_editor_property("parameter_name", pname)
        s.set_editor_property("default_value", default)
        mel.connect_material_property(s, "", prop)
        params[pname] = s
    if masked:
        mel.connect_material_property(base, "A", unreal.MaterialProperty.MP_OPACITY_MASK)
    if rvt_out:
        try:
            out = mel.create_material_expression(m, unreal.MaterialExpressionRuntimeVirtualTextureOutput, 300, 300)
            wn = _tangent_to_world(m, nrm, 100, 450)
            mel.connect_material_expressions(bm, "", out, "BaseColor")
            mel.connect_material_expressions(params["Roughness"], "", out, "Roughness")
            mel.connect_material_expressions(wn, "", out, "Normal")
        except Exception as ex:  # noqa: BLE001
            warn(f"RVT output on {name}: {ex}")
    mel.recompile_material(m)
    return m


def _tangent_to_world(m, src, x, y):
    t = mel.create_material_expression(m, unreal.MaterialExpressionTransform, x, y)
    t.set_editor_property("transform_source_type", unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_TANGENT)
    t.set_editor_property("transform_type", unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    mel.connect_material_expressions(src, "RGB", t, "")
    return t


def terrain_material(rvt, blend_albedo, blend_normal):
    """M_RidePrepKit_Terrain: the kit master plus road-edge blending. RoadMask (vertex colour R, baked by the chunk bake:
    1 at the verge → 0 four metres out) broken up with world-space noise lerps the terrain toward what the roadside
    drew into the RVT (or toward the gravel layer without RVT). Normals are blended in world space."""
    path = f"{ROOT}/Materials"
    full = f"{path}/M_RidePrepKit_Terrain"
    if eal.does_asset_exist(full):
        return unreal.load_asset(full)
    m = asset_tools.create_asset("M_RidePrepKit_Terrain", path, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("tangent_space_normal", False)
    tc = mel.create_material_expression(m, unreal.MaterialExpressionTextureCoordinate, -1300, 0)
    uvs = mel.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -1300, 150)
    uvs.set_editor_property("parameter_name", "UVScale")
    uvs.set_editor_property("default_value", unreal.LinearColor(1, 1, 0, 0))
    mask2 = mel.create_material_expression(m, unreal.MaterialExpressionComponentMask, -1100, 150)
    mask2.set_editor_property("r", True)
    mask2.set_editor_property("g", True)
    mel.connect_material_expressions(uvs, "", mask2, "")
    uv = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -950, 50)
    mel.connect_material_expressions(tc, "", uv, "A")
    mel.connect_material_expressions(mask2, "", uv, "B")
    base = mel.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -750, -200)
    base.set_editor_property("parameter_name", "BaseColor")
    base.set_editor_property("texture", unreal.load_asset(WHITE))
    mel.connect_material_expressions(uv, "", base, "UVs")
    tint = mel.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -750, -350)
    tint.set_editor_property("parameter_name", "Tint")
    tint.set_editor_property("default_value", unreal.LinearColor(1, 1, 1, 1))
    col = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -500, -250)
    mel.connect_material_expressions(base, "RGB", col, "A")
    mel.connect_material_expressions(tint, "", col, "B")
    nrm = mel.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -750, 100)
    nrm.set_editor_property("parameter_name", "Normal")
    nrm.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    nrm.set_editor_property("texture", unreal.load_asset(FLAT_NORMAL))
    mel.connect_material_expressions(uv, "", nrm, "UVs")
    wn = _tangent_to_world(m, nrm, -500, 100)
    rough = mel.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -500, 300)
    rough.set_editor_property("parameter_name", "Roughness")
    rough.set_editor_property("default_value", 0.9)
    # Blend weight: RoadMask with a ragged, world-space-noise edge
    vc = mel.create_material_expression(m, unreal.MaterialExpressionVertexColor, -900, 500)
    noise = mel.create_material_expression(m, unreal.MaterialExpressionNoise, -900, 650)
    noise.set_editor_property("scale", 0.6)
    noise.set_editor_property("output_min", 0.0)
    noise.set_editor_property("output_max", 1.0)
    strength = mel.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -900, 800)
    strength.set_editor_property("parameter_name", "RoadBlend")
    strength.set_editor_property("default_value", 1.0)
    k1 = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -700, 550)
    mel.connect_material_expressions(vc, "R", k1, "A")
    mel.connect_material_expressions(noise, "", k1, "B")
    k2 = mel.create_material_expression(m, unreal.MaterialExpressionAdd, -550, 550)
    mel.connect_material_expressions(k1, "", k2, "A")
    mel.connect_material_expressions(vc, "R", k2, "B")
    k3 = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -420, 550)
    mel.connect_material_expressions(k2, "", k3, "A")
    mel.connect_material_expressions(strength, "", k3, "B")
    w = mel.create_material_expression(m, unreal.MaterialExpressionSaturate, -300, 550)
    mel.connect_material_expressions(k3, "", w, "")
    # Blend source: the RVT (what the roadside drew) or the gravel layer
    if rvt is not None:
        src = mel.create_material_expression(m, unreal.MaterialExpressionRuntimeVirtualTextureSampleParameter, -500, 800)
        src.set_editor_property("parameter_name", "RoadRVT")
        src.set_editor_property("virtual_texture", rvt)
        _set_enum(src, "material_type", unreal.RuntimeVirtualTextureMaterialType, ("BASE_COLOR_NORMAL_ROUGHNESS", "BASE_COLOR_NORMAL_SPECULAR"))
        b_col, b_col_pin, b_nrm, b_nrm_pin, b_rough, b_rough_pin = src, "BaseColor", src, "Normal", src, "Roughness"
    else:
        bt = mel.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -750, 800)
        bt.set_editor_property("parameter_name", "BlendBaseColor")
        bt.set_editor_property("texture", blend_albedo or unreal.load_asset(WHITE))
        mel.connect_material_expressions(uv, "", bt, "UVs")
        bn = mel.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -750, 1000)
        bn.set_editor_property("parameter_name", "BlendNormal")
        bn.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        bn.set_editor_property("texture", blend_normal or unreal.load_asset(FLAT_NORMAL))
        mel.connect_material_expressions(uv, "", bn, "UVs")
        br = mel.create_material_expression(m, unreal.MaterialExpressionConstant, -500, 1100)
        br.set_editor_property("r", 0.95)
        b_col, b_col_pin, b_nrm, b_nrm_pin, b_rough, b_rough_pin = bt, "RGB", _tangent_to_world(m, bn, -500, 1000), "", br, ""
    for i, (a_, a_pin, b_, b_pin, prop) in enumerate(((col, "", b_col, b_col_pin, unreal.MaterialProperty.MP_BASE_COLOR),
                                                      (rough, "", b_rough, b_rough_pin, unreal.MaterialProperty.MP_ROUGHNESS),
                                                      (wn, "", b_nrm, b_nrm_pin, unreal.MaterialProperty.MP_NORMAL))):
        lerp = mel.create_material_expression(m, unreal.MaterialExpressionLinearInterpolate, -100, -200 + 250 * i)
        mel.connect_material_expressions(a_, a_pin, lerp, "A")
        mel.connect_material_expressions(b_, b_pin, lerp, "B")
        mel.connect_material_expressions(w, "", lerp, "Alpha")
        mel.connect_material_property(lerp, "", prop)
    met = mel.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -100, 600)
    met.set_editor_property("parameter_name", "Metallic")
    met.set_editor_property("default_value", 0.0)
    mel.connect_material_property(met, "", unreal.MaterialProperty.MP_METALLIC)
    mel.recompile_material(m)
    return m


def _set_enum(obj, prop, enum_cls, names):
    for n in names:
        v = getattr(enum_cls, n, None)
        if v is not None:
            obj.set_editor_property(prop, v)
            return True
    warn(f"{type(obj).__name__}.{prop}: none of {names} in this engine version")
    return False


def setup_rvt(bounds_cm):
    """One RVT over the course corridor (BaseColor/Normal/Roughness, 4096 × 256 px tiles ≈ 3 cm per texel over 30 km,
    adaptive page table) and its volume. The volume's transform maps the unit box onto the bounds."""
    path = f"{ROOT}/RVT"
    ensure_dir(path)
    rvt = create("RVT_RoadBlend", path, unreal.RuntimeVirtualTexture, unreal.RuntimeVirtualTextureFactory())
    _set_enum(rvt, "material_type", unreal.RuntimeVirtualTextureMaterialType, ("BASE_COLOR_NORMAL_ROUGHNESS", "BASE_COLOR_NORMAL_SPECULAR"))
    for prop, val in (("tile_count", 4096), ("tile_size", 256), ("adaptive", True), ("compress_textures", True)):
        try:
            rvt.set_editor_property(prop, val)
        except Exception as ex:  # noqa: BLE001
            warn(f"RVT {prop}: {ex}")
    (x0, y0, z0), (x1, y1, z1) = bounds_cm
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    vol = eas.spawn_actor_from_class(unreal.RuntimeVirtualTextureVolume, unreal.Vector(x0, y0, z0 - 20000))
    vol.set_actor_scale3d(unreal.Vector(x1 - x0, y1 - y0, (z1 - z0) + 40000))
    vol.set_actor_label("RidePrep_RoadBlend_RVT")
    vol.set_folder_path("RidePrep")
    vol.get_editor_property("virtual_texture_component").set_editor_property("virtual_texture", rvt)
    log(f"RVT over {(x1 - x0) / 1e5:.1f} × {(y1 - y0) / 1e5:.1f} km")
    return rvt


def draw_into_rvt(actor, rvt):
    comp = actor.static_mesh_component
    comp.set_editor_property("runtime_virtual_textures", [rvt])
    _set_enum(comp, "virtual_texture_render_pass_type", unreal.RuntimeVirtualTextureMainPassType, ("ALWAYS",))


def physmats():
    path = f"{ROOT}/PhysMats"
    ensure_dir(path)
    out = {}
    for name, (friction, st) in PHYSMATS.items():
        pm = create(f"PM_{name}", path, unreal.PhysicalMaterial, unreal.PhysicalMaterialFactoryNew())
        try:
            pm.set_editor_property("friction", friction)
            pm.set_editor_property("surface_type", getattr(unreal.PhysicalSurface, f"SURFACE_TYPE{st}"))
        except Exception as ex:  # noqa: BLE001
            warn(f"PhysMat {name}: {ex}")
        out[name] = pm
    return out


def hex_to_linear(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def import_kit(pkg, index, rvt=None):
    """Kit textures, master materials, one MI per kit material (+ a road-edge-blending terrain MI for the terrain
    classes), PhysMats, kit meshes. Returns (mis, terrain_mis, meshes)."""
    kit = index["kit"]
    kroot = f"{KIT_ROOT}/{kit['name']}"
    kdir = os.path.join(pkg, kit["dir"])
    mats_doc = load_json(os.path.join(kdir, "materials.json"))["materials"]
    # Textures
    tdir = f"{kroot}/Textures"
    ensure_dir(tdir)
    files = sorted(os.path.join(kdir, "textures", f) for f in os.listdir(os.path.join(kdir, "textures")))
    textures = {}
    for tex in import_files(files, tdir):
        textures[tex.get_name()] = tex
        if tex.get_name().endswith("_normal"):
            tex.set_editor_property("srgb", False)
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
    log(f"kit textures: {len(textures)}")
    opaque, masked = master_material("M_RidePrepKit", False, rvt_out=True), master_material("M_RidePrepKit_Masked", True)
    pms = physmats()
    mdir = f"{kroot}/Materials"
    ensure_dir(mdir)
    gravel = mats_doc.get("gravel", {})
    try:
        terrain_master = terrain_material(rvt, textures.get(os.path.splitext(gravel.get("albedo", ""))[0]),
                                          textures.get(os.path.splitext(gravel.get("normal", ""))[0]))
    except Exception as ex:  # noqa: BLE001
        terrain_master = None
        warn(f"terrain blend material: {ex} — terrain uses the plain kit materials")
    terrain_ids = {m for m in index.get("landuseClasses", []) if m != "none" and "water" not in m}  # water never blends
    mis, terrain_mis = {}, {}
    for mid, spec in mats_doc.items():
        cut = spec.get("alphaCutoff") is not None
        mis[mid] = _kit_mi(f"MI_{mid}", mdir, masked if cut else opaque, mid, spec, textures, pms)
        if terrain_master is not None and mid in terrain_ids and not cut:
            terrain_mis[mid] = _kit_mi(f"MI_{mid}_Terrain", mdir, terrain_master, mid, spec, textures, pms)
    log(f"kit material instances: {len(mis)} (+{len(terrain_mis)} terrain blend)")
    return mis, terrain_mis, _kit_meshes(kdir, kroot, mis)


def _kit_mi(name, mdir, parent, mid, spec, textures, pms):
    mi = create(name, mdir, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mi.set_editor_property("parent", parent)
    alb = textures.get(os.path.splitext(spec.get("albedo", ""))[0]) if spec.get("albedo") else None
    nrm = textures.get(os.path.splitext(spec.get("normal", ""))[0]) if spec.get("normal") else None
    if alb:
        mel.set_material_instance_texture_parameter_value(mi, "BaseColor", alb)
    if nrm:
        mel.set_material_instance_texture_parameter_value(mi, "Normal", nrm)
    tile = spec.get("tileM")
    sx, sy = (tile, tile) if tile and not isinstance(tile, list) else (tile or [1, 1])
    # UVs are metres for tiled materials (repeat = 1/tileM); 0–1 for leaf cards and the sign atlas.
    mel.set_material_instance_vector_parameter_value(mi, "UVScale", unreal.LinearColor(1 / sx if tile else 1, 1 / sy if tile else 1, 0, 0))
    tint = hex_to_linear(spec["color"]) if ("color" in spec and not alb) else [1, 1, 1]
    mel.set_material_instance_vector_parameter_value(mi, "Tint", unreal.LinearColor(*tint, 1))
    mel.set_material_instance_scalar_parameter_value(mi, "Roughness", float(spec.get("roughness", 0.9)))
    mel.set_material_instance_scalar_parameter_value(mi, "Metallic", float(spec.get("metallic", 0.0)))
    surf = SURFACE.get(mid) or ("Asphalt" if mid.startswith("asphalt") else None)
    if surf:
        try:
            mi.set_editor_property("phys_material", pms[surf])
        except Exception as ex:  # noqa: BLE001
            warn(f"phys_material on {mid}: {ex}")
    mel.update_material_instance(mi)
    return mi


def _kit_meshes(kdir, kroot, mis):
    # Meshes (kit.glb via Interchange); one static mesh per asset node, LOD1 from "<asset>__lod1"
    sdir = f"{kroot}/Meshes"
    ensure_dir(sdir)
    imported = [o for o in import_files([os.path.join(kdir, "kit.glb")], sdir) if isinstance(o, unreal.StaticMesh)]
    assets_doc = load_json(os.path.join(kdir, "assets.json"))["assets"]
    by_name = {}
    for sm in imported:
        assign_materials(sm, mis)
        by_name[sm.get_name()] = sm
    meshes = {}
    sme = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    for asset in assets_doc:
        lod0 = _find(by_name, asset)
        lod1 = _find(by_name, asset + "__lod1")
        if not lod0:
            warn(f"kit mesh {asset} not found after import")
            continue
        if lod1 and lod1 is not lod0:
            try:
                sme.set_lod_from_static_mesh(lod0, 1, lod1, 0, True)
            except Exception as ex:  # noqa: BLE001
                warn(f"LOD1 for {asset}: {ex}")
        meshes[asset] = lod0
    log(f"kit meshes: {len(meshes)}")
    return meshes


def _find(by_name, asset):
    """Interchange may prefix/suffix names (SM_, _0): pick the shortest name containing the asset id exactly."""
    cands = [n for n in by_name if n == asset or n.endswith("_" + asset) or n.startswith(asset + "_") or n == "SM_" + asset]
    if not asset.endswith("__lod1"):
        cands = [n for n in cands if "__lod1" not in n]
    return by_name[min(cands, key=len)] if cands else None


def assign_materials(sm, mis):
    for i, slot in enumerate(sm.get_editor_property("static_materials")):
        name = str(slot.get_editor_property("material_slot_name"))
        mid = name[3:] if name.startswith("MI_") else name
        mid = mid.split(".")[0]
        if mid in mis:
            sm.set_material(i, mis[mid])


def configure_chunk_mesh(sm, kind, nanite=True, full_fallback=False):
    """Collision and Nanite. full_fallback (hero road): the Nanite fallback mesh keeps every triangle instead of the
    coarse default — it is what complex collision is cooked from and what renderers without Nanite draw."""
    body = sm.get_editor_property("body_setup")
    if body:
        body.set_editor_property("collision_trace_flag",
                                 unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if kind not in ("markings", "defects") else unreal.CollisionTraceFlag.CTF_USE_DEFAULT)
    if kind not in ("terrain", "buildings", "road", "sideroads", "far", "shoulder", "verge"):
        return
    try:
        ns = sm.get_editor_property("nanite_settings")
        if ns.get_editor_property("enabled") == nanite and not (nanite and full_fallback):
            return  # already right; setting it again would rebuild the mesh
        ns.set_editor_property("enabled", nanite)
        if nanite and full_fallback:
            keep = [("fallback_percent_triangles", 1.0), ("fallback_relative_error", 0.0)]
            if hasattr(unreal, "NaniteFallbackTarget"):  # UE 5.2+: pick which of the two applies
                keep.insert(0, ("fallback_target", unreal.NaniteFallbackTarget.PERCENT_TRIANGLES))
            for prop, value in keep:
                try:
                    ns.set_editor_property(prop, value)
                except Exception as ex:  # noqa: BLE001
                    warn(f"Nanite {prop} on {sm.get_name()}: {ex}")
        sm.set_editor_property("nanite_settings", ns)
    except Exception as ex:  # noqa: BLE001
        warn(f"Nanite on {sm.get_name()}: {ex}")


# ---- level ------------------------------------------------------------------------------------------------------------


def enu_to_ue(e, n, u):
    return unreal.Vector(e * 100.0, -n * 100.0, u * 100.0)


def solar_position(when_utc, lat, lon):
    """NOAA approximation → (elevation°, azimuth° clockwise from north)."""
    doy = when_utc.timetuple().tm_yday
    hour = when_utc.hour + when_utc.minute / 60 + when_utc.second / 3600
    g = 2 * math.pi / 365 * (doy - 1 + (hour - 12) / 24)
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = 0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g) \
        - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g)
    tst = hour * 60 + eqt + 4 * lon
    ha = math.radians(tst / 4 - 180)
    la = math.radians(lat)
    cz = math.sin(la) * math.sin(decl) + math.cos(la) * math.cos(decl) * math.cos(ha)
    zen = math.acos(max(-1, min(1, cz)))
    az = math.degrees(math.atan2(math.sin(ha), math.cos(ha) * math.sin(la) - math.tan(decl) * math.cos(la))) + 180
    return 90 - math.degrees(zen), az % 360


def set_sun(manifest, actors):
    try:
        when = datetime.fromisoformat(manifest.get("eventStart", "").replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        warn("no eventStart; sun left as in the template")
        return
    el, az = solar_position(when, manifest["origin"]["lat"], manifest["origin"]["lon"])
    # Light travels away from the sun: ENU (−sinA·cosE, −cosA·cosE, −sinE) → UE (X = E, Y = −N, Z = U)
    d = (-math.sin(math.radians(az)) * math.cos(math.radians(el)), math.cos(math.radians(az)) * math.cos(math.radians(el)), -math.sin(math.radians(el)))
    yaw = math.degrees(math.atan2(d[1], d[0]))
    pitch = math.degrees(math.asin(d[2]))
    for a in actors:
        if isinstance(a, unreal.DirectionalLight):
            a.set_actor_rotation(unreal.Rotator(pitch=pitch, yaw=yaw, roll=0), False)
            log(f"sun: elevation {el:.1f}°, azimuth {az:.1f}° ({when.isoformat()})")


def missing_files(pkg, index, want=None, hero=True):
    """Course files the import needs (for the chunks in `want`, all when None) that are not on disk — typically a zip
    part of the hand-off bundle unpacked into its own folder instead of the project folder."""
    kit = index["kit"]
    rels = [kit.get("glb") or f"{kit['dir']}/kit.glb", index.get("farUnreal")]
    if hero and index.get("hero"):
        rels.append(index["hero"].get("pebbles"))
    for c in index["chunks"]:
        if want is None or c["id"] in want:
            rels += [c.get("glbUnreal") or c["glb"], c.get("instances")] + ([c.get("hero")] if hero and index.get("hero") else [])
    return [r for r in rels if r and not os.path.exists(os.path.join(pkg, r))]


def main():
    a = parse()
    pkg = a.package
    manifest = load_json(os.path.join(pkg, "manifest.json"))
    index = load_json(os.path.join(pkg, "game", "index.json"))
    want = {int(x) for x in a.chunks.split(",")} if a.chunks else None
    missing = missing_files(pkg, index, want, not a.no_hero)
    if missing:
        unreal.log_error(f"[RidePrep] {len(missing)} course file(s) missing, e.g. {missing[0]}: unzip every zip "
                         f"(all _part…of… zips and _hero) into the same folder as the project, then run again "
                         f"(or add --no-hero if you left out the _hero zip). Looked in {pkg}")
        return
    overrides = load_json(a.overrides) if a.overrides else {}
    level_name = a.level or f"{manifest['courseId']}_game"
    croot = f"{ROOT}/Courses/{level_name}"
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    # Level
    les.new_level_from_template(f"{croot}/{level_name}", OPEN_WORLD_TEMPLATE)
    for actor in eas.get_all_level_actors():
        if isinstance(actor, (unreal.Landscape, unreal.LandscapeProxy)):
            eas.destroy_actor(actor)
    set_sun(manifest, eas.get_all_level_actors())
    rvt = None
    if not a.no_rvt:
        try:
            rvt = setup_rvt(corridor_bounds_cm(index))
        except Exception as ex:  # noqa: BLE001
            warn(f"RVT not set up ({ex}); the terrain blends toward the gravel layer instead")
    mis, terrain_mis, kit_meshes = import_kit(pkg, index, rvt)
    hero = index.get("hero") if not a.no_hero else None
    replaced = set(hero.get("replaces", [])) if hero else set()
    nanite = not a.no_nanite
    log("Nanite " + ("on" if nanite else "off: regular full-detail meshes (--no-nanite)"))
    pebble_meshes = import_pebbles(pkg, hero, mis, nanite) if hero else {}
    route = read_route(pkg, manifest)
    # Far field
    far = index.get("farUnreal")
    if far and os.path.exists(os.path.join(pkg, far)):
        for sm in [o for o in import_files([os.path.join(pkg, far)], f"{croot}/Far") if isinstance(o, unreal.StaticMesh)]:
            if "farfill" in sm.get_name():
                continue  # corridor fills are for streaming clients; every chunk is resident in the editor level
            assign_materials(sm, mis)
            configure_chunk_mesh(sm, "far", nanite)
            act = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
            act.static_mesh_component.set_static_mesh(sm)
            act.set_actor_label("RidePrep_Far")
            act.set_folder_path("RidePrep")
    # Chunks
    graph = unreal.load_asset(PCG_GRAPH) if not a.no_pcg and eal.does_asset_exist(PCG_GRAPH) else None
    if not a.no_pcg and graph is None:
        warn(f"{PCG_GRAPH} not found — PCG ground detail skipped (author it once, see apps/unreal/README.md)")
    n_inst = 0
    for c in index["chunks"]:
        if want is not None and c["id"] not in want:
            continue
        cid = c["id"]
        ox, oy, oz = c["origin"]
        loc = enu_to_ue(ox, oy, oz)
        glb = os.path.join(pkg, c.get("glbUnreal") or c["glb"])
        meshes = [o for o in import_files([glb], f"{croot}/Chunks/g{cid}") if isinstance(o, unreal.StaticMesh)]
        has_hero = bool(hero and c.get("hero") and os.path.exists(os.path.join(pkg, c["hero"])))
        if has_hero:  # the dense Nanite carriageway + shoulders replace the chunk's light road
            meshes += [o for o in import_files([os.path.join(pkg, c["hero"])], f"{croot}/Hero/h{cid}") if isinstance(o, unreal.StaticMesh)]
        for sm in meshes:
            kind = sm.get_name().split("_")[0].lower()
            if has_hero and kind in replaced:
                continue
            assign_materials(sm, {**mis, **terrain_mis} if kind == "terrain" else mis)
            configure_chunk_mesh(sm, "road" if kind == "hero" else kind, nanite, full_fallback=kind == "hero")
            act = eas.spawn_actor_from_class(unreal.StaticMeshActor, loc)
            act.static_mesh_component.set_static_mesh(sm)
            if kind in ("markings", "defects"):
                act.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
            if rvt is not None and kind in RVT_DRAW_KINDS:
                try:
                    draw_into_rvt(act, rvt)
                except Exception as ex:  # noqa: BLE001
                    warn(f"RVT draw on g{cid}_{kind}: {ex}")
            act.set_actor_label(f"g{cid}_{kind}" if kind != "hero" else sm.get_name())
            act.set_folder_path(f"RidePrep/Chunks/g{cid // 20 * 20:03d}")
        road_spline(route, c, loc)
        # Kit instances
        inst = load_json(os.path.join(pkg, c["instances"]))["instances"]
        ia = Instancer(loc, f"g{cid}_instances", f"RidePrep/Chunks/g{cid // 20 * 20:03d}")
        for asset, rows in inst.items():
            ov = overrides.get(asset, {})
            mesh = unreal.load_asset(ov["mesh"]) if ov.get("mesh") else kit_meshes.get(asset)
            if mesh is None:
                continue
            yaw_off = float(ov.get("yawDeg", 0.0))
            sc = float(ov.get("scale", 1.0))
            xs = [unreal.Transform(location=unreal.Vector(x * 100, -y * 100, z * 100),
                                   rotation=unreal.Rotator(pitch=0, yaw=-math.degrees(rot) + yaw_off, roll=0),
                                   scale=unreal.Vector(s * sc, s * sc, s * sc)) for x, y, z, rot, s in rows]
            solid = asset.startswith(SOLID_ASSETS)
            n_inst += ia.add(asset, mesh, xs, float(CULL_CM.get(asset, 0)), solid)
        if has_hero and c.get("heroPebbles") and os.path.exists(os.path.join(pkg, c["heroPebbles"])):
            for asset, rows in load_json(os.path.join(pkg, c["heroPebbles"]))["instances"].items():
                mesh = pebble_meshes.get(asset)
                if mesh is None:
                    continue
                xs = [unreal.Transform(location=unreal.Vector(x * 100, -y * 100, z * 100), rotation=unreal.Rotator(pitch=0, yaw=-math.degrees(rot), roll=0),
                                       scale=unreal.Vector(sc_, sc_, sc_)) for x, y, z, rot, sc_ in rows]
                n_inst += ia.add(asset, mesh, xs, 6000.0, False)
        # PCG ground detail from the land-use mask
        if graph is not None and c.get("landuse"):
            pcg_volume(pkg, c, croot, graph, loc)
    import_rider(a.rider_dir)
    if a.rails != "none":
        rider_rails(route, rail_ranges(a.rails, manifest, index))
    les.save_current_level()
    eal.save_directory(ROOT, only_if_is_dirty=True, recursive=True)
    n_hero = sum(1 for c in index["chunks"] if c.get("hero")) if hero else 0
    log(f"imported {manifest['name']} → {croot}/{level_name}: {len(index['chunks'])} chunks ({n_hero} hero), {n_inst} instances")


def corridor_bounds_cm(index):
    """UE-space box (cm) around every chunk's terrain (chunk bounds are ENU metres relative to the chunk origin)."""
    xs, ys, zs = [], [], []
    for c in index["chunks"]:
        ox, oy, oz = c["origin"]
        b = c.get("bounds")
        if b:
            xs += [b[0] + 0.0, b[2] + 0.0]
            ys += [b[1] + 0.0, b[3] + 0.0]
        else:
            xs.append(ox)
            ys.append(oy)
        zs.append(oz)
    # bounds are absolute lattice metres (cells × grid), so no origin offset; UE flips north
    return ((min(xs) * 100, -max(ys) * 100, min(zs) * 100 - 20000), (max(xs) * 100, -min(ys) * 100, max(zs) * 100 + 20000))


def import_pebbles(pkg, hero, mis, nanite=True):
    path = os.path.join(pkg, hero["pebbles"])
    if not os.path.exists(path):
        return {}
    out = {}
    for sm in [o for o in import_files([path], f"{ROOT}/Hero") if isinstance(o, unreal.StaticMesh)]:
        assign_materials(sm, mis)
        configure_chunk_mesh(sm, "road", nanite)
        body = sm.get_editor_property("body_setup")
        if body:
            body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_DEFAULT)
        for k in ("pebble_a", "pebble_b", "pebble_c"):
            if sm.get_name() == k or sm.get_name().endswith("_" + k):
                out[k] = sm
    log(f"hero pebbles: {sorted(out)}")
    return out


def read_route(pkg, manifest):
    """x, y, z, s arrays (ENU m) from route.bin, for the road splines. Plain `array` — no numpy in the editor."""
    from array import array

    r = manifest["route"]
    n = r["count"]
    data = open(os.path.join(pkg, "route.bin"), "rb").read()
    out = {"spacing": float(r["sampleSpacingM"])}
    for spec in r["arrays"]:
        if spec["name"] in ("s", "x", "y", "z", "headingRad", "bankDeg") and spec["type"] == "float32":
            a = array("f")
            a.frombytes(data[spec["offset"]:spec["offset"] + 4 * n])
            if sys.byteorder != "little":
                a.byteswap()
            out[spec["name"]] = a
        elif spec["name"] == "roadWidthM":
            out["roadWidthM"] = array("B", data[spec["offset"]:spec["offset"] + n])
    return out


def road_spline(route, c, loc, step_m=10.0):
    """ARidePrepRoadSpline along this chunk's stretch of the course road (UE units, relative to the chunk actor)."""
    if not route or not hasattr(unreal, "RidePrepRoadSpline"):
        return
    s, x, y, z = route["s"], route["x"], route["y"], route["z"]
    pts = []
    i = 0
    last = -1e9
    while i < len(s) and s[i] <= c["sEnd"] + 1e-6:
        if s[i] >= c["sStart"] - 1e-6 and s[i] - last >= step_m - 1e-6:
            pts.append(unreal.Vector(x[i] * 100 - loc.x, -y[i] * 100 - loc.y, z[i] * 100 - loc.z))
            last = s[i]
        i += 1
    if len(pts) < 2:
        return
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    sp = eas.spawn_actor_from_class(unreal.RidePrepRoadSpline, loc)
    sp.set_points(pts)
    sp.set_actor_label(f"g{c['id']}_road_spline")
    sp.set_folder_path(f"RidePrep/Chunks/g{c['id'] // 20 * 20:03d}")


class Instancer:
    """One chunk's kit instances. With the RidePrepRuntime C++ plugin compiled in: ARidePrepInstanceActor (HISM per
    asset). Without it (a Blueprint-only render project): a static mesh actor with one HISM component per asset added
    through the SubobjectDataSubsystem — no C++ toolchain needed."""

    def __init__(self, loc, label, folder):
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        self.native = hasattr(unreal, "RidePrepInstanceActor")
        self.actor = eas.spawn_actor_from_class(unreal.RidePrepInstanceActor if self.native else unreal.StaticMeshActor, loc)
        self.actor.set_actor_label(label)
        self.actor.set_folder_path(folder)
        if not self.native:
            self.sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
            self.root = self.sds.k2_gather_subobject_data_for_instance(self.actor)[0]

    def add(self, asset, mesh, transforms, cull_end_cm, collision, shadows=True):
        if not transforms:
            return 0
        if self.native:
            return self.actor.add_instances(asset, mesh, transforms, 0.0, cull_end_cm, collision, shadows)
        params = unreal.AddNewSubobjectParams(parent_handle=self.root, new_class=unreal.HierarchicalInstancedStaticMeshComponent,
                                              blueprint_context=None)
        handle, fail = self.sds.add_new_subobject(params)
        if str(fail):
            warn(f"{asset}: {fail}")
            return 0
        self.sds.rename_subobject(handle, unreal.Text(asset))
        lib = unreal.SubobjectDataBlueprintFunctionLibrary
        comp = lib.get_object(lib.get_data(handle))
        comp.set_static_mesh(mesh)
        comp.set_mobility(unreal.ComponentMobility.STATIC)
        if cull_end_cm > 0:
            comp.set_cull_distances(0, int(cull_end_cm))
        comp.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS if collision else unreal.CollisionEnabled.NO_COLLISION)
        comp.set_cast_shadow(shadows)
        comp.add_instances(transforms, False, False)
        return len(transforms)


def rail_ranges(spec, manifest, index):
    """[(s0, s1, label)] in route metres: explicit 'km:a-b,…', or 'auto' = the start, every climb, every hero stretch."""
    L = float(manifest["route"]["count"] - 1) * float(manifest["route"]["sampleSpacingM"])
    out = []
    if spec.startswith("km:"):
        for part in spec[3:].split(","):
            a, _, b = part.partition("-")
            out.append((float(a) * 1000, float(b or a) * 1000, f"km{a}-{b or a}"))
    else:
        out.append((0.0, min(2000.0, L), "start"))
        for k, c in enumerate(manifest.get("segments", {}).get("climbs", [])):
            out.append((max(0.0, c["sStart"] - 300), min(L, c["sEnd"] + 200), f"climb{k + 1}"))
        hero = sorted(c["id"] for c in index["chunks"] if c.get("hero"))
        run = []
        for cid in hero + [None]:
            if run and (cid is None or cid != run[-1] + 1):
                s0 = next(c["sStart"] for c in index["chunks"] if c["id"] == run[0])
                s1 = next(c["sEnd"] for c in index["chunks"] if c["id"] == run[-1])
                out.append((s0, s1, f"hero_km{s0 / 1000:.1f}-{s1 / 1000:.1f}"))
                run = []
            if cid is not None:
                run.append(cid)
    return [(max(0.0, a), min(L, b), lab) for a, b, lab in out if b > a]


def rider_rails(route, ranges):
    """Camera Rig Rails along the riding line (keep right, ~1 m from the edge, on the crowned/banked surface): attach
    the rider and cameras in Sequencer and key "Current Position on Rail" (0 → 1) for a ride along the course."""
    if not route or not hasattr(unreal, "CameraRig_Rail"):
        warn("Camera Rig Rail not available — rails skipped")
        return
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    s, x, y, z, hd = route["s"], route["x"], route["y"], route["z"], route.get("headingRad")
    wid, bank = route.get("roadWidthM"), route.get("bankDeg")
    for s0, s1, label in ranges:
        idx = [i for i in range(len(s)) if s0 <= s[i] <= s1]
        if len(idx) < 2:
            continue
        pts = []
        for i in idx:
            hw = (wid[i] if wid else 6) / 2.0
            off = 0.0 if hw < 1.6 else min(max(max(hw / 2, hw - 1.0), 0.3), hw - 0.5)  # LaneKeeper's straight-road line
            h = hd[i] if hd else 0.0
            nx, ny = math.cos(h), -math.sin(h)
            t = math.tan(math.radians(bank[i] if bank else 0.0))
            w = min(1.0, abs(t) / 0.025)
            dz = (1 - w) * (-0.02 * abs(off)) + w * (-t * off)
            pts.append((x[i] + nx * off, y[i] + ny * off, z[i] + 0.04 + dz))
        x0, y0, z0 = pts[0]
        origin = enu_to_ue(x0, y0, z0)
        rail = eas.spawn_actor_from_class(unreal.CameraRig_Rail, origin)
        rail.set_actor_label(f"RideLine_{label}")
        rail.set_folder_path("RidePrep/Rails")
        spline = rail.get_rail_spline_component()
        spline.set_spline_points([unreal.Vector((px - x0) * 100, -(py - y0) * 100, (pz - z0) * 100) for px, py, pz in pts],
                                 unreal.SplineCoordinateSpace.LOCAL, True)
        try:
            rail.set_editor_property("lock_orientation_to_rail", True)
        except Exception as ex:  # noqa: BLE001
            warn(f"rail orientation lock: {ex}")
        log(f"rail RideLine_{label}: {(s1 - s0) / 1000:.2f} km, {len(pts)} points")


def import_rider(rider_dir):
    """tools/rider GLBs → /Game/RidePrep/Rider/<bike>: skeletal mesh, skeleton, and the clips as anim sequences."""
    for bike in ("road", "tt"):
        path = os.path.join(rider_dir, f"rider_{bike}.glb")
        if not os.path.exists(path):
            warn(f"rider model {path} missing (build it with tools/rider)")
            continue
        dest = f"{ROOT}/Rider/{bike}"
        ensure_dir(dest)
        objs = import_files([path], dest)
        kinds = sorted({type(o).__name__ for o in objs})
        log(f"rider {bike}: {len(objs)} assets ({', '.join(kinds)})")


def pcg_volume(pkg, c, croot, graph, loc):
    tex = import_files([os.path.join(pkg, c["landuse"])], f"{croot}/Landuse")
    if not tex:
        return
    t = tex[0]
    t.set_editor_property("srgb", False)
    t.set_editor_property("filter", unreal.TextureFilter.TF_NEAREST)
    t.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
    t.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_GRAYSCALE)
    x0, y0, x1, y1 = c["landuseBounds"]
    centre = unreal.Vector(loc.x + (x0 + x1) / 2 * 100, loc.y - (y0 + y1) / 2 * 100, loc.z)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    vol = eas.spawn_actor_from_class(unreal.PCGVolume, centre)
    vol.set_actor_scale3d(unreal.Vector((x1 - x0) / 2, (y1 - y0) / 2, 50))  # PCG volume is a 200 cm cube
    vol.set_actor_label(f"g{c['id']}_pcg")
    vol.set_folder_path(f"RidePrep/Chunks/g{c['id'] // 20 * 20:03d}")
    comp = vol.get_component_by_class(unreal.PCGComponent)
    comp.set_graph(graph)
    try:
        gi = comp.get_editor_property("graph_instance")
        unreal.PCGGraphParametersHelpers.set_soft_object_parameter(gi, "LanduseMask", t)
        unreal.PCGGraphParametersHelpers.set_vector_parameter(gi, "LanduseBoundsMinCm", unreal.Vector(centre.x - (x1 - x0) * 50, centre.y - (y1 - y0) * 50, 0))
        unreal.PCGGraphParametersHelpers.set_vector_parameter(gi, "LanduseBoundsMaxCm", unreal.Vector(centre.x + (x1 - x0) * 50, centre.y + (y1 - y0) * 50, 0))
    except Exception as ex:  # noqa: BLE001
        vol.tags = [unreal.Name(f"RidePrep:landuse:{t.get_path_name()}")]
        warn(f"PCG graph parameters not set ({ex}); mask path stored in the volume tags")
    comp.generate(True)


if __name__ == "__main__":
    main()
