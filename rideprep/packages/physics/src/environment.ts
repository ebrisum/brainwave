import { airDensity } from "./airDensity";
import { WindModel } from "./wind/runtime";

export interface EnvSample {
  rho: number;
  wHead: number;
  wCross: number;
  wet: boolean;
  tempC: number;
  uRider: number;
  shelter: number;
}

/** Everything outside the rider that the equation of motion needs at (s, t). */
export interface Environment {
  at(s: number, tEpoch: number, headingRad: number, elevationM: number, dt?: number): EnvSample;
}

/** Wet when it rained more than this (mm/h) in the current hour. */
export const WET_THRESHOLD_MM_H = 0.2;

/** Environment backed by the wind model and the weather field. With `gusts`, `dt` advances the OU processes. */
export function windEnvironment(model: WindModel, gusts = false): Environment {
  return {
    at(s, tEpoch, headingRad, elevationM, dt = 0.02) {
      const w = gusts ? model.step(s, tEpoch, headingRad, dt) : model.mean(s, tEpoch, headingRad);
      const rho = airDensity({ tempC: w.weather.tempC, rh: w.weather.rh, pMslHpa: w.weather.pMslHpa, elevationM });
      return {
        rho, wHead: w.wHead, wCross: w.wCross, wet: w.weather.precipMmH > WET_THRESHOLD_MM_H,
        tempC: w.weather.tempC, uRider: w.uRider, shelter: w.factors.shelter,
      };
    },
  };
}

/** Constant environment (tests, calm flat). */
export function constantEnvironment(e: Partial<EnvSample> = {}): Environment {
  const v: EnvSample = { rho: 1.225, wHead: 0, wCross: 0, wet: false, tempC: 15, uRider: 0, shelter: 1, ...e };
  return { at: () => v };
}
