/**
 * Real backend: Supabase Auth + PostgREST RPCs + Realtime + Storage.
 * All access is enforced server-side by RLS and the security-definer functions
 * in cloud/supabase/migrations - this client holds only the public key.
 */
import { File } from 'expo-file-system';
import { Platform } from 'react-native';
import type { RealtimeChannel, SupabaseClient } from '@supabase/supabase-js';

import { normalizeClaimCode } from '../claim';

import { DEFAULT_SETTINGS } from './types';
import type {
  ActivityDay,
  AlertItem,
  AlertKind,
  CatProfile,
  HistoryDays,
  Lifestyle,
  PowerMode,
  ShareLink,
  UserSettings,
  Backend,
  Cat,
  CatAccess,
  CatEvent,
  CatSitter,
  HeatCell,
  CatPlace,
  ClaimCheck,
  NewTrackerLabel,
  StaffTracker,
  HomeZone,
  TrackerHealth,
  ZoneTarget,
  Household,
  HouseholdRole,
  InviteResult,
  LiveHandlers,
  NightWatch,
  PhoneFix,
  ReportResult,
  TrackPoint,
} from './types';
import { t as tr } from '../i18n';

interface DeviceRow {
  id: string;
  display_name: string | null;
  color: string;
  kind: 'collar' | 'phone';
  owner_id: string | null;
  last_lat: number | null;
  last_lng: number | null;
  last_accuracy_m: number | null;
  last_battery_pct: number | null;
  last_fix_at: string | null;
  lost_mode: boolean;
  lost_mode_since: string | null;
  night_mode: boolean;
  night_start_min: number;
  night_end_min: number;
  night_interval_s: number;
  photo_path: string | null;
  household_id: string | null;
  last_seen_at: string | null;
  // Added in migration 1200 (absent on older databases).
  power_mode?: PowerMode | null;
  model?: string | null;
  fw_version?: string | null;
  birth_date?: string | null;
  breed?: string | null;
  weight_kg?: number | string | null;
  microchip?: string | null;
  vet_name?: string | null;
  vet_phone?: string | null;
  lifestyle?: Lifestyle | null;
  notes?: string | null;
}

/** How the signed-in person sees a cat (from my_cat_access). */
interface AccessInfo {
  access: CatAccess;
  householdName: string | null;
  sitterUntil: string | null;
}

const BASE_COLUMNS =
  'id, display_name, color, kind, owner_id, last_lat, last_lng, last_accuracy_m, last_battery_pct, last_fix_at, ' +
  'lost_mode, lost_mode_since, night_mode, night_start_min, night_end_min, night_interval_s, photo_path, household_id, last_seen_at';
const DEVICE_COLUMNS =
  BASE_COLUMNS + ', power_mode, model, fw_version, birth_date, breed, weight_kg, microchip, vet_name, vet_phone, lifestyle, notes';

const PROFILE_COLUMNS: Record<keyof CatProfile, string> = {
  birthDate: 'birth_date', breed: 'breed', weightKg: 'weight_kg', microchip: 'microchip',
  vetName: 'vet_name', vetPhone: 'vet_phone', lifestyle: 'lifestyle', notes: 'notes',
};

const SETTINGS_KEYS: Record<string, string> = {
  lang: 'lang', quietEnabled: 'quiet_enabled', quietStartMin: 'quiet_start_min', quietEndMin: 'quiet_end_min',
  timezone: 'timezone', historyDays: 'history_days',
};

function toSettings(r: Record<string, unknown>): UserSettings {
  return {
    lang: r.lang === 'nl' ? 'nl' : 'en',
    notify: {
      zone_exit: r.notify_zone_exit !== false,
      zone_enter: r.notify_zone_enter !== false,
      low_battery: r.notify_low_battery !== false,
      tracker_silent: r.notify_tracker_silent !== false,
      found: r.notify_found !== false,
    },
    quietEnabled: r.quiet_enabled === true,
    quietStartMin: Number(r.quiet_start_min ?? DEFAULT_SETTINGS.quietStartMin),
    quietEndMin: Number(r.quiet_end_min ?? DEFAULT_SETTINGS.quietEndMin),
    timezone: String(r.timezone ?? DEFAULT_SETTINGS.timezone),
    historyDays: ([30, 90, 180, 365].includes(Number(r.history_days)) ? Number(r.history_days) : 180) as HistoryDays,
  };
}

