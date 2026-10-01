/// <reference lib="dom" />
import { BleAdapter, BleDevice, DeviceFilter } from "./adapter";
import { ALL_OPTIONAL_SERVICES } from "./uuids";

// Minimal structural types so this compiles without @types/web-bluetooth.
interface GattChar {
  startNotifications(): Promise<GattChar>;
  addEventListener(t: string, cb: (e: { target: { value: DataView } }) => void): void;
  writeValueWithResponse(d: BufferSource): Promise<void>;
  writeValueWithoutResponse(d: BufferSource): Promise<void>;
  readValue(): Promise<DataView>;
}
interface GattService { getCharacteristic(c: string): Promise<GattChar> }
interface GattServer { connected: boolean; connect(): Promise<GattServer>; disconnect(): void; getPrimaryService(s: string): Promise<GattService> }
interface WbDevice { id: string; name?: string; gatt?: GattServer; addEventListener(t: string, cb: () => void): void }
interface WbBluetooth { requestDevice(o: unknown): Promise<WbDevice>; getAvailability?(): Promise<boolean> }

const bluetooth = (): WbBluetooth | undefined => (globalThis as unknown as { navigator?: { bluetooth?: WbBluetooth } }).navigator?.bluetooth;

class WebBluetoothDevice implements BleDevice {
  id: string;
  name: string;
  private server?: GattServer;
  private chars = new Map<string, GattChar>();
  constructor(private dev: WbDevice) {
    this.id = dev.id;
    this.name = dev.name ?? "Unknown device";
  }
  async connect() {
    if (!this.dev.gatt) throw new Error("Device has no GATT server");
    this.server = await this.dev.gatt.connect();
    this.chars.clear();
  }
  async disconnect() { this.server?.disconnect(); }
  onDisconnect(cb: () => void) { this.dev.addEventListener("gattserverdisconnected", cb); }
  private async char(s: string, c: string) {
    const k = `${s}/${c}`;
    let ch = this.chars.get(k);
    if (!ch) {
      if (!this.server) throw new Error("Not connected");
      ch = await (await this.server.getPrimaryService(s)).getCharacteristic(c);
      this.chars.set(k, ch);
    }
    return ch;
  }
  async hasService(s: string) {
    try { await this.server!.getPrimaryService(s); return true; } catch { return false; }
  }
  async subscribe(s: string, c: string, cb: (dv: DataView) => void) {
    const ch = await this.char(s, c);
    ch.addEventListener("characteristicvaluechanged", (e) => cb(e.target.value));
    await ch.startNotifications();
  }
  async write(s: string, c: string, data: Uint8Array, withResponse: boolean) {
    const ch = await this.char(s, c);
    const buf = data.slice().buffer as ArrayBuffer;
    await (withResponse ? ch.writeValueWithResponse(buf) : ch.writeValueWithoutResponse(buf));
  }
  async read(s: string, c: string) { return (await this.char(s, c)).readValue(); }
}

/** Web Bluetooth (Chrome/Edge desktop and Android). Needs a secure context and a user gesture. */
export class WebBluetoothAdapter implements BleAdapter {
  async isAvailable() {
    const bt = bluetooth();
    if (!bt) return false;
    return bt.getAvailability ? bt.getAvailability() : true;
  }
  async requestDevice(filter: DeviceFilter): Promise<BleDevice> {
    const bt = bluetooth();
    if (!bt) throw new Error("Web Bluetooth is not available in this browser (Safari/iOS do not support it).");
    const filters = [];
    if (filter.services?.length) for (const s of filter.services) filters.push({ services: [s] });
    if (filter.namePrefix) filters.push({ namePrefix: filter.namePrefix });
    const dev = await bt.requestDevice({
      ...(filters.length ? { filters } : { acceptAllDevices: true }),
      optionalServices: filter.optionalServices ?? ALL_OPTIONAL_SERVICES,
    });
    return new WebBluetoothDevice(dev);
  }
}
