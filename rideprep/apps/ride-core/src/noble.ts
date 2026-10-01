import { BleAdapter, BleDevice, DeviceFilter } from "@rideprep/ble";

// Minimal structural types for @abandonware/noble (optional native dependency; desktop only).
interface NChar { uuid: string; subscribe(cb?: (e?: Error) => void): void; on(ev: "data", cb: (d: Buffer) => void): void; write(d: Buffer, withoutResponse: boolean, cb?: (e?: Error) => void): void; read(cb: (e: Error | undefined, d: Buffer) => void): void }
interface NService { uuid: string; characteristics: NChar[] }
interface NPeripheral { id: string; advertisement: { localName?: string; serviceUuids?: string[] }; connectAsync(): Promise<void>; disconnectAsync(): Promise<void>; once(ev: "disconnect", cb: () => void): void; discoverAllServicesAndCharacteristicsAsync(): Promise<{ services: NService[] }> }
interface Noble { state: string; on(ev: string, cb: (...a: never[]) => void): void; removeListener(ev: string, cb: (...a: never[]) => void): void; startScanningAsync(uuids: string[], dup: boolean): Promise<void>; stopScanningAsync(): Promise<void> }

const short = (u: string) => u.replace(/-/g, "").toLowerCase().replace(/^0000(....)00001000800000805f9b34fb$/, "$1");

class NobleDevice implements BleDevice {
  id: string;
  name: string;
  private services: NService[] = [];
  constructor(private p: NPeripheral) {
    this.id = p.id;
    this.name = p.advertisement.localName ?? p.id;
  }
  async connect() {
    await this.p.connectAsync();
    this.services = (await this.p.discoverAllServicesAndCharacteristicsAsync()).services;
  }
  async disconnect() { await this.p.disconnectAsync(); }
  onDisconnect(cb: () => void) { this.p.once("disconnect", cb); }
  async hasService(s: string) { return this.services.some((x) => short(x.uuid) === short(s)); }
  private ch(s: string, c: string): NChar {
    const svc = this.services.find((x) => short(x.uuid) === short(s));
    const ch = svc?.characteristics.find((x) => short(x.uuid) === short(c));
    if (!ch) throw new Error(`characteristic ${c} not found on ${this.name}`);
    return ch;
  }
  async subscribe(s: string, c: string, cb: (dv: DataView) => void) {
    const ch = this.ch(s, c);
    ch.on("data", (d) => cb(new DataView(d.buffer, d.byteOffset, d.byteLength)));
    await new Promise<void>((res, rej) => ch.subscribe((e) => (e ? rej(e) : res())));
  }
  async write(s: string, c: string, data: Uint8Array, withResponse: boolean) {
    const ch = this.ch(s, c);
    await new Promise<void>((res, rej) => ch.write(Buffer.from(data), !withResponse, (e) => (e ? rej(e) : res())));
  }
  async read(s: string, c: string) {
    const ch = this.ch(s, c);
    const d = await new Promise<Buffer>((res, rej) => ch.read((e, b) => (e ? rej(e) : res(b))));
    return new DataView(d.buffer, d.byteOffset, d.byteLength);
  }
}

/** BLE on desktop through @abandonware/noble (used by the ride core next to Unreal). */
export class NobleAdapter implements BleAdapter {
  private noble?: Noble;
  private async lib(): Promise<Noble> {
    if (!this.noble) {
      const mod = (await import("@abandonware/noble" as string)) as { default: Noble };
      this.noble = mod.default;
    }
    return this.noble;
  }
  async isAvailable() {
    try {
      const n = await this.lib();
      if (n.state === "poweredOn") return true;
      return await new Promise<boolean>((res) => {
        const t = setTimeout(() => res(false), 3000);
        n.on("stateChange", ((s: string) => { clearTimeout(t); res(s === "poweredOn"); }) as never);
      });
    } catch {
      return false;
    }
  }
  /** Scans up to 15 s and returns the first device advertising one of the services (or matching the name prefix). */
  async requestDevice(filter: DeviceFilter): Promise<BleDevice> {
    const n = await this.lib();
    const uuids = (filter.services ?? []).map(short);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(async () => { await n.stopScanningAsync(); reject(new Error("no device found")); }, 15000);
      const onDiscover = (async (p: NPeripheral) => {
        const adv = (p.advertisement.serviceUuids ?? []).map(short);
        const nameOk = filter.namePrefix ? (p.advertisement.localName ?? "").startsWith(filter.namePrefix) : true;
        if ((uuids.length === 0 || uuids.some((u) => adv.includes(u))) && nameOk) {
          clearTimeout(timer);
          n.removeListener("discover", onDiscover);
          await n.stopScanningAsync();
          resolve(new NobleDevice(p));
        }
      }) as never;
      n.on("discover", onDiscover);
      void n.startScanningAsync(uuids, false);
    });
  }
}
