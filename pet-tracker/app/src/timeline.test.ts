import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { HomeZone, TrackPoint } from './backend/types';
import { offset } from './geo.ts';
import { weekSummary, collarShare } from './insights.ts';
import { buildTimeline } from './timeline.ts';
import { alertView } from './alerts.ts';
import { inviteCodeFrom, shareUrl } from './links.ts';

const HOME: HomeZone = { id: 'z', name: 'Home', lat: 52.374, lng: 4.883, radiusM: 30, allCats: false, householdId: 'h', householdName: 'Huis' };
const at = (min: number) => new Date(Date.UTC(2026, 10, 14, 8, 0) + min * 60_000).toISOString();
const p = (min: number, dist: number, bearing = 90): TrackPoint => {
  const q = offset(HOME.lat, HOME.lng, dist, bearing);
  return { at: at(min), lat: q.lat, lng: q.lng, accuracyM: 8, batteryPct: 80 };
};

test('a day becomes home, out (with a stop) and home again', () => {
  const track = [
    p(0, 5), p(30, 8),                          // home
    p(40, 120), p(45, 300),                     // walking out
    p(50, 400), p(60, 405), p(70, 402),         // 20 min stop near 400 m
    p(80, 200), p(90, 6), p(120, 4),            // back home
  ];
  const tl = buildTimeline(track, [HOME]);
  assert.deepEqual(tl.map((e) => e.kind), ['zone', 'out', 'stop', 'zone']);
  const out = tl[1]!;
  assert.ok(out.kind === 'out' && out.farthestM > 350 && out.distanceM > 450);
  assert.equal(tl[0]!.kind === 'zone' && tl[0]!.to, at(40)); // no gaps between blocks
});

test('imprecise fixes are ignored', () => {
  const noisy = { ...p(10, 500), accuracyM: 400 };
  assert.deepEqual(buildTimeline([p(0, 5), noisy, p(20, 5)], [HOME]).map((e) => e.kind), ['zone']);
});

test('weekly summary compares with the week before', () => {
  const day = (i: number, m: number) => ({ day: `2026-11-${String(14 - i).padStart(2, '0')}`, distanceM: m, activeMinutes: 60, roamRadiusM: 200 + i, nightShare: 0.6, fixes: 40 });
  const days = [...Array.from({ length: 7 }, (_, i) => day(i, 1200)), ...Array.from({ length: 7 }, (_, i) => day(i + 7, 1000))];
  const s = weekSummary(days);
  assert.equal(s.distanceM, 8400);
  assert.ok(Math.abs(s.trend! - 0.2) < 1e-9);
  assert.equal(s.maxRoamM, 206);
  assert.ok(collarShare(19, 4)! < 0.005 && collarShare(19, null) === null);
});

test('alerts read in words, with the facts', () => {
  assert.equal(alertView({ kind: 'zone_exit', meta: { zone: 'Home' } }, 'Minoes').title, 'Minoes left Home');
  assert.match(alertView({ kind: 'low_battery', meta: { battery: 15 } }, 'Pluis').body, /15%/);
});

test('invite and share links', () => {
  assert.equal(inviteCodeFrom('https://example.com/join?code=abcd2345'), 'ABCD2345');
  assert.equal(inviteCodeFrom('ABCD-2345'), 'ABCD-2345');
  assert.equal(inviteCodeFrom('not a code!'), null);
  assert.match(shareUrl('tok_123'), /share\/tok_123$/);
});