const PHOTO_BUCKET = 'cat-photos';

/**
 * Bytes of a local file. On phones this goes through expo-file-system:
 * fetch() on a file:// URI is not reliable in React Native and can produce an
 * empty upload, which then shows as a blank avatar.
 */
async function readLocalFile(uri: string): Promise<ArrayBuffer> {
  if (Platform.OS === 'web') return (await fetch(uri)).arrayBuffer();
  return new File(uri).arrayBuffer();
}
const SIGNED_URL_TTL_S = 3600;

interface ZoneRow {
  id: string;
  name: string;
  center_lat: number;
  center_lng: number;
  radius_m: number;
  all_cats: boolean;
  household_id: string | null;
  household_name: string | null;
}

const toZone = (r: ZoneRow): HomeZone => ({
  id: r.id, name: r.name, lat: r.center_lat, lng: r.center_lng, radiusM: r.radius_m, allCats: r.all_cats,
  householdId: r.household_id ?? null, householdName: r.household_name ?? null,
});

function toCat(r: DeviceRow, info: AccessInfo, place: CatPlace | null): Cat {
  return {
    id: r.id,
    name: r.display_name ?? tr('Unnamed cat'),
    color: r.color,
    kind: r.kind,
    ownerId: r.owner_id,
    lastLat: r.last_lat,
    lastLng: r.last_lng,
    lastAccuracyM: r.last_accuracy_m,
    lastBatteryPct: r.last_battery_pct,
    lastFixAt: r.last_fix_at,
    lostMode: r.lost_mode ?? false,
    lostModeSince: r.lost_mode_since ?? null,
    night: {
      enabled: r.night_mode ?? false,
      startMin: r.night_start_min ?? 1260,
      endMin: r.night_end_min ?? 420,
      intervalS: r.night_interval_s ?? 300,
    },
    photoPath: r.photo_path ?? null,
    householdId: r.household_id ?? null,
    householdName: info.householdName,
    access: info.access,
    sitterUntil: info.sitterUntil,
    lastSeenAt: r.last_seen_at ?? null,
    place,
    powerMode: r.power_mode ?? 'normal',
    model: r.model ?? null,
    fwVersion: r.fw_version ?? null,
    profile: {
      birthDate: r.birth_date ?? null,
      breed: r.breed ?? null,
      weightKg: r.weight_kg === null || r.weight_kg === undefined ? null : Number(r.weight_kg),
      microchip: r.microchip ?? null,
      vetName: r.vet_name ?? null,
      vetPhone: r.vet_phone ?? null,
      lifestyle: r.lifestyle ?? null,
      notes: r.notes ?? null,
    },
  };
}

function fail(error: { message: string } | null): asserts error is null {
  if (error) throw new Error(error.message);
}

export class SupabaseBackend implements Backend {
  readonly mode = 'supabase' as const;
  readonly userId: string;
  readonly userLabel: string;
  readonly #db: SupabaseClient;
  readonly #photoUrls = new Map<string, { url: string; expires: number }>();
  /** Latest my_cat_access result, reused for Realtime updates between refreshes. */
  readonly #access = new Map<string, AccessInfo>();
  /** Latest get_cat_status result: where each cat is relative to its zones. */
  readonly #places = new Map<string, CatPlace>();

  constructor(db: SupabaseClient, userId: string, email: string | undefined) {
    this.#db = db;
    this.userId = userId;
    this.userLabel = email ?? tr('Signed in');
  }

