import { CourseProfile } from "@rideprep/physics";

export type RoadLine = "keepRight" | "racing";
type Route = CourseProfile & { roadWidthM: Uint8Array };

const G = 9.81;

/**
 * Where the bike is across the road. A trainer reports speed, not steering, so the rider cannot choose a line: this
 * holds a realistic one inside the road "box" and moves the bike there the way a rider drifts across.
 *  - keepRight (open roads; the default): about 1 m from the right edge, a little tighter on the inside of
 *    right-handers and back toward the lane centre on left-handers, never over the centre line.
 *  - racing (closed roads): the whole width — the right side between bends, the inside of each bend, set up ~1.5 s ahead.
 * A critically damped spring moves the bike, with caps on lateral acceleration and on lateral speed (a bike only moves
 * sideways by pointing that way, so it is also limited by forward speed); the resulting yaw and lean are returned.
 * Below ~11 km/h a pedal-synchronous weave appears, as on steep climbs. Lengths in m (+ = right of the route
 * centreline), angles in rad (+ = right).
 */
export class LaneKeeper {
  /** Lateral offset from the route centreline. */
  offset = 0;
  /** Bike heading relative to the road. */
  yaw = 0;
  /** Extra lean from lateral acceleration. */
  lean = 0;
  private base = 0;
  private vel = 0;
  private weave = 0;
  private started = false;
  /** Cumulative heading change (unwrapped) per route sample. */
  private turn: Float32Array;

  constructor(private c: Route, public line: RoadLine = "keepRight") {
    this.turn = new Float32Array(c.count);
    for (let i = 1; i < c.count; i++) {
      const d = c.headingRad[i] - c.headingRad[i - 1];
      this.turn[i] = this.turn[i - 1] + Math.atan2(Math.sin(d), Math.cos(d));
    }
  }

  private idx(s: number): number {
    return Math.min(this.c.count - 1, Math.max(0, Math.round(s / this.c.spacingM)));
  }

  /** Mean signed curvature over s ± w (1/m, + = bending right). */
  curvature(s: number, w: number): number {
    const a = this.idx(s - w);
    const b = this.idx(s + w);
    return b > a ? (this.turn[b] - this.turn[a]) / ((b - a) * this.c.spacingM) : 0;
  }

  /** The line a rider would hold at s, riding at v m/s. */
  target(s: number, v: number): number {
    const hw = this.c.roadWidthM[this.idx(s)] / 2;
    if (hw < 1.6) return 0; // a single lane or a path: the middle
    const k = this.curvature(s + Math.max(5, v * 1.5), 15);
    const sharp = Math.min(1, Math.abs(k) * 40); // 0 on straights … 1 at R ≤ 40 m
    if (this.line === "racing") {
      const room = hw - 0.6;
      return room * (0.5 * (1 - sharp) + Math.sign(k) * sharp);
    }
    const lane = hw / 2; // right-lane centre
    const edge = Math.max(lane, hw - 1.0); // ~1 m off the right edge
    const t = k > 0 ? edge + (hw - 0.7 - edge) * sharp : edge + (lane - edge) * sharp;
    return Math.max(0.3, Math.min(hw - 0.5, t));
  }

  /** Advance by dt at route distance s, speed v (m/s) and crank angle (rad). */
  update(dt: number, s: number, v: number, crankRad: number): void {
    const goal = this.target(s, v);
    if (!this.started || dt <= 0) {
      this.started = true;
      this.base = goal;
      this.offset = goal;
      return;
    }
    const w = 1.3; // rad/s: a line change settles in ~3 s
    const acc = Math.max(-1.2, Math.min(1.2, w * w * (goal - this.base) - 2 * w * this.vel));
    this.vel += acc * dt;
    const vMax = Math.min(1.0, 0.18 * v);
    this.vel = Math.max(-vMax, Math.min(vMax, this.vel));
    this.base += this.vel * dt;
    // Slow climbing: the bike weaves a little with each pedal stroke
    const slow = Math.max(0, Math.min(1, (3 - v) / 1.8)) * (v > 0.3 ? 1 : 0);
    const weave = slow * 0.035 * Math.sin(crankRad);
    const weaveVel = (weave - this.weave) / dt;
    this.weave = weave;
    this.offset = this.base + weave;
    this.yaw = v > 0.5 ? Math.max(-0.12, Math.min(0.12, Math.atan2(this.vel + weaveVel, v))) : 0;
    this.lean += (Math.atan(acc / G) - this.lean) * Math.min(1, dt / 0.35); // a rider eases into the lean
  }

  /** Jump straight to the line at s (teleports, restarts). */
  reset(): void {
    this.started = false;
    this.vel = 0;
    this.weave = 0;
    this.yaw = 0;
    this.lean = 0;
  }
}
