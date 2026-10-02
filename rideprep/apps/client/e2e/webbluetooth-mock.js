/*
 * Web Bluetooth emulator for end-to-end tests (Playwright `addInitScript`). Emulates, at the GATT level, the three
 * devices a typical indoor setup has — so the app's real Web Bluetooth code path runs unchanged:
 *
 *   "KICKR CORE (emulated)"   Fitness Machine Service 0x1826: Indoor Bike Data 0x2AD2 (4 Hz notifications),
 *                             Control Point 0x2AD9 (writes answered with 0x80 indications), Feature 0x2ACC.
 *   "HRM-Pro (emulated)"      Heart Rate 0x180D: Heart Rate Measurement 0x2A37 (1 Hz).
 *   "Assioma Duo (emulated)"  Cycling Power 0x1818: Cycling Power Measurement 0x2A63 with crank data (4 Hz).
 *
 * The emulated rider pushes harder on climbs and eases off downhill; the trainer applies the simulation parameters it
 * receives (grade, wind, Crr, Cw) to compute its flywheel speed, exactly like a smart trainer's resistance model.
 * Everything the app writes is logged in `window.__ble.log` ({t, op, gradePct, windMs, crr, cw}).
 */
(() => {
  const u16 = (n) => `0000${n.toString(16).padStart(4, "0")}-0000-1000-8000-00805f9b34fb`;
  const norm = (x) => (typeof x === "number" ? u16(x) : String(x).toLowerCase());
  const state = {
    t0: performance.now(), log: [], sim: { gradePct: 0, windMs: 0, crr: 0.004, cw: 0.36 }, erg: null,
    powerW: 0, cadence: 0, speedKmh: 0, hr: 95, crankRevs: 0, crankTime: 0, controlled: false,
  };
  window.__ble = state;

  // Rider model: holds ~210 W on the flat, +9 W per % uphill, eases off on descents; cadence drops on climbs.
  function riderPower() {
    if (state.erg !== null) return state.erg;
    const g = state.sim.gradePct;
    const base = 210 + (g > 0 ? 9 * g : 28 * g);
    return Math.max(40, base + 6 * Math.sin((performance.now() - state.t0) / 1700));
  }
  // Trainer: steady speed where rider power = gravity + rolling + air (with the simulated headwind).
  function trainerSpeed(p) {
    const m = 83, g = 9.81, grade = state.sim.gradePct / 100;
    const fixed = m * g * (Math.sin(Math.atan(grade)) + state.sim.crr * Math.cos(Math.atan(grade)));
    let lo = 0.3, hi = 40;
    for (let i = 0; i < 50; i++) {
      const v = (lo + hi) / 2;
      const need = (fixed + 0.5 * state.sim.cw * (v + state.sim.windMs) * Math.abs(v + state.sim.windMs)) * v; // FTMS Cw = ρ·CdA
      if (need > p) hi = v; else lo = v;
    }
    return lo;
  }
  setInterval(() => {
    state.powerW = riderPower();
    state.cadence = Math.max(60, 90 - Math.max(0, state.sim.gradePct) * 1.4);
    state.speedKmh = trainerSpeed(state.powerW) * 3.6;
    state.hr += ((105 + (state.powerW - 120) * 0.32) - state.hr) * 0.04;
    // Crank events: a power meter reports the cumulative revolutions and the time (1/1024 s) of the LAST full revolution
    const dt = 0.25;
    state.phase = (state.phase ?? 0) + (state.cadence / 60) * dt;
    state.clock = (state.clock ?? 0) + dt;
    while (state.phase >= 1) {
      state.phase -= 1;
      state.crankRevs += 1;
      state.crankTime = (state.clock - state.phase / (state.cadence / 60)) * 1024;
    }
  }, 250);

  class Char extends EventTarget {
    constructor(uuid, opts) { super(); this.uuid = uuid; this.opts = opts || {}; this.notifying = false; this.value = null; }
    async startNotifications() {
      this.notifying = true;
      if (this.opts.period) this.timer = setInterval(() => this.emit(this.opts.produce()), this.opts.period);
      return this;
    }
    async stopNotifications() { this.notifying = false; clearInterval(this.timer); return this; }
    emit(bytes) {
      if (!this.notifying) return;
      this.value = new DataView(new Uint8Array(bytes).buffer);
      const ev = new Event("characteristicvaluechanged");
      Object.defineProperty(ev, "target", { value: this });
      this.dispatchEvent(ev);
    }
    async readValue() { return new DataView(new Uint8Array(this.opts.read ? this.opts.read() : [0]).buffer); }
    async writeValueWithResponse(buf) { return this.opts.write ? this.opts.write(new Uint8Array(buf instanceof ArrayBuffer ? buf : buf.buffer)) : undefined; }
    async writeValueWithoutResponse(buf) { return this.writeValueWithResponse(buf); }
    async writeValue(buf) { return this.writeValueWithResponse(buf); }
  }

  const le16 = (v) => [v & 0xff, (v >> 8) & 0xff];
  const s16 = (v) => le16(v < 0 ? 0x10000 + v : v);

  function makeTrainer() {
    let cp;
    const ibd = new Char(u16(0x2ad2), {
      period: 250,
      // flags 0x0044: speed (always present), instantaneous cadence (bit 2), instantaneous power (bit 6)
      produce: () => [...le16(0x0044), ...le16(Math.round(state.speedKmh * 100)), ...le16(Math.round(state.cadence * 2)), ...s16(Math.round(state.powerW))],
    });
    cp = new Char(u16(0x2ad9), {
      write: async (b) => {
        const op = b[0];
        const dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
        const entry = { t: (performance.now() - state.t0) / 1000, op };
        if (op === 0x00) state.controlled = true;
        if (op === 0x11 && b.length >= 7) {
          state.sim = { windMs: dv.getInt16(1, true) / 1000, gradePct: dv.getInt16(3, true) / 100, crr: dv.getUint8(5) / 10000, cw: dv.getUint8(6) / 100 };
          state.erg = null;
          Object.assign(entry, state.sim);
        }
        if (op === 0x05) { state.erg = dv.getInt16(1, true); entry.targetW = state.erg; }
        state.log.push(entry);
        setTimeout(() => cp.emit([0x80, op, 0x01]), 20); // success indication
      },
    });
    const feature = new Char(u16(0x2acc), { read: () => [0x02, 0x40, 0x00, 0x00, 0x0c, 0xe0, 0x00, 0x00] });
    const ranges = new Char(u16(0x2ad5), { read: () => [...s16(-2000), ...s16(2000), ...le16(10)] });
    return { name: "KICKR CORE (emulated)", services: { [u16(0x1826)]: [ibd, cp, feature, ranges] } };
  }
  function makeHr() {
    const hrm = new Char(u16(0x2a37), { period: 1000, produce: () => [0x00, Math.round(state.hr)] });
    return { name: "HRM-Pro (emulated)", services: { [u16(0x180d)]: [hrm] } };
  }
  function makePower() {
    const m = new Char(u16(0x2a63), {
      period: 250,
      // flags 0x0020: crank revolution data present
      produce: () => [...le16(0x0020), ...s16(Math.round(state.powerW)), ...le16(Math.floor(state.crankRevs) & 0xffff), ...le16(Math.floor(state.crankTime) & 0xffff)],
    });
    const f = new Char(u16(0x2a65), { read: () => [0x08, 0, 0, 0] });
    return { name: "Assioma Duo (emulated)", services: { [u16(0x1818)]: [m, f] } };
  }

  const catalogue = [makeTrainer(), makeHr(), makePower()];
  let ids = 0;
  function device(spec) {
    const dev = new EventTarget();
    dev.id = `emu-${++ids}`;
    dev.name = spec.name;
    const server = {
      connected: false, device: dev,
      async connect() { this.connected = true; return this; },
      disconnect() { this.connected = false; dev.dispatchEvent(new Event("gattserverdisconnected")); },
      async getPrimaryService(s) {
        const chars = spec.services[norm(s)];
        if (!chars) throw new DOMException("No Services matching UUID found in Device.", "NotFoundError");
        return { uuid: norm(s), async getCharacteristic(c) {
          const ch = chars.find((x) => x.uuid === norm(c));
          if (!ch) throw new DOMException("No Characteristics matching UUID found in Service.", "NotFoundError");
          return ch;
        } };
      },
    };
    dev.gatt = server;
    return dev;
  }
  const bluetooth = {
    async getAvailability() { return true; },
    async requestDevice(opts) {
      const wanted = (opts.filters || []).flatMap((f) => (f.services || []).map(norm));
      const spec = catalogue.find((d) => wanted.some((w) => d.services[w]));
      if (!spec) throw new DOMException("User cancelled the requestDevice() chooser.", "NotFoundError");
      await new Promise((r) => setTimeout(r, 300)); // chooser
      return device(spec);
    },
  };
  Object.defineProperty(navigator, "bluetooth", { value: bluetooth, configurable: true });
})();
