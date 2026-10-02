"""Rider + bike for RidePrep, built in headless Blender (5.x):

  blender -b --factory-startup --python tools/rider/build_rider.py -- --mh <makehuman_dir> --out <dir>
      [--bike road|tt] [--variant male|female] [--frame "#c81e1e"] [--jersey "#f0b429"] [--render]

Body: MakeHuman hm08 (CC0) morphed to a young athletic adult, 74-bone rig, cycling kit with straight hems, helmet and
glasses. Bike: procedural road or TT bike fitted to the rider (saddle height = 0.883 × inseam). One armature drives
both: bike bones (bike → crank → pedals, wheels, steer) and the rider (root is a child of the bike bone).
Clips (glTF animations; cyclic ones are one crank revolution, 48 frames + a closing key = 2.0 s at 24 fps):
  pedal  seated pedalling, ankling, slight hip rock
  stand  out of the saddle: hips up and forward, bike rocks ±7° under the rider
  coast  pedals level, relaxed
  pedal_drops, coast_drops (road bike)  the same in the drops
Clients set the clip time from the crank angle (time = angle / 2π × duration), spin `wheel.F`/`wheel.R` from speed, lean
the `bike` bone in corners and steer with `steer`. Exports rider_<bike>.glb (+ .blend for Unreal/artists).
"""
import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "services", "course-builder", "blender", "game"))

import bpy  # noqa: E402,I001
import mathutils  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import bike  # noqa: E402
import kit  # noqa: E402
import mh  # noqa: E402

BODIES = {
    "male": {"caucasian-male-young": 1.0, "universal-male-young-maxmuscle-minweight": 0.45, "universal-male-young-averagemuscle-minweight": 0.25,
             "male-young-averagemuscle-averageweight-maxheight": 0.15, "male-young-averagemuscle-averageweight-idealproportions": 0.6},
    "female": {"caucasian-female-young": 1.0, "universal-female-young-maxmuscle-minweight": 0.45},
}
FRAMES = 48
POSITION = {"road": "hoods", "tt": "aero"}


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--mh", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--bike", default="road", choices=["road", "tt"])
    p.add_argument("--variant", default="male", choices=list(BODIES))
    p.add_argument("--frame", default=None)
    p.add_argument("--jersey", default="#f0b429")
    p.add_argument("--render", action="store_true")
    p.add_argument("--no-export", action="store_true")
    return p.parse_args(argv)


# ---- helpers --------------------------------------------------------------------------------------------------------


def head(arm, b):
    return arm.matrix_world @ arm.pose.bones[b].head


def tail(arm, b):
    return arm.matrix_world @ arm.pose.bones[b].tail


def rest_head(arm, b):
    return arm.data.bones[b].head_local.copy()


def rotate_world(arm, bone, axis, angle_rad, pivot=None):
    """Rotate a pose bone (and its children) about a world axis through `pivot` (default: its head)."""
    pb = arm.pose.bones[bone]
    pivot = pb.head.copy() if pivot is None else pivot
    R = Matrix.Translation(pivot) @ Matrix.Rotation(angle_rad, 4, axis) @ Matrix.Translation(-pivot)
    pb.matrix = R @ pb.matrix
    bpy.context.view_layer.update()


def elbow_point(sh, grip, upper, fore, hint):
    """Two-link arm: the elbow a distance `upper` from the shoulder and `fore` from the grip, bent toward `hint`."""
    d = grip - sh
    n = d.normalized()
    L = min(d.length, upper + fore - 1e-3)
    a = (upper * upper - fore * fore + L * L) / (2 * L)
    h = math.sqrt(max(0.0, upper * upper - a * a))
    return sh + n * a + (hint - n * hint.dot(n)).normalized() * h


def aim_bone(arm, bone, direction):
    """Rotate a pose bone about its head so it points along `direction` (world), minimal rotation."""
    pb = arm.pose.bones[bone]
    cur = (pb.tail - pb.head).normalized()
    q = cur.rotation_difference(direction.normalized())
    R = Matrix.Translation(pb.head) @ q.to_matrix().to_4x4() @ Matrix.Translation(-pb.head)
    pb.matrix = R @ pb.matrix
    bpy.context.view_layer.update()


def empty(name, loc):
    e = bpy.data.objects.new(name, None)
    e.location = loc
    bpy.context.scene.collection.objects.link(e)
    return e


