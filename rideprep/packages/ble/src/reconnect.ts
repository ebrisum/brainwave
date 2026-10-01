import { BleDevice } from "./adapter";

export type DeviceState = "connecting" | "connected" | "reconnecting" | "disconnected";

/** Backoff schedule 1, 2, 4, 8, … s capped at 30 s. */
export const backoffMs = (attempt: number): number => Math.min(1000 * 2 ** attempt, 30000);

/**
 * Keeps a device connected: on disconnect it retries with exponential backoff and re-runs `setup`
 * (subscriptions, control requests). The ride keeps running meanwhile; `onState` drives the HUD.
 */
export class ManagedConnection {
  state: DeviceState = "disconnected";
  attempts = 0;
  private stopped = false;
  private timer?: ReturnType<typeof setTimeout>;

  constructor(public device: BleDevice, private setup: (d: BleDevice) => Promise<void>, private onState?: (s: DeviceState) => void) {
    device.onDisconnect(() => this.handleDrop());
  }

  private set(s: DeviceState) { this.state = s; this.onState?.(s); }

  async start() {
    this.set("connecting");
    await this.device.connect();
    await this.setup(this.device);
    this.attempts = 0;
    this.set("connected");
  }

  private handleDrop() {
    if (this.stopped || this.state === "reconnecting") return;
    this.set("reconnecting");
    this.schedule();
  }

  private schedule() {
    const delay = backoffMs(this.attempts++);
    this.timer = setTimeout(async () => {
      if (this.stopped) return;
      try {
        await this.device.connect();
        await this.setup(this.device);
        this.attempts = 0;
        this.set("connected");
      } catch {
        this.schedule();
      }
    }, delay);
  }

  async stop() {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    await this.device.disconnect();
    this.set("disconnected");
  }
}
