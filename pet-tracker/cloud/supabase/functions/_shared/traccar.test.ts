import assert from "node:assert/strict";
import { test } from "node:test";

import { batteryPercent, buildCommand, parseTraccarForward } from "./traccar.ts";

const NOW = Date.parse("2026-11-13T12:00:00Z");
const msg = (position: Record<string, unknown>, uniqueId = "861234567890123") =>
  parseTraccarForward({ position, device: { id: 1, uniqueId, name: "MT710" } }, NOW);

test("a valid fix becomes a position with accuracy, battery and time", () => {
  const m = msg({ valid: true, latitude: 52.379, longitude: 4.8995, accuracy: 8, fixTime: "2026-11-13T11:59:00.000+00:00", attributes: { batteryLevel: 76.4 } });
  assert.deepEqual(m, {
    kind: "position", deviceUid: "861234567890123", lat: 52.379, lng: 4.8995, accuracyM: 8, batteryPct: 76,
    recordedAt: "2026-11-13T11:59:00.000Z",
  });
});

test("accuracy falls back to HDOP, then to a default", () => {
  const a = msg({ valid: true, latitude: 52.3, longitude: 4.9, attributes: { hdop: 1.2 } });
  assert.equal(a.kind === "position" && a.accuracyM, 6);
  const b = msg({ valid: true, latitude: 52.3, longitude: 4.9, accuracy: 0, attributes: {} });
  assert.equal(b.kind === "position" && b.accuracyM, 25);
});

test("no fix, an outdated repeat or null island is only a check-in", () => {
  for (const p of [
    { valid: false, latitude: 52.3, longitude: 4.9, attributes: { batteryLevel: 50 } },
    { valid: true, outdated: true, latitude: 52.3, longitude: 4.9, attributes: { batteryLevel: 50 } },
    { valid: true, latitude: 0, longitude: 0, attributes: { batteryLevel: 50 } },
  ]) {
    assert.deepEqual(msg(p), { kind: "heartbeat", deviceUid: "861234567890123", batteryPct: 50 });
  }
});

test("a fix time in the future is clamped to now", () => {
  const m = msg({ valid: true, latitude: 52.3, longitude: 4.9, fixTime: "2027-01-01T00:00:00Z" });
  assert.equal(m.kind === "position" && m.recordedAt, new Date(NOW).toISOString());
});

test("battery from percent, or estimated from a voltage", () => {
  assert.equal(batteryPercent({ batteryLevel: 100 }), 100);
  assert.equal(batteryPercent({ battery: 4.2 }), 100);
  assert.equal(batteryPercent({ battery: 3.8 }), 50);
  assert.equal(batteryPercent({ battery: 3.3 }), 0);
  assert.equal(batteryPercent({ battery: 12.4 }), null, "a car battery voltage is not a cat collar");
  assert.equal(batteryPercent({}), null);
});

test("messages without a usable tracker id are ignored", () => {
  assert.equal(msg({ valid: true, latitude: 52.3, longitude: 4.9 }, "bad id!").kind, "ignore");
  assert.equal(parseTraccarForward(null).kind, "ignore");
});

test("command templates take seconds or minutes", () => {
  assert.equal(buildCommand("TIMER,{seconds}#", 30), "TIMER,30#");
  assert.equal(buildCommand("interval {minutes}", 30), "interval 1");
  assert.equal(buildCommand("interval {minutes}", 900), "interval 15");
});
