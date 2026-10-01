import { G } from "./constants";
import { cdaAtYaw, effectiveMass, RiderProfile, totalMass } from "./rider";

/** Local conditions the equation of motion needs at one instant. */
export interface Conditions {
  /** Road grade as a fraction (0.08 = 8 %). */
  grade: number;
  /** Rolling resistance multiplier from the surface (1 = smooth asphalt). */
  crrMultiplier: number;
  /** Extra multiplier for wet roads (1.05 when wet, else 1). */
  wetFactor: number;
  /** Air density, kg/m³. */
  rho: number;
  /** Wind component against the direction of travel at rider height, m/s (positive = headwind). */
  wHead: number;
  /** Crosswind component at rider height, m/s. */
  wCross: number;
}

export const CALM_FLAT: Conditions = { grade: 0, crrMultiplier: 1, wetFactor: 1, rho: 1.225, wHead: 0, wCross: 0 };

export interface Forces {
  grav: number;
  roll: number;
  aero: number;
  yawRad: number;
}

/** Resistive forces (N) at speed v (m/s). */
export function resistiveForces(r: RiderProfile, c: Conditions, v: number): Forces {
  const theta = Math.atan(c.grade);
  const m = totalMass(r);
  const grav = m * G * Math.sin(theta);
  const roll = r.crrBase * c.crrMultiplier * c.wetFactor * m * G * Math.cos(theta);
  const vAx = v + c.wHead;
  const vApp = Math.hypot(vAx, c.wCross);
  const yawRad = Math.atan2(c.wCross, vAx);
  const aero = 0.5 * c.rho * cdaAtYaw(r, yawRad) * vApp * vAx;
  return { grav, roll, aero, yawRad };
}

/** Acceleration (m/s²) given power at the pedals (W), speed and an optional braking force (N). */
export function acceleration(r: RiderProfile, c: Conditions, powerW: number, v: number, brakeN = 0): number {
  const f = resistiveForces(r, c, v);
  const drive = (r.drivetrainEfficiency * powerW) / Math.max(v, 0.5);
  return (drive - f.grav - f.roll - f.aero - brakeN) / effectiveMass(r);
}

/** Power needed at the pedals (W) to hold speed v steady. */
export function powerForSpeed(r: RiderProfile, c: Conditions, v: number): number {
  const f = resistiveForces(r, c, v);
  return (Math.max(f.grav + f.roll + f.aero, 0) * v) / r.drivetrainEfficiency;
}

/**
 * Steady-state speed (m/s) for a constant power. Solves η·P = v·ΣF(v) by bisection.
 * Returns 0 if the rider cannot move forward (e.g. 0 W uphill).
 */
export function steadyStateSpeed(r: RiderProfile, c: Conditions, powerW: number): number {
  const net = (v: number) => r.drivetrainEfficiency * powerW - v * sumForces(r, c, v);
  let lo = 0;
  let hi = 40;
  // Coasting downhill: net(v) = -v·ΣF, so find root of ΣF instead.
  if (powerW <= 0) {
    if (sumForces(r, c, 0.01) >= 0) return 0;
    const f = (v: number) => sumForces(r, c, v);
    while (f(hi) < 0 && hi < 200) hi *= 2;
    for (let i = 0; i < 80; i++) {
      const mid = (lo + hi) / 2;
      if (f(mid) < 0) lo = mid;
      else hi = mid;
    }
    return (lo + hi) / 2;
  }
  while (net(hi) > 0 && hi < 200) hi *= 2;
  for (let i = 0; i < 80; i++) {
    const mid = (lo + hi) / 2;
    if (net(mid) > 0) lo = mid;
    else hi = mid;
  }
  return (lo + hi) / 2;
}

function sumForces(r: RiderProfile, c: Conditions, v: number): number {
  const f = resistiveForces(r, c, v);
  return f.grav + f.roll + f.aero;
}

/** One semi-implicit Euler step. Returns the new speed (clamped ≥ 0). */
export function integrateSpeed(r: RiderProfile, c: Conditions, powerW: number, v: number, dt: number, brakeN = 0): number {
  const a = acceleration(r, c, powerW, v, brakeN);
  return Math.max(0, v + a * dt);
}
