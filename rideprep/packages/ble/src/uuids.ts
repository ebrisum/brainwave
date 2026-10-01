/** Bluetooth SIG 16-bit UUIDs (Assigned Numbers) expanded to 128-bit form. */
export const uuid16 = (n: number): string => `0000${n.toString(16).padStart(4, "0")}-0000-1000-8000-00805f9b34fb`;

export const SERVICES = {
  ftms: uuid16(0x1826),
  cyclingPower: uuid16(0x1818),
  heartRate: uuid16(0x180d),
  cscs: uuid16(0x1816),
  userData: uuid16(0x181c),
  /** Tacx FE-C over BLE (fallback when FTMS is absent). */
  tacxFec: "6e40fec1-b5a3-f393-e0a9-e50e24dcca9e",
} as const;

export const CHARS = {
  ftmsFeature: uuid16(0x2acc),
  indoorBikeData: uuid16(0x2ad2),
  trainingStatus: uuid16(0x2ad3),
  supportedResistanceRange: uuid16(0x2ad6),
  supportedPowerRange: uuid16(0x2ad8),
  ftmsControlPoint: uuid16(0x2ad9),
  ftmsStatus: uuid16(0x2ada),
  cyclingPowerMeasurement: uuid16(0x2a63),
  cyclingPowerFeature: uuid16(0x2a65),
  heartRateMeasurement: uuid16(0x2a37),
  cscMeasurement: uuid16(0x2a5b),
  weight: uuid16(0x2a98),
} as const;

export const ALL_OPTIONAL_SERVICES = Object.values(SERVICES);
