"""Course preview shots with Cycles: assemble the game chunks around a course position, place the kit instances,
sun for the race morning, and render a cockpit / chase / drone view.

  blender -b --factory-startup --python render_course.py -- --kit <kit_dir> --specs <game_dir> --s 41200 \
      --mode cockpit --out shot.jpg [--look-back] [--sun-elev 35 --sun-az 125] [--radius 900]
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402,I001
import mathutils  # noqa: E402

import bake_game_chunk as bg  # noqa: E402
import kitlib  # noqa: E402
import render_common as rc  # noqa: E402


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--kit", required=True)
    p.add_argument("--specs", required=True)
    p.add_argument("--s", type=float, required=True)
    p.add_argument("--mode", default="cockpit", choices=["cockpit", "chase", "drone", "side"])
    p.add_argument("--out", required=True)
    p.add_argument("--look-back", action="store_true")
    p.add_argument("--radius", type=float, default=900.0)
    p.add_argument("--sun-elev", type=float, default=36.0)
    p.add_argument("--sun-az", type=float, default=128.0)
    p.add_argument("--samples", type=int, default=40)
    p.add_argument("--w", type=int, default=1600)
    p.add_argument("--h", type=int, default=900)
    p.add_argument("--lens", type=float, default=0.0)
    p.add_argument("--no-far", action="store_true")
    return p.parse_args(argv)


def route_pose(specs_dir, index, s):
    """(x, y, z, heading) in world ENU at distance s, from the chunk specs' road arrays."""
    for c in index["chunks"]:
        if c["sStart"] <= s <= c["sEnd"]:
            spec = json.load(open(os.path.join(specs_dir, f"g{c['id']}.json")))
            rd = spec["road"]
            ox, oy, oz = spec["origin"]
            ss = rd["s"]
            k = max(0, min(len(ss) - 2, next((i for i in range(len(ss) - 1) if ss[i + 1] >= s), len(ss) - 2)))
            t = (s - ss[k]) / max(ss[k + 1] - ss[k], 1e-6)
            lerp = lambda a: a[k] + (a[k + 1] - a[k]) * t  # noqa: E731
            hd0, hd1 = rd["heading"][k], rd["heading"][k + 1]
            dh = (hd1 - hd0 + math.pi) % math.tau - math.pi
            return lerp(rd["x"]) + ox, lerp(rd["y"]) + oy, lerp(rd["z"]) + oz, hd0 + dh * t, (rd["width"][k] / 2)
    raise SystemExit(f"s={s} outside the course")


def load_kit_meshes(kit_dir):
    path = os.path.join(kit_dir, "kit.blend")
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.meshes = list(src.meshes)
    return {m.name: m for m in dst.meshes}


def cockpit(cam):
    """Simple road-bike front end (drop bars, stem, hoods, computer) parented to the camera."""
    mb = kitlib.MeshBuilder("cockpit")
    # In camera space: −Z forward, +Y up, +X right
    y0, z0 = -0.33, -0.62
    mb.cylinder((-0.21, y0, z0), (0.21, y0, z0), 0.014, 0.014, 10, "paint_black")
    for sx in (-1, 1):
        mb.cylinder((sx * 0.21, y0, z0), (sx * 0.215, y0 - 0.02, z0 - 0.12), 0.014, 0.014, 8, "paint_black")
        mb.cylinder((sx * 0.215, y0 - 0.02, z0 - 0.12), (sx * 0.2, y0 - 0.15, z0 - 0.1), 0.014, 0.014, 8, "paint_black")
        mb.box((sx * 0.21, y0 + 0.03, z0 - 0.05), (0.035, 0.06, 0.09), "paint_black")
    mb.cylinder((0, y0 - 0.02, z0 + 0.12), (0, y0, z0), 0.017, 0.017, 10, "paint_black")
    mb.box((0, y0 + 0.012, z0 - 0.07), (0.055, 0.012, 0.085), "paint_black")
    ob = mb.build(True)
    ob.parent = cam
    # Small screen glow
    scr = kitlib.MeshBuilder("computer_screen")
    scr.quad((-0.022, y0 + 0.0185, z0 - 0.105), (0.022, y0 + 0.0185, z0 - 0.105), (0.022, y0 + 0.0185, z0 - 0.04), (-0.022, y0 + 0.0185, z0 - 0.04), "marking_white")
    s = scr.build(True)
    s.parent = cam
    return ob


