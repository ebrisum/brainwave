"""Game-art "hero level" import (hybrid pipeline): gpx2course game package → World Partition level.

  UnrealEditor-Cmd RidePrep.uproject -run=pythonscript \
      -script="Scripts/import_game_level.py --package /data/courses/c_xxx [--overrides Config/RidePrepAssetOverrides.json]"

What it builds (all from <package>/game/index.json, written by `gpx2course game`):
  1. Kit: master materials M_RidePrepKit / M_RidePrepKit_Masked (created once), textures, one material instance per
     kit material id (UV scale = 1/tileM, roughness, tint) with a PhysMat per surface class, kit meshes with
     `<asset>__lod1` merged in as LOD1.
  2. Level: new World Partition level (OpenWorld template; its landscape is removed — terrain comes with the chunks).
  3. Chunks: g<id>.glb (uncompressed copies in game/unreal/) → static meshes with the kit material instances,
     complex-as-simple collision on terrain/roads/buildings, none on markings, Nanite on opaque meshes; one actor per
     mesh at the chunk origin (ENU → UE: X = E·100, Y = −N·100, Z = U·100), so World Partition streams them by cell.
  4. Instances: one ARidePrepInstanceActor per chunk with HISM per kit asset; `--overrides` maps kit asset ids to
     high-quality project assets (e.g. scanned Pinus pinea, cypress, olive) with optional yaw offset/scale.
  5. PCG: a PCG volume per chunk with the land-use mask (game/landuse/g<id>.png) as graph parameter for dense ground
     detail (grass, flowers, stones, shoulder gravel) — graph authored once in the project (see README).
  6. Sun: directional light set for the event start (manifest eventStart, NOAA solar position).

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
    "gravel": "Gravel", "roof_flat": "Gravel", "grass_dry": "Grass", "grass_green": "Grass", "orchard_grass": "Grass", "wetland": "Grass",
    "stubble": "Soil", "soil_ploughed": "Soil", "vineyard_soil": "Soil", "forest_floor": "Soil", "urban_ground": "Soil", "sand": "Soil",
    "salt": "Soil", "crop_green": "Grass", "water": "Water", "saltpan_water": "Water", "metal_galvanised": "Metal", "plastic_barrier": "Metal",
}
PHYSMATS = {"Asphalt": (0.9, 1), "Setts": (0.75, 2), "Gravel": (0.6, 3), "Grass": (0.5, 4), "Soil": (0.55, 5), "Water": (0.1, 6), "Metal": (0.45, 7)}
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


def master_material(name, masked):
    """BaseColor(tex)·Tint, Normal(tex), Roughness, Metallic; UV = TexCoord0 · UVScale (UVs are metres → 1/tileM)."""
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
    for i, (pname, default, prop) in enumerate((("Roughness", 0.9, unreal.MaterialProperty.MP_ROUGHNESS),
                                                ("Metallic", 0.0, unreal.MaterialProperty.MP_METALLIC))):
        s = mel.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -100, 250 + 120 * i)
        s.set_editor_property("parameter_name", pname)
        s.set_editor_property("default_value", default)
        mel.connect_material_property(s, "", prop)
    if masked:
        mel.connect_material_property(base, "A", unreal.MaterialProperty.MP_OPACITY_MASK)
    mel.recompile_material(m)
    return m


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


def import_kit(pkg, index):
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
    opaque, masked = master_material("M_RidePrepKit", False), master_material("M_RidePrepKit_Masked", True)
    pms = physmats()
    mdir = f"{kroot}/Materials"
    ensure_dir(mdir)
    mis = {}
    for mid, spec in mats_doc.items():
        cut = spec.get("alphaCutoff") is not None
        mi = create(f"MI_{mid}", mdir, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        mi.set_editor_property("parent", masked if cut else opaque)
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
        mis[mid] = mi
    log(f"kit material instances: {len(mis)}")
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
    return mis, meshes


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


def configure_chunk_mesh(sm, kind):
    body = sm.get_editor_property("body_setup")
    if body:
        body.set_editor_property("collision_trace_flag",
                                 unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if kind != "markings" else unreal.CollisionTraceFlag.CTF_USE_DEFAULT)
    if kind in ("terrain", "buildings", "road", "sideroads", "far"):
        try:
            ns = sm.get_editor_property("nanite_settings")
            ns.set_editor_property("enabled", True)
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


def main():
    a = parse()
    pkg = a.package
    manifest = load_json(os.path.join(pkg, "manifest.json"))
    index = load_json(os.path.join(pkg, "game", "index.json"))
    overrides = load_json(a.overrides) if a.overrides else {}
    level_name = a.level or f"{manifest['courseId']}_game"
    croot = f"{ROOT}/Courses/{level_name}"
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    mis, kit_meshes = import_kit(pkg, index)
    # Level
    les.new_level_from_template(f"{croot}/{level_name}", OPEN_WORLD_TEMPLATE)
    for actor in eas.get_all_level_actors():
        if isinstance(actor, (unreal.Landscape, unreal.LandscapeProxy)):
            eas.destroy_actor(actor)
    set_sun(manifest, eas.get_all_level_actors())
    # Far field
    far = index.get("farUnreal")
    if far and os.path.exists(os.path.join(pkg, far)):
        for sm in [o for o in import_files([os.path.join(pkg, far)], f"{croot}/Far") if isinstance(o, unreal.StaticMesh)]:
            if "farfill" in sm.get_name():
                continue  # corridor fills are for streaming clients; every chunk is resident in the editor level
            assign_materials(sm, mis)
            configure_chunk_mesh(sm, "far")
            act = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
            act.static_mesh_component.set_static_mesh(sm)
            act.set_actor_label("RidePrep_Far")
            act.set_folder_path("RidePrep")
    # Chunks
    want = {int(x) for x in a.chunks.split(",")} if a.chunks else None
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
        for sm in meshes:
            kind = sm.get_name().split("_")[0].lower()
            assign_materials(sm, mis)
            configure_chunk_mesh(sm, kind)
            act = eas.spawn_actor_from_class(unreal.StaticMeshActor, loc)
            act.static_mesh_component.set_static_mesh(sm)
            if kind == "markings":
                act.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
            act.set_actor_label(f"g{cid}_{kind}")
            act.set_folder_path(f"RidePrep/Chunks/g{cid // 20 * 20:03d}")
        # Kit instances
        inst = load_json(os.path.join(pkg, c["instances"]))["instances"]
        ia = eas.spawn_actor_from_class(unreal.RidePrepInstanceActor, loc)
        ia.set_actor_label(f"g{cid}_instances")
        ia.set_folder_path(f"RidePrep/Chunks/g{cid // 20 * 20:03d}")
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
            n_inst += ia.add_instances(asset, mesh, xs, 0.0, float(CULL_CM.get(asset, 0)), solid, True)
        # PCG ground detail from the land-use mask
        if graph is not None and c.get("landuse"):
            pcg_volume(pkg, c, croot, graph, loc)
    les.save_current_level()
    eal.save_directory(ROOT, only_if_is_dirty=True, recursive=True)
    log(f"imported {manifest['name']} → {croot}/{level_name}: {len(index['chunks'])} chunks, {n_inst} instances")


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
