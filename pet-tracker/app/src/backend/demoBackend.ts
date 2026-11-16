/**
 * Demo backend: no account, no server. Two simulated cats wander around, and
 * any cat you mark as "tracked by this phone" follows the phone's real GPS.
 * Zone alerts, heatmap and activity use the same rules as the database.
 */
import { normalizeClaimCode } from '../claim';
import { binHeatmap, distanceM, estimateActivity, insideZone, offset } from '../geo';
import {
  DEFAULT_NIGHT,
  DEFAULT_SETTINGS,
  EMPTY_PROFILE,
  type AlertItem,
  type AlertKind,
  type CatProfile,
  type PowerMode,
  type ShareLink,
  type UserSettings,
  type ActivityDay,
  type Backend,
  type Cat,
  type CatEvent,
  type HeatCell,
  type ClaimCheck,
  type HomeZone,
  type TrackerHealth,
  type ZoneTarget,
  type CatSitter,
  type Household,
  type InviteResult,
  type LiveHandlers,
  type NightWatch,
  type PhoneFix,
  type ReportResult,
  type TrackPoint,
} from './types';
import { t as tr } from '../i18n';

const DEFAULT_CENTER = { lat: 52.35335, lng: 4.87612 }; // a street near the Vondelpark, until the phone reports
const HOME_ZONE_ID = 'demo-home';
const SIM_TICK_MS = 4000;
const MAX_TRACK = 4000;
const DEMO_USER = 'demo-user';
const DEMO_HOUSEHOLD = 'demo-household';
/** Label of the demo collar (also printed by cloud/provisioning for testing). */
export const DEMO_COLLAR = { deviceUid: 'DEMO-0001', claimCode: 'DEMOCODE2345' } as const;
const NEEDS_ACCOUNT_COLLAR = () => tr('A new collar needs an account. Exit the demo and sign in.');
const NEEDS_ACCOUNT = () => tr('Sharing needs an account. Exit the demo and sign in to invite people.');

let nextId = 1;
const newId = (p: string) => `${p}-${Date.now().toString(36)}-${(nextId++).toString(36)}`;

interface SimState {
  heading: number;
  napUntil: number;
  /** Stays at home unless lost (the demo's sleepy cat). */
  homebody?: boolean;
}

export class DemoBackend implements Backend {
  readonly mode = 'demo' as const;
  readonly userId = DEMO_USER;
  get userLabel() {
    return tr('Demo mode');
  }

  #cats = new Map<string, Cat>();
  #tracks = new Map<string, TrackPoint[]>();
  #zones = new Map<string, HomeZone[]>(); // key: catId, or `hh:<householdId>` for a household's zones
  #zoneState = new Map<string, boolean>(); // `${catId}:${zoneId}`
  #events: CatEvent[] = [];
  #sim = new Map<string, SimState>();
  #listeners = new Set<LiveHandlers>();
  #timer: ReturnType<typeof setInterval> | null = null;
  #center = { ...DEFAULT_CENTER };
  #centered = false;
  /** In-memory households, so moving cats around can be tried without an account. */
  #demoCollarClaimed = false;
  #alerts: AlertItem[] = [];
  #readUntil = 0;
  #settings: UserSettings = { ...DEFAULT_SETTINGS, notify: { ...DEFAULT_SETTINGS.notify } };
  #shares = new Map<string, ShareLink>();
  #households = new Map<string, { id: string; name: string }>([[DEMO_HOUSEHOLD, { id: DEMO_HOUSEHOLD, name: tr('Demo household') }]]);

