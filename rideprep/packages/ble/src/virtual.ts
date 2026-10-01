import { BleAdapter, BleDevice, DeviceFilter } from "./adapter";
import { encodeCyclingPower, encodeHeartRate, encodeIndoorBikeData } from "./encoders";
import { OP, RESULT } from "./ftms";
import { CHARS, SERVICES } from "./uuids";

export interface RiderScript {
  power(tS: number): number;
  heartRate(tS: number): number;
  cadence(tS: number): number;
}

/** A steady rider with a little noise and a periodic surge — handy for demos. */
export const demoRider = (ftp = 250): RiderScript => ({
  power: (t) => Math.max(0, ftp * 0.8 + 25 * Math.sin(t / 7) + (Math.floor(t / 180) % 4 === 3 ? 60 : 0)),
  heartRate: (t) => Math.round(120 + 30 * (1 - Math.exp(-t / 300)) + 4 * Math.sin(t / 11)),
  cadence: (t) => 88 + 4 * Math.sin(t / 13),
});

export interface VirtualDeviceOptions {
  script?: RiderScript;
  rateHz?: number;
  /** Respond 0x02 (not supported) to 0x11 to exercise the fallback path. */
  rejectSimulation?: boolean;
  services?: string[];
}

/** Simulated trainer + power meter + HR strap. Accepts and logs FTMS control-point commands. */
export class VirtualDevice implements BleDevice {
  id = "virtual-1";
  name = "RidePrep Virtual Rider";
  connected = false;
  readonly commands: number[][] = [];
  private subs = new Map<string, ((dv: DataView) => void)[]>();
  private timer?: ReturnType<typeof setInterval>;
  private t0 = 0;
  private crankRevs = 0;
  private crankTicks = 0;
  private disconnectCbs: (() => void)[] = [];
  private script: RiderScript;
  private services: string[];

  constructor(private opts: VirtualDeviceOptions = {}) {
    this.script = opts.script ?? demoRider();
    this.services = opts.services ?? [SERVICES.ftms, SERVICES.cyclingPower, SERVICES.heartRate];
  }

  async connect() {
    this.connected = true;
    this.t0 = Date.now();
    const period = 1000 / (this.opts.rateHz ?? 4);
    this.timer = setInterval(() => this.emit((Date.now() - this.t0) / 1000, period / 1000), period);
  }

  async disconnect() {
    this.connected = false;
    if (this.timer) clearInterval(this.timer);
    this.disconnectCbs.forEach((cb) => cb());
  }

  /** Simulate a radio dropout. */
  drop() { void this.disconnect(); }

  onDisconnect(cb: () => void) { this.disconnectCbs.push(cb); }

  async hasService(s: string) { return this.services.includes(s); }

  async subscribe(service: string, characteristic: string, cb: (dv: DataView) => void) {
    const k = `${service}/${characteristic}`;
    this.subs.set(k, [...(this.subs.get(k) ?? []), cb]);
  }

  async write(service: string, characteristic: string, data: Uint8Array) {
    if (characteristic !== CHARS.ftmsControlPoint) return;
    this.commands.push(Array.from(data));
    const op = data[0];
    const result = op === OP.setIndoorBikeSimulation && this.opts.rejectSimulation ? RESULT.notSupported : RESULT.success;
    queueMicrotask(() => this.notify(SERVICES.ftms, CHARS.ftmsControlPoint, Uint8Array.of(OP.response, op, result)));
  }

  private notify(service: string, ch: string, bytes: Uint8Array) {
    const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    for (const cb of this.subs.get(`${service}/${ch}`) ?? []) cb(dv);
  }

  /** Emit one round of sensor notifications for elapsed time t (s). */
  emit(t: number, dt: number) {
    const P = this.script.power(t);
    const hr = this.script.heartRate(t);
    const cad = this.script.cadence(t);
    // Crank event time = when the last full revolution completed (not the notification time)
    const before = Math.floor(this.crankRevs);
    this.crankRevs += (cad / 60) * dt;
    const after = Math.floor(this.crankRevs);
    if (after > before && cad > 0) {
      const frac = this.crankRevs - after; // revolutions since the last completed one
      const eventT = t - frac / (cad / 60);
      this.crankTicks = Math.round(eventT * 1024) & 0xffff;
    }
    if (this.services.includes(SERVICES.ftms))
      this.notify(SERVICES.ftms, CHARS.indoorBikeData, encodeIndoorBikeData({ speedKmh: 30, cadenceRpm: cad, powerW: P }));
    if (this.services.includes(SERVICES.cyclingPower))
      this.notify(SERVICES.cyclingPower, CHARS.cyclingPowerMeasurement,
        encodeCyclingPower({ powerW: P, crankRevs: Math.floor(this.crankRevs), crankEventTicks: this.crankTicks }));
    if (this.services.includes(SERVICES.heartRate))
      this.notify(SERVICES.heartRate, CHARS.heartRateMeasurement, encodeHeartRate(hr, [60 / hr]));
  }
}

export class VirtualDeviceAdapter implements BleAdapter {
  constructor(private opts: VirtualDeviceOptions = {}) {}
  async isAvailable() { return true; }
  async requestDevice(_filter: DeviceFilter): Promise<BleDevice> { return new VirtualDevice(this.opts); }
}