def main():
    a = args()
    kitlib.reset_scene()
    kitlib.load_kit(a.kit)
    index = json.load(open(os.path.join(a.specs, "index.json")))
    px, py, pz, hd, hw = route_pose(a.specs, index, a.s)
    W0 = (px, py, pz)  # render frame origin
    # Chunks whose origin lies within radius of the camera (+ neighbours along the route)
    chosen = [c for c in index["chunks"] if math.hypot(c["origin"][0] - px, c["origin"][1] - py) < a.radius + 500]
    meshes = load_kit_meshes(a.kit)
    col = bpy.context.scene.collection
    n_inst = 0
    for c in chosen:
        spec = json.load(open(os.path.join(a.specs, f"g{c['id']}.json")))
        ox, oy, oz = spec["origin"]
        objs = bg.build_chunk(spec, textured=True, col=col)
        for o in objs:
            o.location = (ox - W0[0], oy - W0[1], oz - W0[2])
        for asset, lst in spec["instances"].items():
            for x, y, z, rot, sc in lst:
                wx, wy = x + ox - W0[0], y + oy - W0[1]
                dist = math.hypot(wx, wy)
                if dist > a.radius:
                    continue
                me = meshes.get(asset if dist < 220 else asset + "__lod1") or meshes.get(asset)
                if me is None:
                    continue
                ob = bpy.data.objects.new(asset, me)
                ob.location = (wx, wy, z + oz - W0[2])
                ob.rotation_euler = (0, 0, rot)
                ob.scale = (sc, sc, sc)
                col.objects.link(ob)
                n_inst += 1
    if not a.no_far and os.path.exists(os.path.join(a.specs, "far.json")):
        far = json.load(open(os.path.join(a.specs, "far.json")))
        bg.build_far(far, textured=True, col=col, origin=W0, fills=False)
    print(f"render: {len(chosen)} chunks, {n_inst} instances", flush=True)
    # Camera
    fx, fy = math.sin(hd), math.cos(hd)
    if a.look_back:
        fx, fy = -fx, -fy
    rx, ry = fy, -fx
    if a.mode == "cockpit":
        loc = (rx * hw * 0.45, ry * hw * 0.45, 1.48)
        tgt = (loc[0] + fx * 40, loc[1] + fy * 40, 1.48 - 2.6)
        lens = a.lens or 20
    elif a.mode == "chase":
        loc = (-fx * 7 + rx * hw * 0.4, -fy * 7 + ry * hw * 0.4, 2.6)
        tgt = (fx * 25, fy * 25, 0.8)
        lens = a.lens or 24
    elif a.mode == "side":
        loc = (rx * (hw + 9), ry * (hw + 9), 1.6)
        tgt = (fx * 6, fy * 6, 1.0)
        lens = a.lens or 28
    else:
        loc = (-fx * 60 + rx * 40, -fy * 60 + ry * 40, 55)
        tgt = (fx * 120, fy * 120, 0)
        lens = a.lens or 24
    # Terrain-following camera height (cockpit/chase sit on the road surface already: road z = 0 here)
    cam = rc.camera(loc, tgt, lens=lens)
    if a.mode == "cockpit":
        cockpit(cam)
    rc.sky_and_sun(a.sun_elev, a.sun_az)
    rc.render(a.out, a.w, a.h, a.samples)


if __name__ == "__main__":
    main()