  async listCats(): Promise<Cat[]> {
    const [devices, access, status] = await Promise.all([
      this.#selectDevices(),
      this.#db.rpc('my_cat_access'),
      this.#db.rpc('get_cat_status'),
    ]);
    fail(devices.error);
    fail(access.error);
    this.#access.clear();
    for (const a of access.data as Array<{ device_id: string; access: CatAccess; household_name: string | null; sitter_until: string | null }>) {
      this.#access.set(a.device_id, { access: a.access, householdName: a.household_name, sitterUntil: a.sitter_until });
    }
    // Older databases without get_cat_status just show no place.
    this.#places.clear();
    for (const p of (status.error ? [] : status.data) as Array<{ device_id: string; zone_name: string | null; nearest_zone_name: string | null; nearest_zone_m: number | null }>) {
      if (p.zone_name !== null || p.nearest_zone_name !== null) {
        this.#places.set(p.device_id, { zoneName: p.zone_name, nearestZoneName: p.nearest_zone_name, nearestZoneM: p.nearest_zone_m });
      }
    }
    return (devices.data as unknown as DeviceRow[]).map((r) => this.#toCat(r));
  }

  /** Before migration 1200 the extra columns don't exist yet: fall back to the old set. */
  #fullColumns = true;
  async #selectDevices() {
    if (this.#fullColumns) {
      const res = await this.#db.from('devices').select(DEVICE_COLUMNS).order('created_at', { ascending: true });
      if (!res.error || !/column/i.test(res.error.message)) return res;
      this.#fullColumns = false;
    }
    return this.#db.from('devices').select(BASE_COLUMNS).order('created_at', { ascending: true });
  }

