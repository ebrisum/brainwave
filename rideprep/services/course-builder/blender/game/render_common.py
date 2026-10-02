"""Render helpers for kit showcases and course preview shots (Cycles, CPU; physically based sky + sun)."""
import math

import bpy  # noqa: I001
import mathutils

import kitlib


def sky_and_sun(elevation_deg=40.0, azimuth_deg=135.0, strength=1.0, haze=1.0):
    """azimuth: compass bearing the sun is *in* (0 = north, 90 = east), Blender world +Y = north."""
    world = bpy.data.worlds.new("World") if not bpy.context.scene.world else bpy.context.scene.world
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    sky = nt.nodes.new("ShaderNodeTexSky")
    for t in ("MULTIPLE_SCATTERING", "SINGLE_SCATTERING", "NISHITA"):
        try:
            sky.sky_type = t
            break
        except TypeError:
            continue
    sky.sun_elevation = math.radians(elevation_deg)
    # Sky texture rotation: 0 = sun towards −Y? Blender: sun_rotation measured from +X counter-clockwise → convert from compass
    sky.sun_rotation = math.radians(90.0 - azimuth_deg)
    if hasattr(sky, "air_density"):
        sky.air_density = 1.0
        sky.aerosol_density = 1.0 * haze
    elif hasattr(sky, "dust_density"):
        sky.dust_density = 1.0 * haze
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 0.35 * strength
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 3.2 * strength
    sun_data.angle = math.radians(0.53)
    sun_data.color = (1.0, 0.96, 0.9)
    sun = bpy.data.objects.new("Sun", sun_data)
    bpy.context.scene.collection.objects.link(sun)
    el, az = math.radians(elevation_deg), math.radians(azimuth_deg)
    d = mathutils.Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))  # towards the sun
    sun.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    return sun


def camera(loc, target, lens=28.0, roll_deg=0.0):
    cd = bpy.data.cameras.new("Camera")
    cd.lens = lens
    cd.clip_start = 0.1
    cd.clip_end = 40000
    cam = bpy.data.objects.new("Camera", cd)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = loc
    d = mathutils.Vector(target) - mathutils.Vector(loc)
    q = d.to_track_quat("-Z", "Y")
    cam.rotation_euler = q.to_euler()
    if roll_deg:
        cam.rotation_euler.rotate_axis("Z", math.radians(roll_deg))
    bpy.context.scene.camera = cam
    return cam


def ground_plate(center, size, mid):
    mb = kitlib.MeshBuilder("ground")
    cx, cy, cz = center
    w, h = size
    mb.quad((cx - w / 2, cy - h / 2, cz), (cx + w / 2, cy - h / 2, cz), (cx + w / 2, cy + h / 2, cz), (cx - w / 2, cy + h / 2, cz), mid,
            [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)])
    return mb.build()


def render(path, w, h, samples=48, exposure=-0.55):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except TypeError:
        pass
    sc.cycles.max_bounces = 4
    sc.cycles.transparent_max_bounces = 16
    sc.render.resolution_x = w
    sc.render.resolution_y = h
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX" if "AgX" in [i.identifier for i in sc.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"
    try:
        sc.view_settings.look = "AgX - Punchy"
    except TypeError:
        pass
    sc.view_settings.exposure = exposure
    sc.render.image_settings.file_format = "JPEG" if path.endswith(".jpg") else "PNG"
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