def ik(arm, bone, target, chain, pole=None, pole_angle=-math.pi / 2, use_tail=True):
    c = arm.pose.bones[bone].constraints.new("IK")
    c.target = target
    c.chain_count = chain
    c.use_tail = use_tail
    if pole is not None:
        c.pole_target = pole
        c.pole_angle = pole_angle
    return c


# ---- assembly -------------------------------------------------------------------------------------------------------


def build(a):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    body, arm, _ = mh.build_body(a.mh, BODIES[a.variant], name="Rider")
    # Face +X and stand on the ground: transform mesh data and rest bones (armature object stays at identity)
    zmin = min(v.co.z for v in body.data.vertices)
    M = Matrix.Rotation(math.pi / 2, 4, "Z") @ Matrix.Translation((0, 0, -zmin))
    body.data.transform(M)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    for eb in arm.data.edit_bones:
        eb.transform(M)
    bpy.ops.object.mode_set(mode="OBJECT")
    kit.apply_kit(body, arm, {"jersey": a.jersey, "shorts": "#14161a", "socks": "#f4f4f4", "shoes": "#f7f7f7", "gloves": "#1b1c1f"})
    helmet = kit.add_helmet(body, arm)
    glasses = kit.add_glasses(body, arm)
    kit.add_shoes(body, arm)
    # Fit: inseam = crotch height (lowest body point between the legs), saddle height (BB → saddle top) = 0.883 × inseam
    crotch = min(v.co.z for v in body.data.vertices if abs(v.co.y) < 0.025 and v.co.z > 0.5)
    inseam = crotch
    saddle_h = 0.883 * inseam
    aero_fit = None
    if a.bike == "tt":
        # Aero fit: torso ~14° above horizontal from the hips on the saddle nose; elbows under the shoulders
        r = lambda b: rest_head(arm, b)  # noqa: E731
        hips_r = (r("upperleg01.L") + r("upperleg01.R")) / 2
        sh_r = (r("upperarm01.L") + r("upperarm01.R")) / 2
        torso = (sh_r - hips_r).length * 0.94
        ua = (r("upperarm01.L") - r("lowerarm01.L")).length
        fa = (r("lowerarm01.L") - arm.data.bones["lowerarm02.L"].tail_local).length
        pre = bike.geometry("tt", saddle_h, inseam)
        hip = pre["saddle"] + Vector((0.04, 0, 0.09))
        sh = hip + Vector((math.cos(math.radians(14)), 0, math.sin(math.radians(14)))) * torso
        pads = sh + Vector((0.03, 0, -ua * 0.97 - 0.04))                        # pad surface, elbows 4 cm above
        d = Vector((math.cos(math.radians(12)), 0, math.sin(math.radians(12))))  # forearms rise ~12° to the hands
        grip = pads + Vector((0, 0, 0.04)) + d * (fa * 0.99)
        aero_fit = {"pads": pads, "grip": grip, "ext": grip + d * 0.07 + Vector((0, 0, -0.035))}
    parts, pts = bike.build_bike(a.bike, a.frame or ("#c81e1e" if a.bike == "road" else "#101827"), saddle_h, inseam, aero_fit)
    print(f"fit: inseam {inseam:.3f} m, saddle height {saddle_h:.3f} m")
    # Bike bones in the rider armature
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    b_bike = eb.new("bike")
    b_bike.head, b_bike.tail = Vector((0, 0, 0)), Vector((0.3, 0, 0))            # local Y = world X → roll about X
    b_crank = eb.new("crank")
    b_crank.head, b_crank.tail = pts["bb"], pts["bb"] + Vector((0, 0.12, 0))     # local Y = world Y
    b_crank.parent = b_bike
    for side, sgn in (("L", 1), ("R", -1)):
        d = Vector((1, 0, 0)) if sgn < 0 else Vector((-1, 0, 0))
        sp = pts["bb"] + Vector((0, sgn * 0.075, 0)) + d * bike.CRANK
        p = eb.new(f"pedal.{side}")
        p.head, p.tail = sp, sp + Vector((0, 0.08, 0))
        p.parent = b_crank
    st = eb.new("steer")
    st.head, st.tail = pts["ht_bot"], pts["ht_bot"] + pts["axis_up"] * 0.2         # local Y = steering axis
    st.parent = b_bike
    for nm, c, par in (("wheel.R", pts["rear"], b_bike), ("wheel.F", pts["front"], st)):
        w = eb.new(nm)
        w.head, w.tail = c, c + Vector((0, 0.12, 0))
        w.parent = par
    eb["root"].parent = b_bike
    for b in ("bike", "crank", "pedal.L", "pedal.R", "steer", "wheel.R", "wheel.F"):
        eb[b].roll = 0.0
    bpy.ops.object.mode_set(mode="OBJECT")
    for name, bone in (("frame", "bike"), ("drivetrain_static", "bike"), ("saddle", "bike"), ("crankset", "crank"), ("pedal_L", "pedal.L"),
                       ("pedal_R", "pedal.R"), ("steer", "steer"), ("wheel_rear", "wheel.R"), ("wheel_front", "wheel.F")):
        kit._parent_to_bone(parts[name], arm, bone)
    return body, arm, helmet, glasses, parts, pts