  #toCat(r: DeviceRow): Cat {
    const known = this.#access.get(r.id);
    return toCat(
      r,
      known ?? { access: r.owner_id === this.userId ? 'owner' : 'household', householdName: null, sitterUntil: null },
      this.#places.get(r.id) ?? null,
    );
  }

  async getTrackerHealth(catId: string): Promise<TrackerHealth> {
    const { data, error } = await this.#db.rpc('get_tracker_health', { p_device_id: catId });
    fail(error);
    const r = (data as Array<{
      last_seen_at: string | null; last_fix_at: string | null; battery_pct: number | null; drain_pct_per_day: number | null;
      days_left: number | null; fixes_24h: number; report_interval_s: number; silent: boolean | null; silent_after_s: number;
      resting?: boolean | null;
    }>)[0]!;
    return {
      lastSeenAt: r.last_seen_at, lastFixAt: r.last_fix_at, batteryPct: r.battery_pct, drainPctPerDay: r.drain_pct_per_day,
      daysLeft: r.days_left, fixes24h: r.fixes_24h, reportIntervalS: r.report_interval_s, silent: r.silent ?? false,
      silentAfterS: r.silent_after_s, resting: r.resting ?? false,
    };
  }

  subscribe(handlers: LiveHandlers): () => void {
    // RLS is applied per subscriber: users only receive their household's rows.
    const channel: RealtimeChannel = this.#db
      .channel(`cats-${Math.random().toString(36).slice(2)}`)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'devices' }, (payload) => {
        if (payload.eventType === 'DELETE') {
          const id = (payload.old as Partial<DeviceRow>).id;
          if (id) handlers.onCatRemoved?.(id);
          return;
        }
        const row = payload.new as DeviceRow;
        if (row.owner_id === null) {
          handlers.onCatRemoved?.(row.id);
          return;
        }
        handlers.onCat(this.#toCat(row));
      })
      .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'geofence_events' }, async (payload) => {
        const ev = payload.new as { id: number; device_id: string; geofence_id: string; transition: 'enter' | 'exit'; occurred_at: string; notify: boolean };
        if (!ev.notify) return;
        const { data } = await this.#db.from('geofences').select('name').eq('id', ev.geofence_id).maybeSingle();
        handlers.onEvent?.({
          id: String(ev.id), catId: ev.device_id, transition: ev.transition,
          zoneName: (data as { name: string } | null)?.name ?? 'zone', at: ev.occurred_at,
        });
      })
      .subscribe();

    return () => {
      void this.#db.removeChannel(channel);
    };
  }

  async addPhoneCat(name: string, color: string): Promise<string> {
    const { data, error } = await this.#db.rpc('create_phone_tracker', { p_name: name, p_color: color });
    fail(error);
    return data as string;
  }

  async isStaff(): Promise<boolean> {
    const { data, error } = await this.#db.rpc('is_staff');
    return !error && data === true; // older databases: nobody is staff
  }

  async staffCreateTracker(model: string, iccid?: string, deviceUid?: string): Promise<NewTrackerLabel> {
    const { data, error } = await this.#db.rpc('staff_create_tracker', {
      p_model: model.trim() || null, p_iccid: iccid?.trim() || null, p_device_uid: deviceUid?.trim() || null,
    });
    fail(error);
    const r = data as { device_uid: string; claim_code: string; model: string | null };
    return { deviceUid: r.device_uid, claimCode: r.claim_code, model: r.model };
  }

  async staffListTrackers(search?: string): Promise<StaffTracker[]> {
    const { data, error } = await this.#db.rpc('staff_list_trackers', { p_search: search?.trim() || null });
    fail(error);
    return (data as Array<Record<string, string | number | null>>).map((r) => ({
      deviceUid: r.device_uid as string, model: r.model as string | null, iccid: r.iccid as string | null,
      status: r.status as string, ownerEmail: r.owner_email as string | null, catName: r.cat_name as string | null,
      householdName: r.household_name as string | null, claimedAt: r.claimed_at as string | null,
      lastSeenAt: r.last_seen_at as string | null, batteryPct: r.battery_pct as number | null,
      registeredAt: r.registered_at as string, registeredBy: r.registered_by as string | null,
    }));
  }

  async staffResetTracker(deviceUid: string): Promise<string> {
    const { data, error } = await this.#db.rpc('staff_reset_tracker', { p_device_uid: deviceUid });
    fail(error);
    return data as string;
  }

  async checkClaimCode(deviceUid: string, claimCode: string): Promise<ClaimCheck> {
    const { data, error } = await this.#db.rpc('check_claim_code', {
      p_device_uid: deviceUid.trim(),
      p_claim_code: normalizeClaimCode(claimCode),
    });
    fail(error);
    const r = data as { status: ClaimCheck['status']; model?: string | null };
    return { status: r.status, model: r.model ?? null };
  }

  async claimCollar(deviceUid: string, claimCode: string): Promise<string> {
    const { data, error } = await this.#db.rpc('claim_device', {
      p_device_uid: deviceUid.trim(),
      p_claim_code: normalizeClaimCode(claimCode),
    });
    fail(error);
    return data as string;
  }

  async updateCat(id: string, changes: { name?: string; color?: string }): Promise<void> {
    const patch: Record<string, string> = {};
    if (changes.name !== undefined) patch.display_name = changes.name.trim();
    if (changes.color !== undefined) patch.color = changes.color;
    const { error } = await this.#db.from('devices').update(patch).eq('id', id);
    fail(error);
  }

  async removeCat(id: string): Promise<void> {
    const { error } = await this.#db.rpc('release_device', { p_device_id: id });
    fail(error);
  }

  async setPhoto(catId: string, localUri: string): Promise<void> {
    const body = await readLocalFile(localUri);
    if (body.byteLength === 0) throw new Error(tr('Could not read the photo. Please try again.'));
    const path = `${this.userId}/${catId}-${Date.now()}.jpg`;
    const { error } = await this.#db.storage.from(PHOTO_BUCKET).upload(path, body, { contentType: 'image/jpeg', upsert: false });
    fail(error);

    const { data: before } = await this.#db.from('devices').select('photo_path').eq('id', catId).maybeSingle();
    const { error: updError } = await this.#db.from('devices').update({ photo_path: path }).eq('id', catId);
    if (updError) {
      await this.#db.storage.from(PHOTO_BUCKET).remove([path]);
      fail(updError);
    }
    const old = (before as { photo_path: string | null } | null)?.photo_path;
    if (old) await this.#db.storage.from(PHOTO_BUCKET).remove([old]);
  }

  async removePhoto(catId: string): Promise<void> {
    const { data: before } = await this.#db.from('devices').select('photo_path').eq('id', catId).maybeSingle();
    const { error } = await this.#db.from('devices').update({ photo_path: null }).eq('id', catId);
    fail(error);
    const old = (before as { photo_path: string | null } | null)?.photo_path;
    if (old) await this.#db.storage.from(PHOTO_BUCKET).remove([old]);
  }

  async photoUrl(path: string): Promise<string | null> {
    const cached = this.#photoUrls.get(path);
    if (cached && cached.expires > Date.now() + 60_000) return cached.url;
    const { data, error } = await this.#db.storage.from(PHOTO_BUCKET).createSignedUrl(path, SIGNED_URL_TTL_S);
    if (error || !data) return null;
    this.#photoUrls.set(path, { url: data.signedUrl, expires: Date.now() + SIGNED_URL_TTL_S * 1000 });
    return data.signedUrl;
  }

  async setLostMode(catId: string, on: boolean): Promise<void> {
    const { error } = await this.#db.rpc('set_lost_mode', { p_device_id: catId, p_on: on });
    fail(error);
  }

  async setNightWatch(catId: string, night: NightWatch, timezone: string): Promise<void> {
    const { error } = await this.#db
      .from('devices')
      .update({
        night_mode: night.enabled,
        night_start_min: night.startMin,
        night_end_min: night.endMin,
        night_interval_s: night.intervalS,
        timezone,
      })
      .eq('id', catId);
    fail(error);
  }

  async reportLocation(catId: string, fix: PhoneFix): Promise<ReportResult> {
    const { data, error } = await this.#db.rpc('report_phone_location', {
      p_device_id: catId,
      p_lat: fix.lat,
      p_lng: fix.lng,
      p_accuracy_m: fix.accuracyM,
      p_battery_pct: fix.batteryPct,
      p_recorded_at: fix.at,
    });
    fail(error);
    const status = (data as { status?: string } | null)?.status;
    return status === 'ok' || status === 'duplicate' || status === 'rate_limited' ? status : 'rejected';
  }

  async getTrack(catId: string, sinceIso: string): Promise<TrackPoint[]> {
    const { data, error } = await this.#db.rpc('get_pet_track', { p_device_id: catId, p_since: sinceIso });
    fail(error);
    return (data as Array<{ recorded_at: string; lat: number; lng: number; accuracy_m: number; battery_pct: number }>).map(
      (r) => ({ at: r.recorded_at, lat: r.lat, lng: r.lng, accuracyM: r.accuracy_m, batteryPct: r.battery_pct }),
    );
  }

  async getHeatmap(catId: string, sinceIso: string): Promise<HeatCell[]> {
    const { data, error } = await this.#db.rpc('get_pet_heatmap', { p_device_id: catId, p_since: sinceIso, p_cell_m: 25 });
    fail(error);
    return (data as Array<{ lat: number; lng: number; weight_s: number }>).map((r) => ({ lat: r.lat, lng: r.lng, weightS: r.weight_s }));
  }

  async getActivity(catId: string, days: number): Promise<ActivityDay[]> {
    const { data, error } = await this.#db.rpc('get_pet_activity', { p_device_id: catId, p_days: days });
    fail(error);
    return (data as Array<{ day: string; distance_m: number; active_minutes: number; roam_radius_m: number | null; night_share: number | null; fixes: number }>).map(
      (r) => ({
        day: r.day, distanceM: r.distance_m, activeMinutes: r.active_minutes,
        roamRadiusM: r.roam_radius_m, nightShare: r.night_share, fixes: r.fixes,
      }),
    );
  }

  async getZones(catId: string): Promise<HomeZone[]> {
    const { data, error } = await this.#db.rpc('get_pet_geofences', { p_device_id: catId });
    fail(error);
    return (data as ZoneRow[]).map(toZone);
  }

  async getHouseholdZones(householdId: string): Promise<HomeZone[]> {
    const { data, error } = await this.#db.rpc('get_household_zones', { p_household_id: householdId });
    fail(error);
    return (data as ZoneRow[]).map(toZone);
  }

  async addZone(target: ZoneTarget, name: string, lat: number, lng: number, radiusM: number): Promise<void> {
    const { error } = await this.#db.rpc('create_circle_geofence', {
      p_device_id: 'catId' in target ? target.catId : null,
      p_household_id: 'householdId' in target ? target.householdId : null,
      p_name: name.trim() || tr('Home'), p_lat: lat, p_lng: lng, p_radius_m: radiusM, p_alert_on_enter: true,
    });
    fail(error);
  }

  async removeZone(zoneId: string): Promise<void> {
    const { error } = await this.#db.rpc('delete_zone', { p_zone_id: zoneId });
    fail(error);
  }

  async getEvents(catId: string): Promise<CatEvent[]> {
    const { data, error } = await this.#db
      .from('geofence_events')
      .select('id, device_id, transition, occurred_at, geofences(name)')
      .eq('device_id', catId)
      .order('occurred_at', { ascending: false })
      .limit(50);
    fail(error);
    return (data as unknown as Array<{ id: number; device_id: string; transition: 'enter' | 'exit'; occurred_at: string; geofences: { name: string } | null }>).map(
      (r) => ({ id: String(r.id), catId: r.device_id, transition: r.transition, zoneName: r.geofences?.name ?? 'zone', at: r.occurred_at }),
    );
  }

  async listHouseholds(): Promise<Household[]> {
    const { data, error } = await this.#db.rpc('list_households');
    fail(error);
    type Row = {
      household_id: string;
      name: string;
      my_role: HouseholdRole;
      members: Array<{ user_id: string; email: string; role: HouseholdRole }>;
      cat_count: number;
    };
    return (data as Row[]).map((r) => ({
      id: r.household_id,
      name: r.name,
      myRole: r.my_role,
      members: r.members.map((m) => ({ userId: m.user_id, email: m.email, role: m.role })),
      catCount: r.cat_count,
    }));
  }

  async createHousehold(name: string): Promise<string> {
    const { data, error } = await this.#db.rpc('create_household', { p_name: name });
    fail(error);
    return data as string;
  }

  async renameHousehold(householdId: string, name: string): Promise<void> {
    const { error } = await this.#db.rpc('rename_household', { p_household_id: householdId, p_name: name });
    fail(error);
  }

  async deleteHousehold(householdId: string): Promise<void> {
    const { error } = await this.#db.rpc('delete_household', { p_household_id: householdId });
    fail(error);
  }

  async createHouseholdInvite(householdId: string): Promise<string> {
    const { data, error } = await this.#db.rpc('create_household_invite', { p_household_id: householdId });
    fail(error);
    return data as string;
  }

  async removeMember(householdId: string, userId: string): Promise<void> {
    const { error } = await this.#db.rpc('remove_household_member', { p_household_id: householdId, p_user_id: userId });
    fail(error);
  }

  async leaveHousehold(householdId: string): Promise<void> {
    const { error } = await this.#db.rpc('leave_household', { p_household_id: householdId });
    fail(error);
  }

  async setCatHousehold(catId: string, householdId: string | null): Promise<void> {
    const { error } = await this.#db.rpc('set_cat_household', { p_device_id: catId, p_household_id: householdId });
    fail(error);
  }

  async createSitterInvite(catId: string, untilIso: string | null): Promise<string> {
    const { data, error } = await this.#db.rpc('create_sitter_invite', { p_device_id: catId, p_until: untilIso });
    fail(error);
    return data as string;
  }

  async listCatSitters(catId: string): Promise<CatSitter[]> {
    const { data, error } = await this.#db.rpc('list_cat_sitters', { p_device_id: catId });
    fail(error);
    return (data as Array<{ user_id: string; email: string; until: string | null }>).map((r) => ({
      userId: r.user_id,
      email: r.email,
      until: r.until,
    }));
  }

  async removeCatSitter(catId: string, userId: string): Promise<void> {
    const { error } = await this.#db.rpc('remove_cat_sitter', { p_device_id: catId, p_user_id: userId });
    fail(error);
  }

  async acceptInvite(code: string): Promise<InviteResult> {
    const { data, error } = await this.#db.rpc('accept_invite', { p_code: code });
    fail(error);
    const r = data as { kind: 'household' | 'sitter'; name: string };
    return { kind: r.kind, name: r.name };
  }

  async setPowerMode(catId: string, mode: PowerMode): Promise<void> {
    const { error } = await this.#db.from('devices').update({ power_mode: mode }).eq('id', catId);
    fail(error);
  }

  async updateProfile(catId: string, changes: Partial<CatProfile>): Promise<void> {
    const patch: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(changes) as Array<[keyof CatProfile, unknown]>) {
      patch[PROFILE_COLUMNS[k]] = typeof v === 'string' ? v.trim() || null : v;
    }
    const { error } = await this.#db.from('devices').update(patch).eq('id', catId);
    fail(error);
  }

  async replaceCollar(catId: string, deviceUid: string, claimCode: string): Promise<string> {
    const { data, error } = await this.#db.rpc('replace_collar', {
      p_old_device_id: catId, p_device_uid: deviceUid.trim(), p_claim_code: normalizeClaimCode(claimCode),
    });
    fail(error);
    return data as string;
  }

  async getTrackRange(catId: string, fromIso: string, toIso: string): Promise<TrackPoint[]> {
    const { data, error } = await this.#db.rpc('get_pet_track_range', { p_device_id: catId, p_from: fromIso, p_to: toIso });
    fail(error);
    return (data as Array<{ recorded_at: string; lat: number; lng: number; accuracy_m: number; battery_pct: number }>).map(
      (r) => ({ at: r.recorded_at, lat: r.lat, lng: r.lng, accuracyM: r.accuracy_m, batteryPct: r.battery_pct }),
    );
  }

  async listAlerts(limit = 50, beforeIso?: string): Promise<AlertItem[]> {
    const { data, error } = await this.#db.rpc('list_alerts', { p_limit: limit, p_before: beforeIso ?? null });
    fail(error);
    return (data as Array<{ id: number; device_id: string | null; kind: AlertKind; title: string; body: string; meta: Record<string, unknown> | null; created_at: string; unread: boolean }>).map(
      (r) => ({
        id: String(r.id), catId: r.device_id, kind: r.kind, title: r.title, body: r.body,
        meta: {
          zone: (r.meta?.zone as string | null | undefined) ?? null,
          battery: typeof r.meta?.battery === 'number' ? r.meta.battery : null,
          lastSeenAt: (r.meta?.last_seen_at as string | null | undefined) ?? null,
        },
        at: r.created_at, unread: r.unread,
      }),
    );
  }

  async unreadAlertCount(): Promise<number> {
    const { data, error } = await this.#db.rpc('unread_alert_count');
    return error ? 0 : Number(data ?? 0); // older databases: no inbox yet
  }

  async markAlertsRead(): Promise<void> {
    const { error } = await this.#db.rpc('mark_alerts_read');
    fail(error);
  }

  async getSettings(): Promise<UserSettings> {
    const { data, error } = await this.#db.rpc('get_my_settings');
    if (error) return { ...DEFAULT_SETTINGS, notify: { ...DEFAULT_SETTINGS.notify } };
    return toSettings(data as Record<string, unknown>);
  }

  async updateSettings(
    changes: Partial<Omit<UserSettings, 'notify'>> & { notify?: Partial<UserSettings['notify']> },
  ): Promise<UserSettings> {
    const patch: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(changes)) {
      if (k === 'notify') {
        for (const [kind, on] of Object.entries(v as Record<string, boolean>)) patch[`notify_${kind}`] = on;
      } else if (SETTINGS_KEYS[k]) {
        patch[SETTINGS_KEYS[k]!] = v;
      }
    }
    const { data, error } = await this.#db.rpc('set_my_settings', { p_changes: patch });
    fail(error);
    return toSettings(data as Record<string, unknown>);
  }

  async createShareLink(catId: string, hours: number): Promise<ShareLink> {
    const { data, error } = await this.#db.rpc('create_share_link', { p_device_id: catId, p_hours: hours });
    fail(error);
    const r = data as { token: string; expires_at: string };
    return { token: r.token, expiresAt: r.expires_at };
  }

  async getShareLink(catId: string): Promise<ShareLink | null> {
    const { data, error } = await this.#db.rpc('get_share_link', { p_device_id: catId });
    if (error || !data) return null;
    const r = data as { token: string; expires_at: string };
    return { token: r.token, expiresAt: r.expires_at };
  }

  async revokeShareLinks(catId: string): Promise<void> {
    const { error } = await this.#db.rpc('revoke_share_links', { p_device_id: catId });
    fail(error);
  }

  async exportMyData(): Promise<unknown> {
    const { data, error } = await this.#db.rpc('export_my_data');
    fail(error);
    return data;
  }

  async registerPushToken(token: string, platform: 'ios' | 'android' | 'web'): Promise<void> {
    const { error } = await this.#db.rpc('register_push_token', { p_token: token, p_platform: platform });
    fail(error);
  }

  async unregisterPushToken(token: string): Promise<void> {
    const { error } = await this.#db.rpc('unregister_push_token', { p_token: token });
    fail(error);
  }

  async deleteAccount(): Promise<void> {
    const { error } = await this.#db.functions.invoke('delete-account', { method: 'POST' });
    if (error) throw new Error(error.message);
    await this.#db.removeAllChannels();
    await this.#db.auth.signOut({ scope: 'local' });
  }

  async signOut(): Promise<void> {
    await this.#db.removeAllChannels();
    await this.#db.auth.signOut();
  }
}
