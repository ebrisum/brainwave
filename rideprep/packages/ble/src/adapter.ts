export interface DeviceFilter {
  services?: string[];
  namePrefix?: string;
  optionalServices?: string[];
}

export interface BleAdapter {
  /** Must be called from a user gesture in browsers. */
  requestDevice(filter: DeviceFilter): Promise<BleDevice>;
  isAvailable(): Promise<boolean>;
}

export interface BleDevice {
  id: string;
  name: string;
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  subscribe(service: string, characteristic: string, cb: (dv: DataView) => void): Promise<void>;
  write(service: string, characteristic: string, data: Uint8Array, withResponse: boolean): Promise<void>;
  read?(service: string, characteristic: string): Promise<DataView>;
  hasService?(service: string): Promise<boolean>;
  onDisconnect(cb: () => void): void;
}