# ---- posing ---------------------------------------------------------------------------------------------------------


class Poser:
    def __init__(self, arm, pts, kind):
        self.arm, self.pts, self.kind = arm, pts, kind
        self.position = POSITION[kind]
        r = lambda b: rest_head(arm, b)  # noqa: E731
        self.hip0 = (r("upperleg01.L") + r("upperleg01.R")) / 2
        self.thigh = (r("upperleg01.L") - r("lowerleg01.L")).length
        self.foot_len = (arm.data.bones["foot.L"].tail_local - arm.data.bones["foot.L"].head_local).length
        self.upper_arm = (r("upperarm01.L") - r("lowerarm01.L")).length
        self.forearm = (r("lowerarm01.L") - arm.data.bones["lowerarm02.L"].tail_local).length
        self.targets = {}
        self.poles = []                                                # (IK constraint, root bone, mid bone)
        for side in "LR":
            self.targets[f"ankle.{side}"] = empty(f"tgt_ankle.{side}", Vector())
            self.targets[f"ball.{side}"] = empty(f"tgt_ball.{side}", Vector())
            self.targets[f"knee.{side}"] = empty(f"pole_knee.{side}", Vector())
            self.targets[f"hand.{side}"] = empty(f"tgt_hand.{side}", Vector())
            self.targets[f"elbow.{side}"] = empty(f"pole_elbow.{side}", Vector())
            c = ik(arm, f"lowerleg02.{side}", self.targets[f"ankle.{side}"], 4, self.targets[f"knee.{side}"])
            self.poles.append((c, f"upperleg01.{side}", f"lowerleg01.{side}"))
            c = arm.pose.bones[f"foot.{side}"].constraints.new("DAMPED_TRACK")
            c.target = self.targets[f"ball.{side}"]
            if self.position == "aero":
                self.targets[f"pad.{side}"] = empty(f"tgt_pad.{side}", Vector())
                ik(arm, f"upperarm02.{side}", self.targets[f"pad.{side}"], 2, self.targets[f"elbow.{side}"])
                ik(arm, f"lowerarm02.{side}", self.targets[f"hand.{side}"], 2)
            else:
                c = ik(arm, f"lowerarm02.{side}", self.targets[f"hand.{side}"], 4, self.targets[f"elbow.{side}"])
                self.poles.append((c, f"upperarm01.{side}", f"lowerarm01.{side}"))
            # Anatomy for the solver: the MakeHuman limbs are split mid-thigh/shin/upper arm/forearm (twist bones) —
            # those joints only twist; the knee is a hinge about its lateral axis (local Z on both legs).
            for b in ("upperleg02", "lowerleg02", "upperarm02", "lowerarm02"):
                pb = arm.pose.bones[f"{b}.{side}"]
                pb.lock_ik_x = pb.lock_ik_z = True
            knee = arm.pose.bones[f"lowerleg01.{side}"]
            knee.lock_ik_x = knee.lock_ik_y = True
        self.calibrate_poles()

    def calibrate_poles(self):
        """Pole angles that make each chain bend toward its pole target. A fixed angle is not enough: the bone rolls
        MakeHuman derives from nearly straight limbs differ per side, which bent both knees toward the rider's right."""
        def bend_error(c, root, mid):
            a = head(self.arm, root)
            axis = (c.target.matrix_world.translation - a).normalized()
            perp = lambda v: (v - axis * v.dot(axis)).normalized()  # noqa: E731
            u, w = perp(head(self.arm, mid) - a), perp(c.pole_target.matrix_world.translation - a)
            return u.angle(w) * (1 if u.cross(w).dot(axis) > 0 else -1)

        for c, root, mid in self.poles:
            c.pole_angle = 0.0
        for _ in range(5):
            self.pose(0.0, "pedal")
            for c, root, mid in self.poles:
                c.pole_angle += bend_error(c, root, mid)
        self.pose(0.0, "pedal")
        print("poles:", ", ".join(f"{c.id_data.name}:{root} {math.degrees(c.pole_angle):.0f}°/{math.degrees(bend_error(c, root, mid)):+.1f}°"
                                 for c, root, mid in self.poles))

    def road_grip(self, pos):
        """Wrist centre (on the bike's centre plane) holding the hoods or the drops."""
        if pos == "drops":
            return self.pts["drops"] + Vector((-0.05, 0, 0.03))
        return self.pts["hoods"] + Vector((-0.045, 0, 0.035))

    def reset(self):
        for pb in self.arm.pose.bones:
            pb.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()

    def pose(self, phi, mode="pedal", grip=None):
        """phi: right crank angle, 0 = forward (3 o'clock), increasing in the pedalling direction. grip: hoods, drops or
        aero (default: the bike's position); out of the saddle a road rider is on the hoods."""
        arm, pts = self.arm, self.pts
        self.reset()
        standing = mode == "stand"
        coast = mode == "coast"
        pos = grip or self.position
        if standing and pos == "drops":
            pos = "hoods"
        if coast:
            phi = 0.0
        # Bike bones
        roll = math.radians(-7.0) * math.cos(phi) if standing else 0.0
        arm.pose.bones["bike"].rotation_mode = "XYZ"
        arm.pose.bones["bike"].rotation_euler = (0, roll, 0)          # about local Y = world X
        arm.pose.bones["crank"].rotation_mode = "XYZ"
        arm.pose.bones["crank"].rotation_euler = (0, phi, 0)
        bpy.context.view_layer.update()
        Rb = Matrix.Rotation(roll, 4, "X")                              # bike frame → world
        # Feet: ball of the foot on the pedal, ankling through the stroke
        for side, off in (("R", 0.0), ("L", math.pi)):
            ang = phi + off
            theta = (math.degrees(ang) + 90) % 360                      # 0 = top, clockwise seen from the drive side
            psi = math.radians(20 + 8 * math.cos(math.radians(theta - 200)) if not coast else 8)
            pb = arm.pose.bones[f"pedal.{side}"]
            pb.rotation_mode = "XYZ"
            pb.rotation_euler = (0, psi - ang, 0)
            sp = Vector(head(arm, f"pedal.{side}"))
            sgn = 1 if side == "L" else -1
            R3 = Rb.to_3x3()
            contact = sp + R3 @ Vector((0.0, sgn * 0.03, 0.028))          # cleat under the ball of the foot
            u = R3 @ Vector((math.cos(psi), 0, -math.sin(psi)))            # sole direction, heel → toe
            up = R3 @ Vector((math.sin(psi), 0, math.cos(psi)))
            ankle = contact - u * 0.125 + up * 0.055                       # ankle 12.5 cm behind, 5.5 cm above the cleat
            self.targets[f"ball.{side}"].location = ankle + u * 0.3
            self.targets[f"ankle.{side}"].location = ankle
            hip_guess = pts["saddle"] + Vector((0.0, sgn * 0.09, 0.1))
            self.targets[f"knee.{side}"].location = (hip_guess + ankle) / 2 + Rb.to_3x3() @ Vector((0.6, sgn * 0.04, 0.0))
        # Pelvis on the saddle (seated) or up and forward (standing)
        hip_target = pts["saddle"] + Vector(({"aero": 0.04, "drops": 0.02}.get(pos, 0.01), 0, 0.09))
        if standing:
            # Out of the saddle the hips move forward over the bottom bracket at about saddle height (the leg at the
            # bottom of the stroke is nearly straight), dipping onto each downstroke and swaying over the working leg
            fwd = 0.17 if pos != "aero" else 0.1                              # a TT saddle is already forward
            hip_target += Vector((fwd, 0.025 * math.sin(phi), -0.03 + 0.012 * math.cos(2 * phi)))
        elif not coast:
            hip_target += Vector((0, 0.004 * math.sin(phi), 0.003 * math.cos(2 * phi)))  # slight seated rock
        root = arm.pose.bones["root"]
        delta = hip_target - self.hip0
        root.matrix = Matrix.Translation(delta) @ root.matrix
        bpy.context.view_layer.update()
        # Undo the bike roll on the rider's pelvis (root is a child of the bike bone)
        rotate_world(arm, "root", Vector((1, 0, 0)), -roll * 0.85, pivot=hip_target)
        # Torso: pelvis tilt + distributed spine flexion to the position's torso angle
        tilt = math.radians({"aero": 45, "drops": 36}.get(pos, 30))
        rotate_world(arm, "root", Vector((0, 1, 0)), tilt, pivot=hip_target)
        spine = ["spine05", "spine04", "spine03", "spine02", "spine01"]
        weights = [0.14, 0.18, 0.22, 0.24, 0.22]
        half = pts["bar_half"]
        aero = pos == "aero" and not standing                            # TT out of the saddle: hands on the base bar
        if aero:
            elbow_c = pts["pads"] + Vector((0, 0, 0.04))
            err = lambda sh: ((sh - elbow_c).length - self.upper_arm * 0.99)  # noqa: E731  shoulders over the elbows
        elif pos == "aero":
            grip_c = pts["horns"]                                            # low and close: elbows bent, torso over the bar
            reach = (self.upper_arm + self.forearm) * 0.8
            err = lambda sh: ((sh - grip_c).length - reach)                  # noqa: E731
        else:
            grip_c = self.road_grip(pos)
            reach = (self.upper_arm + self.forearm) * (0.93 if standing else 0.88 if pos == "drops" else 0.9)
            err = lambda sh: ((sh - grip_c).length - reach)                  # noqa: E731
        for _ in range(12):
            shc = (head(arm, "upperarm01.L") + head(arm, "upperarm01.R")) / 2
            e = err(shc)
            if abs(e) < 0.004:
                break
            step = max(-0.3, min(0.3, e / 0.55))
            for b, w in zip(spine, weights):
                rotate_world(arm, b, Vector((0, 1, 0)), step * w)
        # Head up: neck extension so the eyes look ~20 m ahead
        hd = (tail(arm, "head") - head(arm, "head"))
        look = math.atan2(hd.z, hd.x)
        want = math.radians({"aero": 62, "drops": 66}.get(pos, 72))
        for k, b in enumerate(("neck01", "neck02", "neck03", "head")):
            rotate_world(arm, b, Vector((0, 1, 0)), (look - want) * 0.25)
        # Hands
        for side in "LR":
            sgn = 1 if side == "L" else -1
            sh = head(arm, f"upperarm01.{side}")
            if aero:
                pad = pts["pads"] + Vector((0, sgn * 0.1, 0.04))
                self.targets[f"pad.{side}"].location = pad
                self.targets[f"elbow.{side}"].location = pad + Vector((-0.2, sgn * 0.3, -0.3))
                bpy.context.view_layer.update()
                # Wrist exactly a forearm from where the elbow landed, aimed at the extension end
                el = tail(arm, f"upperarm02.{side}")
                want = pts["grip"] + Vector((0, sgn * 0.065, 0))
                self.targets[f"hand.{side}"].location = el + (want - el).normalized() * self.forearm * 0.995
            elif pos == "aero":
                grip = Rb @ (pts["horns"] + Vector((0, sgn * half, 0)))
                el = elbow_point(sh, grip, self.upper_arm, self.forearm, Vector((-0.3, sgn * 0.6, -0.5)))
                self.targets[f"pad.{side}"].location = el
                self.targets[f"elbow.{side}"].location = el + Vector((-0.2, sgn * 0.3, -0.3))
                self.targets[f"hand.{side}"].location = grip
            else:
                grip = self.road_grip(pos) + Vector((0, sgn * half, 0))
                self.targets[f"hand.{side}"].location = Rb @ grip
                self.targets[f"elbow.{side}"].location = sh + Vector((-0.15, sgn * 0.45, -0.35))
        bpy.context.view_layer.update()
        # Fingers wrap the bar
        for side in "LR":
            for f in range(1, 6):
                for seg in (1, 2, 3):
                    b = f"finger{f}-{seg}.{side}"
                    if b in arm.pose.bones:
                        pb = arm.pose.bones[b]
                        pb.rotation_mode = "XYZ"
                        curl = {"aero": 56, "drops": 50}.get(pos, 42) if f > 1 else {"aero": 26}.get(pos, 18)
                        pb.rotation_euler = (math.radians(curl), 0, 0)
        bpy.context.view_layer.update()


