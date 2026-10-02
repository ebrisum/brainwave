# Rider and bike (`tools/rider`)

Builds the rigged cyclist the web client rides with (`apps/client/public/models/rider_road.glb`, `rider_tt.glb`) and a
`.blend` per bike for artists and Unreal.

```sh
sh tools/rider/fetch_makehuman.sh .cache/makehuman            # CC0 base mesh, skeleton, weights, body targets
blender -b --factory-startup --python tools/rider/build_rider.py -- \
    --mh .cache/makehuman --out .cache/rider --bike road [--variant male|female] [--jersey "#f0b429"] [--frame "#c81e1e"] [--render]
cp .cache/rider/rider_road.glb apps/client/public/models/      # and the same with --bike tt
```

| File | What it does |
|---|---|
| `mh.py` | MakeHuman hm08 loader: targets → morphed body, 163-bone skeleton reduced to a 74-bone real-time rig (face, toes merged), skin weights |
| `kit.py` | Cycling kit by bone regions with straight hems (bisect cuts), helmet, glasses, shoes, materials |
| `bike.py` | Procedural road or TT bike sized to the rider's inseam (stack/reach, head/seat angles, fork rake), fit points |
| `build_rider.py` | Fit (saddle height 0.883 × inseam, TT cockpit fitted to the arms), one armature for rider and bike, IK posing, clip bake, export |

**Fit.** The inseam is measured on the morphed body (crotch height); the frame grows with it and the saddle sits at
0.883 × inseam above the bottom bracket. On the TT bike the pads go under the elbows (torso ≈ 14°) and the
extensions end one forearm ahead, so the hands close round them.

**Posing.** IK on both legs (ankle on the pedal with ankling through the stroke, foot aimed by a damped track) and the
arms (hoods, drops, or pads + extensions). The MakeHuman limbs are split mid-thigh/shin/upper arm/forearm; those joints
only twist, the knee is a hinge about its lateral axis, and every pole angle is calibrated per chain at build time (a
fixed angle bent both knees toward the rider's right because the rolls MakeHuman derives from straight limbs differ
per side). The torso flexes iteratively until the shoulders sit at the grip's reach; the neck extends so the eyes look
down the road. Out of the saddle the hips move forward over the bottom bracket at about saddle height and the bike
rocks ±7° under the rider.

**Clips** (glTF animations, 24 fps): `pedal`, `stand` (48 frames + a closing key = one crank revolution), `coast`, and
`pedal_drops`/`coast_drops` on the road bike. The client sets clip time from the crank angle (0 = right crank forward),
spins `wheel.F`/`wheel.R`, leans the whole model and turns `steer` a little through bends.

**Checking.** `apps/client/rider-lab.html` (dev server) shows the model on a plain backdrop at an exact crank angle,
clip mix, lean and view (`?bike=road&pos=drops&view=back&deg=90&stand=0.5`), the way the chase camera sees it.

**Unreal.** Import `rider_<bike>.glb` (or the `.blend` via FBX) as a skeletal mesh with its animations; the same
bones drive the bike. For a photoreal rider, retarget the body clips to a MetaHuman with an IK Retargeter (map this
rig's spine/arm/leg chains to the MetaHuman chains) and keep this rig's bike bones for the bike.
