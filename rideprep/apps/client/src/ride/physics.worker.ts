/// <reference lib="webworker" />
import { airDensity, CourseProfile, DEFAULT_CORNERING, RideSimulator, WeatherField, WindLayers, WindLayerName, WindModel, Environment, WindAtRider } from "@rideprep/physics";
import { PhysicsState, ToWorker } from "./protocol";

/**
 * Deterministic 50 Hz physics in a Web Worker: the app's single source of truth for virtual speed.
 * A wall-clock accumulator drives fixed 20 ms steps; the main thread interpolates for rendering.
 */
let sim: RideSimulator | undefined;
let wind: WindModel | undefined;
let lastWind: WindAtRider | undefined;
let paused = false;
let acc = 0;
let last = 0;
let timer: ReturnType<typeof setInterval> | undefined;
let startEpoch = 0;

const ctx = self as unknown as DedicatedWorkerGlobalScope;

ctx.onmessage = (e: MessageEvent<ToWorker>) => {
  const m = e.data;
  switch (m.type) {
    case "init": {
      const course: CourseProfile = m.route;
      const layers = new WindLayers(m.wind.data, m.wind.count, m.wind.spacingM, m.wind.bins, m.wind.layers as WindLayerName[]);
      wind = new WindModel(layers, new WeatherField(m.weather), { seed: m.seed, gusts: m.gusts });
      startEpoch = m.startEpoch;
      const env: Environment = {
        at(s, tEpoch, heading, elevation, dt = 0.02) {
          const w = wind!.step(s, tEpoch, heading, dt);
          lastWind = w;
          return {
            rho: airDensity({ tempC: w.weather.tempC, rh: w.weather.rh, pMslHpa: w.weather.pMslHpa, elevationM: elevation }),
            wHead: w.wHead, wCross: w.wCross, wet: w.weather.precipMmH > 0.2, tempC: w.weather.tempC, uRider: w.uRider, shelter: w.factors.shelter,
          };
        },
      };
      sim = new RideSimulator(course, m.rider, env, { startEpoch, cornering: { ...DEFAULT_CORNERING, enabled: m.cornering } });
      if (m.startS) sim.state.s = m.startS;
      paused = false;
      acc = 0;
      last = performance.now();
      if (timer) clearInterval(timer);
      timer = setInterval(tick, 10);
      break;
    }
    case "power":
      sim?.setPower(m.watts);
      break;
    case "pause":
      paused = true;
      break;
    case "resume":
      paused = false;
      last = performance.now();
      break;
    case "weather":
      if (wind) wind.weather = new WeatherField(m.weather);
      break;
  }
};

function tick() {
  if (!sim) return;
  const now = performance.now();
  const dt = (now - last) / 1000;
  last = now;
  if (paused || sim.state.finished) return;
  acc += Math.min(dt, 0.25);
  let stepped = false;
  while (acc >= sim.dt) {
    sim.step();
    acc -= sim.dt;
    stepped = true;
  }
  if (stepped) post(now);
}

function post(wall: number) {
  const st = sim!.state;
  const w = lastWind!;
  const msg: PhysicsState = {
    type: "state", t: st.t, wall, s: st.s, v: st.v, powerW: st.powerW, braking: st.braking, brakingTimeS: st.brakingTimeS,
    leanRad: st.leanRad, gradePct: st.sample.grade * 100, crrEff: sim!.rider.crrBase * st.sample.crrMultiplier * (st.env.wet ? 1.05 : 1),
    rho: st.env.rho, tempC: st.env.tempC, wet: st.env.wet, finished: st.finished,
    wind: { u10: w.u10, dir10: w.dir10, uRider: w.uRider, dirRider: w.dirRider, wHead: w.wHead, wCross: w.wCross, gust: w.gust, shelter: w.factors.shelter, fRough: w.factors.fRough },
    weather: { rh: w.weather.rh, cloudCover: w.weather.cloudCover, visibilityM: w.weather.visibilityM, precipMmH: w.weather.precipMmH, pMslHpa: w.weather.pMslHpa },
  };
  ctx.postMessage(msg);
}