def bake_clip(arm, poser, name, mode, frames, grip=None):
    """Pose every frame (targets + bike bones keyed), then bake visual transforms into an action. Cyclic clips get a
    closing key (frame `frames` = frame 0, one revolution later) so clip time maps linearly onto the crank angle."""
    scene = bpy.context.scene
    last = frames if frames > 2 else frames - 1
    scene.frame_start, scene.frame_end = 0, last
    arm.animation_data_create()
    arm.animation_data.action = None
    for o in poser.targets.values():
        o.animation_data_clear()
    for f in range(last + 1):
        phi = f / frames * 2 * math.pi
        scene.frame_set(f)
        poser.pose(phi, mode, grip)
        for o in poser.targets.values():
            o.keyframe_insert("location", frame=f)
        for b in ("bike", "crank", "pedal.L", "pedal.R", "root") + tuple(n for n in arm.pose.bones.keys() if n.startswith(("spine", "neck", "head", "finger"))):
            pb = arm.pose.bones[b]
            pb.keyframe_insert("location", frame=f)
            pb.keyframe_insert("rotation_quaternion" if pb.rotation_mode == "QUATERNION" else "rotation_euler", frame=f)
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.select_all(action="SELECT")
    bpy.ops.nla.bake(frame_start=0, frame_end=last, only_selected=False, visual_keying=True, clear_constraints=False,
                     use_current_action=False, bake_types={"POSE"})
    bpy.ops.object.mode_set(mode="OBJECT")
    act = arm.animation_data.action
    act.name = name
    act.use_fake_user = True
    # Push down to an NLA track so the exporter sees each clip
    tr = arm.animation_data.nla_tracks.new()
    tr.name = name
    tr.strips.new(name, 0, act)
    arm.animation_data.action = None
    return act