  constructor() {
    // A home zone for the demo household, so "At Home" / "Out", alerts and the
    // day timeline have something to show.
    this.#zones.set(`hh:${DEMO_HOUSEHOLD}`, [{
      id: HOME_ZONE_ID, name: tr('Home'), lat: this.#center.lat, lng: this.#center.lng, radiusM: 35,
      allCats: true, householdId: DEMO_HOUSEHOLD, householdName: tr('Demo household'),
    }]);
    this.#seed('Minoes', '#F59E0B', 6, 120, 0.15, true);
    this.#seed('Tijger', '#6366F1', 230, 40, 0.65);
    this.#seed('Pluis', '#EC4899', 120, 250, 0.45);
    // A low battery yesterday (since charged), shown in the inbox.
    const pluis = [...this.#cats.values()].find((c) => c.name === 'Pluis');
    if (pluis) this.#alert(pluis, 'low_battery', { battery: 18 }, Date.now() - 26 * 3600_000);
    this.#alerts.sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
    this.#readUntil = Date.now() - 3 * 3600_000; // the last few hours are unread
  }

  #newCat(name: string, color: string, kind: Cat['kind']): Cat {
    return {
      id: newId(kind === 'phone' ? 'ph' : 'sim'),
      name, color, kind, ownerId: DEMO_USER,
      lastLat: null, lastLng: null, lastAccuracyM: null, lastBatteryPct: null, lastFixAt: null,
      lostMode: false, lostModeSince: null, night: { ...DEFAULT_NIGHT }, photoPath: null,
      householdId: DEMO_HOUSEHOLD, householdName: tr('Demo household'), access: 'owner', sitterUntil: null,
      lastSeenAt: null, place: null, powerMode: 'normal', model: kind === 'collar' ? tr('Demo collar') : null, fwVersion: null,
      profile: { ...EMPTY_PROFILE },
    };
  }

  /**
   * A simulated cat `distance` m from home, with three days of history: naps
   * at home and at two favourite spots, short strolls and longer night walks.
   * `outShare` is how much of the day it spends away from home.
   */
  #seed(name: string, color: string, distance: number, bearing: number, outShare: number, homebody = false) {
    const cat = this.#newCat(name, color, 'collar');
    const home = this.#center;
    const p = offset(home.lat, home.lng, distance, bearing);
    Object.assign(cat, {
      lastLat: p.lat, lastLng: p.lng, lastAccuracyM: 8,
      lastBatteryPct: 64 + Math.round(Math.random() * 30), lastFixAt: new Date().toISOString(),
    });
    this.#cats.set(cat.id, cat);
    this.#sim.set(cat.id, { heading: Math.random() * 360, napUntil: 0, homebody });

    const spots = [home, offset(home.lat, home.lng, 140 + distance / 3, bearing + 30), offset(home.lat, home.lng, 260, bearing - 50)];
    const pts: TrackPoint[] = [];
    const now = Date.now();
    for (let m = 10 * 24 * 60; m > 0; m -= 10) {
      const at = now - m * 60_000;
      const hour = new Date(at).getHours();
      const night = hour >= 21 || hour < 6;
      const block = Math.floor(m / 90);
      const away = ((block * 7919) % 100) / 100 < outShare || (night && block % 2 === 0);
      const spot = away ? spots[1 + (block % 2)]! : spots[0]!;
      const wander = away ? (night ? 15 + Math.random() * 45 : 5 + Math.random() * 20) : Math.random() * 4;
      const q = offset(spot.lat, spot.lng, wander, Math.random() * 360);
      pts.push({ at: new Date(at).toISOString(), lat: q.lat, lng: q.lng, accuracyM: 6 + Math.random() * 8, batteryPct: 80 });
    }
    // The last stretch walks to where the cat is now.
    const last = pts[pts.length - 1]!;
    for (let k = 1; k <= 4; k++) {
      pts.push({
        at: new Date(now - (5 - k) * 2 * 60_000).toISOString(),
        lat: last.lat + ((p.lat - last.lat) * k) / 4, lng: last.lng + ((p.lng - last.lng) * k) / 4, accuracyM: 8, batteryPct: 80,
      });
    }
    this.#tracks.set(cat.id, pts);

    // Zone changes in that history become events and alerts, as on the server.
    const zone = this.#zonesFor(cat.id)[0];
    if (!zone) return;
    let was: boolean | null = null;
    for (const pt of pts) {
      const inside = insideZone(zone, pt, was);
      if (was !== null && inside !== was && Date.parse(pt.at) > now - 2 * 86400_000) {
        this.#events.unshift({ id: newId('ev'), catId: cat.id, transition: inside ? 'enter' : 'exit', zoneName: zone.name, at: pt.at });
        this.#alert(cat, inside ? 'zone_enter' : 'zone_exit', { zone: zone.name }, Date.parse(pt.at));
      }
      was = inside;
    }
    this.#zoneState.set(`${cat.id}:${zone.id}`, was ?? false);
  }

  /** Re-anchor the simulated cats near the phone the first time it reports. */
  #recenter(lat: number, lng: number) {
    if (this.#centered) return;
    this.#centered = true;
    const dLat = lat - this.#center.lat;
    const dLng = lng - this.#center.lng;
    this.#center = { lat, lng };
    for (const [key, zs] of this.#zones) {
      this.#zones.set(key, zs.map((z) => ({ ...z, lat: z.lat + dLat, lng: z.lng + dLng })));
    }
    for (const [id, cat] of this.#cats) {
      if (!this.#sim.has(id) || cat.lastLat === null || cat.lastLng === null) continue;
      cat.lastLat += dLat;
      cat.lastLng += dLng;
      this.#tracks.set(id, (this.#tracks.get(id) ?? []).map((p) => ({ ...p, lat: p.lat + dLat, lng: p.lng + dLng })));
      this.#emitCat(cat);
    }
  }

  #emitCat(cat: Cat) {
    for (const l of this.#listeners) l.onCat(this.#view(cat));
  }

  /** A copy with its place relative to its zones (same rule as get_cat_status). */
  #view(cat: Cat): Cat {
    const zones = this.#zonesFor(cat.id);
    let place: Cat['place'] = null;
    if (zones.length && cat.lastLat != null && cat.lastLng != null) {
      const inside = zones.find((z) => this.#zoneState.get(`${cat.id}:${z.id}`));
      const nearest = zones
        .map((z) => ({ z, m: Math.max(0, distanceM(z.lat, z.lng, cat.lastLat!, cat.lastLng!) - z.radiusM) }))
        .sort((a, b) => a.m - b.m)[0]!;
      place = { zoneName: inside?.name ?? null, nearestZoneName: nearest.z.name, nearestZoneM: nearest.m };
    }
    return { ...cat, night: { ...cat.night }, lastSeenAt: cat.lastFixAt, place };
  }

  #zonesFor(catId: string): HomeZone[] {
    const household = this.#cats.get(catId)?.householdId;
    return [...(household ? this.#zones.get(`hh:${household}`) ?? [] : []), ...(this.#zones.get(catId) ?? [])];
  }

  #record(cat: Cat, point: TrackPoint) {
    const track = this.#tracks.get(cat.id) ?? [];
    track.push(point);
    if (track.length > MAX_TRACK) track.splice(0, track.length - MAX_TRACK);
    this.#tracks.set(cat.id, track);

    Object.assign(cat, {
      lastLat: point.lat, lastLng: point.lng, lastAccuracyM: point.accuracyM,
      lastBatteryPct: point.batteryPct, lastFixAt: point.at,
    });
    this.#emitCat(cat);

    for (const zone of this.#zonesFor(cat.id)) {
      const key = `${cat.id}:${zone.id}`;
      const was = this.#zoneState.has(key) ? this.#zoneState.get(key)! : null;
      const now = insideZone(zone, point, was);
      this.#zoneState.set(key, now);
      if (was !== null && was !== now) {
        const ev: CatEvent = { id: newId('ev'), catId: cat.id, transition: now ? 'enter' : 'exit', zoneName: zone.name, at: point.at };
        this.#events.unshift(ev);
        this.#alert(cat, now ? 'zone_enter' : 'zone_exit', { zone: zone.name });
        for (const l of this.#listeners) l.onEvent?.(ev);
      }
    }
  }

  #tick = () => {
    const now = Date.now();
    for (const [id, s] of this.#sim) {
      const cat = this.#cats.get(id);
      if (!cat || cat.lastLat === null || cat.lastLng === null) continue;
      if (s.homebody && !cat.lostMode) continue; // the sleepy one stays on the sofa
      if (now < s.napUntil && !cat.lostMode) continue; // cats sleep a lot
      if (Math.random() < 0.08 && !cat.lostMode) {
        s.napUntil = now + 20_000 + Math.random() * 40_000;
        continue;
      }
      // Wander, but drift back home when far away.
      const homeBearing = (Math.atan2(this.#center.lng - cat.lastLng, this.#center.lat - cat.lastLat) * 180) / Math.PI;
      const far = Math.hypot(this.#center.lat - cat.lastLat, this.#center.lng - cat.lastLng) > 0.004;
      s.heading = far ? homeBearing + (Math.random() - 0.5) * 40 : s.heading + (Math.random() - 0.5) * 70;
      const p = offset(cat.lastLat, cat.lastLng, 3 + Math.random() * 9, s.heading);
      this.#record(cat, {
        at: new Date().toISOString(), lat: p.lat, lng: p.lng,
        accuracyM: 5 + Math.random() * 10,
        batteryPct: Math.max(5, (cat.lastBatteryPct ?? 90) - (Math.random() < 0.02 ? 1 : 0)),
      });
    }
  };

  #alert(cat: Cat, kind: AlertKind, meta: AlertItem['meta'] = {}, at: number = Date.now()) {
    const titles: Record<AlertKind, string> = {
      zone_exit: tr('{name} left {zone}', { name: cat.name, zone: meta.zone ?? tr('a zone') }),
      zone_enter: tr('{name} is back in {zone}', { name: cat.name, zone: meta.zone ?? tr('a zone') }),
      low_battery: tr("{name}'s tracker battery is low", { name: cat.name }),
      lost_mode: tr('Lost mode on for {name}', { name: cat.name }),
      tracker_silent: tr("{name}'s tracker is silent", { name: cat.name }),
      found: tr('{name} is found', { name: cat.name }),
    };
    this.#alerts.unshift({ id: newId('al'), catId: cat.id, kind, title: titles[kind], body: '', meta, at: new Date(at).toISOString(), unread: true });
    this.#alerts.splice(200);
  }

  async listCats(): Promise<Cat[]> {
    return [...this.#cats.values()].map((c) => this.#view(c));
  }

  subscribe(handlers: LiveHandlers): () => void {
    this.#listeners.add(handlers);
    if (!this.#timer) this.#timer = setInterval(this.#tick, SIM_TICK_MS);
    return () => {
      this.#listeners.delete(handlers);
      if (this.#listeners.size === 0 && this.#timer) {
        clearInterval(this.#timer);
        this.#timer = null;
      }
    };
  }

  async addPhoneCat(name: string, color: string): Promise<string> {
    const trimmed = name.trim();
    if (!trimmed || trimmed.length > 64) throw new Error(tr('Name must be 1-64 characters'));
    const cat = this.#newCat(trimmed, color, 'phone');
    this.#cats.set(cat.id, cat);
    this.#emitCat(cat);
    return cat.id;
  }

  // Making labels needs the real backend: they must be recorded there.
  async isStaff(): Promise<boolean> {
    return false;
  }
  async staffCreateTracker(): Promise<never> {
    throw new Error(NEEDS_ACCOUNT());
  }
  async staffListTrackers(): Promise<never> {
    throw new Error(NEEDS_ACCOUNT());
  }
  async staffResetTracker(): Promise<never> {
    throw new Error(NEEDS_ACCOUNT());
  }

  // One pretend collar, so scanning and adding a collar can be tried in demo mode.
  async checkClaimCode(deviceUid: string, claimCode: string): Promise<ClaimCheck> {
    if (deviceUid.trim() !== DEMO_COLLAR.deviceUid || normalizeClaimCode(claimCode) !== DEMO_COLLAR.claimCode) {
      return { status: 'invalid', model: null };
    }
    return { status: this.#demoCollarClaimed ? 'yours' : 'ready', model: tr('Demo collar') };
  }

  async claimCollar(deviceUid: string, claimCode: string): Promise<string> {
    const check = await this.checkClaimCode(deviceUid, claimCode);
    if (check.status !== 'ready') {
      throw new Error(check.status === 'yours' ? tr('This collar is already in your list.') : tr('In demo mode only the demo collar can be added.'));
    }
    this.#demoCollarClaimed = true;
    const cat = this.#newCat(tr('New cat'), '#10B981', 'collar');
    const p = offset(this.#center.lat, this.#center.lng, 60, 120);
    Object.assign(cat, { lastLat: p.lat, lastLng: p.lng, lastAccuracyM: 10, lastBatteryPct: 100, lastFixAt: new Date().toISOString() });
    this.#cats.set(cat.id, cat);
    this.#emitCat(cat);
    return cat.id;
  }

  #cat(id: string): Cat {
    const cat = this.#cats.get(id);
    if (!cat) throw new Error(tr('Cat not found'));
    return cat;
  }

  async updateCat(id: string, changes: { name?: string; color?: string }): Promise<void> {
    const cat = this.#cat(id);
    if (changes.name !== undefined) cat.name = changes.name.trim();
    if (changes.color !== undefined) cat.color = changes.color;
    this.#emitCat(cat);
  }

  async removeCat(id: string): Promise<void> {
    this.#cats.delete(id);
    this.#tracks.delete(id);
    this.#zones.delete(id);
    this.#sim.delete(id);
    for (const l of this.#listeners) l.onCatRemoved?.(id);
  }

  async setPhoto(catId: string, localUri: string): Promise<void> {
    const cat = this.#cat(catId);
    cat.photoPath = localUri;
    this.#emitCat(cat);
  }

  async removePhoto(catId: string): Promise<void> {
    const cat = this.#cat(catId);
    cat.photoPath = null;
    this.#emitCat(cat);
  }

  async photoUrl(path: string): Promise<string | null> {
    return path;
  }

  async setLostMode(catId: string, on: boolean): Promise<void> {
    const cat = this.#cat(catId);
    if (cat.lostMode !== on) this.#alert(cat, on ? 'lost_mode' : 'found');
    cat.lostMode = on;
    cat.lostModeSince = on ? new Date().toISOString() : null;
    this.#emitCat(cat);
  }

  async setNightWatch(catId: string, night: NightWatch): Promise<void> {
    const cat = this.#cat(catId);
    cat.night = { ...night };
    this.#emitCat(cat);
  }

  async reportLocation(catId: string, fix: PhoneFix): Promise<ReportResult> {
    const cat = this.#cats.get(catId);
    if (!cat || cat.kind !== 'phone') return 'rejected';
    this.#recenter(fix.lat, fix.lng);
    this.#record(cat, {
      at: fix.at, lat: fix.lat, lng: fix.lng, accuracyM: fix.accuracyM,
      batteryPct: fix.batteryPct ?? cat.lastBatteryPct ?? 100,
    });
    return 'ok';
  }

  async getTrack(catId: string, sinceIso: string): Promise<TrackPoint[]> {
    const since = Date.parse(sinceIso);
    return (this.#tracks.get(catId) ?? []).filter((p) => Date.parse(p.at) >= since);
  }

  async getHeatmap(catId: string, sinceIso: string): Promise<HeatCell[]> {
    return binHeatmap(await this.getTrack(catId, sinceIso));
  }

  async getActivity(catId: string, days: number): Promise<ActivityDay[]> {
    const cat = this.#cat(catId);
    const track = await this.getTrack(catId, new Date(Date.now() - days * 86_400_000).toISOString());
    const home = this.#zonesFor(catId)[0] ?? null;
    return estimateActivity(track, { nightStartMin: cat.night.startMin, nightEndMin: cat.night.endMin, home });
  }

  async getTrackerHealth(catId: string): Promise<TrackerHealth> {
    const cat = this.#cat(catId);
    const track = this.#tracks.get(catId) ?? [];
    const dayAgo = Date.now() - 86_400_000;
    // The simulation drains slowly; show a plausible collar estimate.
    const drain = cat.kind === 'collar' ? 9 : null;
    return {
      lastSeenAt: cat.lastFixAt, lastFixAt: cat.lastFixAt, batteryPct: cat.lastBatteryPct,
      drainPctPerDay: drain, daysLeft: drain && cat.lastBatteryPct != null ? cat.lastBatteryPct / drain : null,
      fixes24h: track.filter((p) => Date.parse(p.at) > dayAgo).length, reportIntervalS: 300, silent: false, silentAfterS: 10_800,
      resting: false,
    };
  }

  async getZones(catId: string): Promise<HomeZone[]> {
    return this.#zonesFor(catId);
  }

  async getHouseholdZones(householdId: string): Promise<HomeZone[]> {
    return this.#zones.get(`hh:${householdId}`) ?? [];
  }

  async addZone(target: ZoneTarget, name: string, lat: number, lng: number, radiusM: number): Promise<void> {
    const householdId = 'householdId' in target ? target.householdId : null;
    const key = householdId ? `hh:${householdId}` : (target as { catId: string }).catId;
    const zone: HomeZone = {
      id: newId('zone'), name: name.trim() || tr('Home'), lat, lng, radiusM, allCats: householdId !== null,
      householdId, householdName: householdId ? this.#households.get(householdId)?.name ?? null : null,
    };
    this.#zones.set(key, [...(this.#zones.get(key) ?? []), zone]);
    // Start from each cat's current side of the fence so the first exit alerts.
    const cats = [...this.#cats.values()].filter((c) => (householdId ? c.householdId === householdId : c.id === key));
    for (const cat of cats) {
      if (cat.lastLat != null && cat.lastLng != null) {
        this.#zoneState.set(`${cat.id}:${zone.id}`, insideZone(zone, { lat: cat.lastLat, lng: cat.lastLng, accuracyM: cat.lastAccuracyM ?? 0 }, null));
      }
    }
  }

  async removeZone(zoneId: string): Promise<void> {
    for (const [key, zones] of this.#zones) {
      this.#zones.set(key, zones.filter((z) => z.id !== zoneId));
    }
  }

  async getEvents(catId: string): Promise<CatEvent[]> {
    return this.#events.filter((e) => e.catId === catId).slice(0, 50);
  }

  async listHouseholds(): Promise<Household[]> {
    return [...this.#households.values()].map((h) => ({
      id: h.id,
      name: h.name,
      myRole: 'admin',
      members: [{ userId: DEMO_USER, email: 'demo@cat-tracker.app', role: 'admin' }],
      catCount: [...this.#cats.values()].filter((c) => c.householdId === h.id).length,
    }));
  }
  async createHousehold(name: string): Promise<string> {
    const id = newId('hh');
    this.#households.set(id, { id, name: name.trim() || tr('Household') });
    return id;
  }
  async renameHousehold(householdId: string, name: string): Promise<void> {
    const h = this.#households.get(householdId);
    if (!h) return;
    h.name = name.trim() || h.name;
    for (const zone of this.#zones.get(`hh:${householdId}`) ?? []) zone.householdName = h.name;
    for (const cat of this.#cats.values()) {
      if (cat.householdId === householdId) {
        cat.householdName = h.name;
        this.#emitCat(cat);
      }
    }
  }
  async deleteHousehold(householdId: string): Promise<void> {
    this.#households.delete(householdId);
    this.#zones.delete(`hh:${householdId}`);
    for (const cat of this.#cats.values()) {
      if (cat.householdId === householdId) await this.setCatHousehold(cat.id, null);
    }
  }
  async createHouseholdInvite(): Promise<string> {
    throw new Error(NEEDS_ACCOUNT());
  }
  async removeMember(): Promise<void> {}
  async leaveHousehold(householdId: string): Promise<void> {
    await this.deleteHousehold(householdId);
  }
  async setCatHousehold(catId: string, householdId: string | null): Promise<void> {
    const cat = this.#cats.get(catId);
    if (!cat) return;
    cat.householdId = householdId;
    cat.householdName = householdId ? this.#households.get(householdId)?.name ?? null : null;
    this.#emitCat(cat);
  }
  async createSitterInvite(): Promise<string> {
    throw new Error(NEEDS_ACCOUNT());
  }
  async listCatSitters(): Promise<CatSitter[]> {
    return [];
  }
  async removeCatSitter(): Promise<void> {}
  async acceptInvite(): Promise<InviteResult> {
    throw new Error(NEEDS_ACCOUNT());
  }
  async setPowerMode(catId: string, mode: PowerMode): Promise<void> {
    const cat = this.#cat(catId);
    cat.powerMode = mode;
    this.#emitCat(cat);
  }

  async updateProfile(catId: string, changes: Partial<CatProfile>): Promise<void> {
    const cat = this.#cat(catId);
    const clean = Object.fromEntries(Object.entries(changes).map(([k, v]) => [k, typeof v === 'string' ? v.trim() || null : v]));
    cat.profile = { ...cat.profile, ...clean };
    this.#emitCat(cat);
  }

  async replaceCollar(): Promise<string> {
    throw new Error(NEEDS_ACCOUNT_COLLAR());
  }

  async getTrackRange(catId: string, fromIso: string, toIso: string): Promise<TrackPoint[]> {
    const from = Date.parse(fromIso);
    const to = Date.parse(toIso);
    return (this.#tracks.get(catId) ?? []).filter((p) => Date.parse(p.at) >= from && Date.parse(p.at) < to);
  }

  async listAlerts(limit = 50, beforeIso?: string): Promise<AlertItem[]> {
    const before = beforeIso ? Date.parse(beforeIso) : Infinity;
    return this.#alerts
      .filter((a) => Date.parse(a.at) < before)
      .slice(0, limit)
      .map((a) => ({ ...a, unread: Date.parse(a.at) > this.#readUntil }));
  }

  async unreadAlertCount(): Promise<number> {
    return this.#alerts.filter((a) => Date.parse(a.at) > this.#readUntil).length;
  }

  async markAlertsRead(): Promise<void> {
    this.#readUntil = Date.now();
  }

  async getSettings(): Promise<UserSettings> {
    return { ...this.#settings, notify: { ...this.#settings.notify } };
  }

  async updateSettings(
    changes: Partial<Omit<UserSettings, 'notify'>> & { notify?: Partial<UserSettings['notify']> },
  ): Promise<UserSettings> {
    this.#settings = { ...this.#settings, ...changes, notify: { ...this.#settings.notify, ...changes.notify } };
    return this.getSettings();
  }

  async createShareLink(catId: string, hours: number): Promise<ShareLink> {
    this.#cat(catId);
    const link = { token: `demo-${newId('share')}`, expiresAt: new Date(Date.now() + hours * 3600_000).toISOString() };
    this.#shares.set(catId, link);
    return link;
  }

  async getShareLink(catId: string): Promise<ShareLink | null> {
    const link = this.#shares.get(catId);
    return link && Date.parse(link.expiresAt) > Date.now() ? link : null;
  }

  async revokeShareLinks(catId: string): Promise<void> {
    this.#shares.delete(catId);
  }

  async exportMyData(): Promise<unknown> {
    return {
      exported_at: new Date().toISOString(),
      account: { email: 'demo' },
      settings: this.#settings,
      cats: [...this.#cats.values()].map((c) => ({ ...c, positions: this.#tracks.get(c.id) ?? [] })),
      alerts: this.#alerts,
    };
  }

  async registerPushToken(): Promise<void> {}
  async unregisterPushToken(): Promise<void> {}
  async deleteAccount(): Promise<void> {
    await this.signOut();
  }

  async signOut(): Promise<void> {
    if (this.#timer) clearInterval(this.#timer);
    this.#timer = null;
    this.#listeners.clear();
  }
}
