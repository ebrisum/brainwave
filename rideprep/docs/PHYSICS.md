# Physics model (`packages/physics`)

The app's physics computes virtual speed; the trainer only provides resistance feel and measured power.

## Rider profile (defaults, `src/rider.ts`)
| Parameter | Default |
|---|---|
| Rider mass | 75 kg |
| Bike + kit | 8.5 kg |
| CdA | hoods 0.34 / drops 0.30 / aero 0.24 m² (optional CdA(yaw) table, linear in |yaw|) |
| Tyre Crr | 0.0040 (× surface multiplier, × 1.05 when wet) |
| Drivetrain efficiency η | 0.975 |
| Wheel inertia | 0.14 kg·m², radius 0.335 m → +1.25 kg effective mass |
| FTP / W′ | 280 W / 20 kJ (user-set) |

## Equation of motion (`src/motion.ts`), fixed 50 Hz (`src/simulator.ts`)
```
θ = atan(grade);  m = m_rider + m_bike;  m_eff = m + I/r²
F_grav = m·g·sinθ
F_roll = Crr·crrMultiplier(s)·wetFactor·m·g·cosθ
V_ax = v + w_head;  V_app = √(V_ax² + w_cross²);  β = atan2(w_cross, V_ax)
F_aero = ½·ρ·CdA(β)·V_app·V_ax
dv/dt = (η·P / max(v, 0.5) − F_grav − F_roll − F_aero − F_brake) / m_eff
```
Semi-implicit Euler, `v ≥ 0`, g = 9.80665. Power is held 3 s on dropout, then ramped to 0 over 2 s.
The steady-state solver (`steadyStateSpeed`) bisects `η·P = v·ΣF(v)` (or `ΣF = 0` when coasting).

Test vectors (spec §16.1) — rider 75 + 8 kg, CdA 0.32, Crr 0.004, η 0.975, ρ 1.225:
flat 200 W → 9.43 m/s; 8 % 300 W → 4.09 m/s; flat 200 W into 5 m/s headwind → 6.59 m/s (all ±0.5 %).

## Air density (`src/airDensity.ts`)
Station pressure from MSL pressure (barometric formula), Tetens saturation pressure, moist-air density
`ρ = p_d/(R_d·T) + p_v/(R_v·T)` with R_d = 287.05, R_v = 461.495. 20 °C, 1013.25 hPa, RH 0 → 1.204 kg/m³.

## Cornering (`src/cornering.ts`)
`v_max = √(a_lat·r)`, a_lat = 0.55 g dry / 0.35 g wet. Looking 200 m ahead, brake at a = 0.5 g dry / 0.3 g wet when
the speed after braking over the remaining distance would exceed the corner limit; `F_brake = m_eff·a_brake`. Lean
angle `atan(v²/(g·r))`. Braking time is reported (HUD indicator, ride metric, predictor).

## Predictor (`src/predictor.ts`)
Same equation and cornering rules at 1 Hz over the whole course, no gusts. Outputs total time, per-sample cumulative
time (any split: climbs, laps, 5 km), kJ and braking time. 180 km in ~70 ms (budget 1 s).

## Pacing optimiser (`src/optimizer.ts`)
500 m segments. Minimise Σ tᵢ(Pᵢ) subject to NP ≤ target (time-weighted 4th-power mean of segment powers) and
Pᵢ ∈ [0.8, 1.15]·target. The problem is separable with a Lagrange multiplier λ: each segment minimises
`kᵢ·tᵢ(P) + λ·kᵢ·tᵢ(P)·((P/NP)⁴ − 1)` by golden-section on a tabulated steady-state time curve (`kᵢ` calibrates
steady state to the full predictor at the baseline). λ is found by bisection; if the W′-balance floor (default 20 %
of W′, Skiba differential model) is violated, caps above CP are tightened and the solve repeats. The final plan is
verified with the full predictor. Result: more power on climbs and into headwinds, less on descents/tailwinds.
180 km in ~0.4 s (budget 10 s).

## Scenarios (`src/scenarios.ts`)
Calm (U10 = 1 m/s), Most likely (modal direction, P50), Windy (modal, P90), Worst case (the 16-bin direction that
maximises predicted time at P75). Route exposure per 500 m: head/cross/tail/sheltered shares and mean U_rider.

## Metrics (`packages/metrics`)
NP (30 s rolling, 4th power), IF, TSS, VI, kJ, W′ balance (Skiba differential), Coggan power zones, HR zones,
aerobic decoupling (Pa:HR), best averages, split times, actual vs planned per segment. Exports: FIT (Garmin FIT
JavaScript SDK, developer fields `u_rider`, `w_head`, `shelter`, `air_density`), TCX (ActivityExtension v2 watts),
GPX (TrackPointExtension hr/cad + `<power>`).