def main():
    a = args()
    os.makedirs(a.out, exist_ok=True)
    body, arm, helmet, glasses, parts, pts = build(a)
    poser = Poser(arm, pts, a.bike)
    clips = [("pedal", "pedal", FRAMES, None), ("stand", "stand", FRAMES, None), ("coast", "coast", 2, None)]
    if a.bike == "road":  # the start screen offers road on the hoods or in the drops
        clips += [("pedal_drops", "pedal", FRAMES, "drops"), ("coast_drops", "coast", 2, "drops")]
    for name, mode, n, grip in clips:
        bake_clip(arm, poser, name, mode, n, grip)
    # Remove the posing helpers
    for pb in arm.pose.bones:
        for c in list(pb.constraints):
            pb.constraints.remove(c)
    for o in poser.targets.values():
        bpy.data.objects.remove(o)
    out = os.path.join(a.out, f"rider_{a.bike}")
    bpy.ops.wm.save_as_mainfile(filepath=out + ".blend", compress=True)
    if a.render:
        preview(arm, out)
        for o in [o for o in bpy.data.objects if o.type == "CAMERA" or o.type == "LIGHT"]:
            bpy.data.objects.remove(o)
        preview(arm, out + "_stand", "stand", 12)
        for o in [o for o in bpy.data.objects if o.type == "CAMERA" or o.type == "LIGHT"]:
            bpy.data.objects.remove(o)
    if not a.no_export:
        bpy.ops.object.select_all(action="DESELECT")
        bpy.ops.export_scene.gltf(filepath=out + ".glb", export_format="GLB", export_yup=True, export_apply=True, export_skins=True,
                                  export_animations=True, export_animation_mode="NLA_TRACKS", export_force_sampling=True,
                                  export_frame_range=False, export_extras=True, export_image_format="AUTO")
        print(f"rider: {out}.glb ({os.path.getsize(out + '.glb') / 1e6:.1f} MB)")


def preview(arm, out, clip="pedal", frame=10):
    import render_common as rc

    scene = bpy.context.scene
    tr = arm.animation_data.nla_tracks[clip]
    for t in arm.animation_data.nla_tracks:
        t.mute = t is not tr
    arm.animation_data.action = None
    scene.frame_set(frame)
    rc.sky_and_sun(42, 210)
    rc.camera((0.45, -3.0, 1.05), (0.25, 0, 0.85), lens=42)
    rc.render(out + "_side.jpg", 1200, 900, 32)
    cam = scene.camera
    cam.location = (2.5, -2.0, 1.6)
    cam.rotation_euler = (Vector((0.2, 0, 0.9)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    rc.render(out + "_34.jpg", 1200, 900, 32)
    for t in arm.animation_data.nla_tracks:
        t.mute = False


if __name__ == "__main__":
    main()
