/**
 * One interface, two implementations:
 *  - DemoBackend: runs entirely on the phone (simulated cats + this phone's GPS)
 *  - SupabaseBackend: the real stack (cloud/supabase/migrations)
 *
 * Feature set mirrors what REA recovered from Traccar's web app (live channel,
 * device list + map, events, route replay, client-reported positions) plus the
 * cat-specific parts: households, lost mode, night watch, heatmap, activity.
 */

export type TrackerKind = 'collar' | 'phone';

/** How the signed-in person can see a cat. */
export type CatAccess = 'owner' | 'household' | 'sitter';

export interface NightWatch {
  enabled: boolean;
  startMin: number; // local minutes after midnight, e.g. 21:00 = 1260
  endMin: number;
  intervalS: number;
}

export interface Cat {
  id: string;
  name: string;
  color: string;
  kind: TrackerKind;
  ownerId: string | null;
  lastLat: number | null;
  lastLng: number | null;
  lastAccuracyM: number | null;
  lastBatteryPct: number | null;
  lastFixAt: string | null; // ISO
  lostMode: boolean;
  lostModeSince: string | null;
  night: NightWatch;
  photoPath: string | null;
  /** Household the cat belongs to (null: private to its owner). */
  householdId: string | null;
  householdName: string | null;
  access: CatAccess;
  /** For a cat sitter: when access ends (null: until the owner stops it). */
  sitterUntil: string | null;
  /** Last check-in of the tracker, with or without a position. */
  lastSeenAt: string | null;
  /** In one of its zones, or how far from the nearest (null: no zones or no position yet). */
  place: CatPlace | null;
  /** Collars: how often it reports (battery saver / normal / live). */
  powerMode: PowerMode;
  /** Tracker model and firmware, for the collar page (null: unknown). */
  model: string | null;
  fwVersion: string | null;
  profile: CatProfile;
}

export type PowerMode = 'saver' | 'normal' | 'live';
export type Lifestyle = 'indoor' | 'outdoor' | 'both';

/** What the owner tells about the cat (all optional). */
export interface CatProfile {
  birthDate: string | null; // YYYY-MM-DD
  breed: string | null;
  weightKg: number | null;
  microchip: string | null;
  vetName: string | null;
  vetPhone: string | null;
  lifestyle: Lifestyle | null;
  notes: string | null;
}

export const EMPTY_PROFILE: CatProfile = {
  birthDate: null, breed: null, weightKg: null, microchip: null, vetName: null, vetPhone: null, lifestyle: null, notes: null,
};

export type AlertKind = 'zone_exit' | 'zone_enter' | 'low_battery' | 'lost_mode' | 'tracker_silent' | 'found';

/** One entry in the alerts inbox. title/body are the server's English text; the app words it from kind + meta. */
export interface AlertItem {
  id: string;
  catId: string | null;
  kind: AlertKind;
  title: string;
  body: string;
  meta: { zone?: string | null; battery?: number | null; lastSeenAt?: string | null };
  at: string; // ISO
  unread: boolean;
}

export type AlertToggle = 'zone_exit' | 'zone_enter' | 'low_battery' | 'tracker_silent' | 'found';
export type HistoryDays = 30 | 90 | 180 | 365;
export type Lang = 'en' | 'nl';

/** The signed-in person's settings (stored on the server, so pushes follow them too). */
export interface UserSettings {
  lang: Lang;
  notify: Record<AlertToggle, boolean>;
  quietEnabled: boolean;
  quietStartMin: number;
  quietEndMin: number;
  timezone: string;
  historyDays: HistoryDays;
}

export const DEFAULT_SETTINGS: UserSettings = {
  lang: 'en',
  notify: { zone_exit: true, zone_enter: true, low_battery: true, tracker_silent: true, found: true },
  quietEnabled: false,
  quietStartMin: 23 * 60,
  quietEndMin: 7 * 60,
  timezone: 'Europe/Amsterdam',
  historyDays: 180,
};

/** A link anyone can open to follow a (lost) cat until it expires. */
export interface ShareLink {
  token: string;
  expiresAt: string;
}

export interface CatPlace {
  /** The zone the cat is in, as decided for alerts (null: outside all zones). */
  zoneName: string | null;
  nearestZoneName: string | null;
  /** Distance to the edge of the nearest zone. */
  nearestZoneM: number | null;
}

/** A label made by staff: registered in the backend at once. */
export interface NewTrackerLabel {
  deviceUid: string;
  claimCode: string;
  model: string | null;
}

/** One tracker in the staff overview: who has it, since when, who made the label. */
export interface StaffTracker {
  deviceUid: string;
  model: string | null;
  iccid: string | null;
  status: string;
  ownerEmail: string | null;
  catName: string | null;
  householdName: string | null;
  claimedAt: string | null;
  lastSeenAt: string | null;
  batteryPct: number | null;
  registeredAt: string;
  registeredBy: string | null;
}

/** What a scanned or typed label says about its tracker, before linking it. */
export interface ClaimCheck {
  /** ready: free to add; yours: already in your account; taken: someone else's; invalid: wrong id or code. */
  status: 'ready' | 'yours' | 'taken' | 'invalid';
  model: string | null;
}

export interface TrackerHealth {
  lastSeenAt: string | null;
  lastFixAt: string | null;
  batteryPct: number | null;
  /** Battery use per day since the last charge (null: not enough data yet). */
  drainPctPerDay: number | null;
  daysLeft: number | null;
  fixes24h: number;
  reportIntervalS: number;
  /** Collar hasn't checked in for longer than silentAfterS. */
  silent: boolean;
  /** The collar's last check-in said the cat hasn't moved since lastFixAt (accelerometer). */
  resting: boolean;
  silentAfterS: number;
}

export interface TrackPoint {
  at: string; // ISO
  lat: number;
  lng: number;
  accuracyM: number;
  batteryPct: number;
}

export interface HomeZone {
  id: string;
  name: string;
  lat: number;
  lng: number;
  radiusM: number;
  /** Zone applies to several cats: its household's, or (older zones) all of the owner's. */
  allCats: boolean;
  /** Set for a household's zone: it applies to every cat in that household. */
  householdId: string | null;
  householdName: string | null;
}

/** Where a new zone applies: one cat, or every cat in a household. */
export type ZoneTarget = { catId: string } | { householdId: string };

export interface CatEvent {
  id: string;
  catId: string;
  transition: 'enter' | 'exit';
  zoneName: string;
  at: string; // ISO
}

export interface HeatCell {
  lat: number;
  lng: number;
  /** seconds spent in this ~25 m cell */
  weightS: number;
}

export interface ActivityDay {
  day: string; // YYYY-MM-DD (cat's local time)
  distanceM: number;
  activeMinutes: number;
  roamRadiusM: number | null;
  nightShare: number | null;
  fixes: number;
}

export type HouseholdRole = 'admin' | 'member';

export interface HouseholdMember {
  userId: string;
  email: string;
  role: HouseholdRole;
}

/** A group of people who all see the cats in it (e.g. "Home"). */
export interface Household {
  id: string;
  name: string;
  myRole: HouseholdRole;
  members: HouseholdMember[];
  catCount: number;
}

/** Someone following one cat without being in its household. */
export interface CatSitter {
  userId: string;
  email: string;
  /** ISO; null = until the owner stops it */
  until: string | null;
}

export interface InviteResult {
  kind: 'household' | 'sitter';
  /** Household name, or the cat's name for a sitter invite. */
  name: string;
}

export interface PhoneFix {
  lat: number;
  lng: number;
  accuracyM: number;
  batteryPct: number | null;
  at: string; // ISO
}

export type ReportResult = 'ok' | 'duplicate' | 'rate_limited' | 'rejected';

export interface LiveHandlers {
  onCat: (cat: Cat) => void;
  onCatRemoved?: (id: string) => void;
  onEvent?: (event: CatEvent) => void;
}

export interface Backend {
  readonly mode: 'demo' | 'supabase';
  readonly userId: string;
  readonly userLabel: string;

  listCats(): Promise<Cat[]>;
  /** Live updates (Supabase Realtime / demo simulation). Returns unsubscribe. */
  subscribe(handlers: LiveHandlers): () => void;

  addPhoneCat(name: string, color: string): Promise<string>;
  // Staff only (public.staff): making labels and the tracker overview.
  isStaff(): Promise<boolean>;
  staffCreateTracker(model: string, iccid?: string, deviceUid?: string): Promise<NewTrackerLabel>;
  staffListTrackers(search?: string): Promise<StaffTracker[]>;
  /** A returned tracker: removes the owner and history, returns the new claim code. */
  staffResetTracker(deviceUid: string): Promise<string>;

  /** Checks a label without linking anything. */
  checkClaimCode(deviceUid: string, claimCode: string): Promise<ClaimCheck>;
  claimCollar(deviceUid: string, claimCode: string): Promise<string>;
  updateCat(id: string, changes: { name?: string; color?: string }): Promise<void>;
  removeCat(id: string): Promise<void>;

  /** Upload a local image (already resized) as the cat's profile photo. */
  setPhoto(catId: string, localUri: string): Promise<void>;
  removePhoto(catId: string): Promise<void>;
  /** Resolve a stored photo path to a displayable URL (signed, cached). */
  photoUrl(path: string): Promise<string | null>;

  setLostMode(catId: string, on: boolean): Promise<void>;
  setNightWatch(catId: string, night: NightWatch, timezone: string): Promise<void>;

  /** "This phone is the cat's tracker": report one fix. */
  reportLocation(catId: string, fix: PhoneFix): Promise<ReportResult>;

  getTrack(catId: string, sinceIso: string): Promise<TrackPoint[]>;
  getHeatmap(catId: string, sinceIso: string): Promise<HeatCell[]>;
  getActivity(catId: string, days: number): Promise<ActivityDay[]>;

  getTrackerHealth(catId: string): Promise<TrackerHealth>;
  getZones(catId: string): Promise<HomeZone[]>;
  getHouseholdZones(householdId: string): Promise<HomeZone[]>;
  addZone(target: ZoneTarget, name: string, lat: number, lng: number, radiusM: number): Promise<void>;
  /** Your own zones, or any zone of a household you are in. */
  removeZone(zoneId: string): Promise<void>;
  getEvents(catId: string): Promise<CatEvent[]>;

  // Households: several per person; each cat is in one or private.
  listHouseholds(): Promise<Household[]>;
  createHousehold(name: string): Promise<string>;
  renameHousehold(householdId: string, name: string): Promise<void>;
  deleteHousehold(householdId: string): Promise<void>;
  createHouseholdInvite(householdId: string): Promise<string>;
  removeMember(householdId: string, userId: string): Promise<void>;
  leaveHousehold(householdId: string): Promise<void>;
  /** householdId null: the cat becomes private. Owner only. */
  setCatHousehold(catId: string, householdId: string | null): Promise<void>;

  // Cat sitters: follow one cat, optionally until a date.
  createSitterInvite(catId: string, untilIso: string | null): Promise<string>;
  listCatSitters(catId: string): Promise<CatSitter[]>;
  /** The owner removes a sitter, or a sitter (userId = self) stops. */
  removeCatSitter(catId: string, userId: string): Promise<void>;

  /** Accepts a household or a cat-sitter code. */
  acceptInvite(code: string): Promise<InviteResult>;

  // Collar and profile
  setPowerMode(catId: string, mode: PowerMode): Promise<void>;
  updateProfile(catId: string, changes: Partial<CatProfile>): Promise<void>;
  /** Moves the cat (profile, zones, sitters, history) onto a new collar; returns the cat's new id. */
  replaceCollar(catId: string, deviceUid: string, claimCode: string): Promise<string>;
  getTrackRange(catId: string, fromIso: string, toIso: string): Promise<TrackPoint[]>;

  // Alerts inbox and settings
  listAlerts(limit?: number, beforeIso?: string): Promise<AlertItem[]>;
  unreadAlertCount(): Promise<number>;
  markAlertsRead(): Promise<void>;
  getSettings(): Promise<UserSettings>;
  updateSettings(changes: Partial<Omit<UserSettings, 'notify'>> & { notify?: Partial<UserSettings['notify']> }): Promise<UserSettings>;

  // Live share links (lost cat)
  createShareLink(catId: string, hours: number): Promise<ShareLink>;
  getShareLink(catId: string): Promise<ShareLink | null>;
  revokeShareLinks(catId: string): Promise<void>;

  /** Everything stored about you and your cats (GDPR), as JSON. */
  exportMyData(): Promise<unknown>;

  // Notifications + account
  registerPushToken(token: string, platform: 'ios' | 'android' | 'web'): Promise<void>;
  unregisterPushToken(token: string): Promise<void>;
  deleteAccount(): Promise<void>;
  signOut(): Promise<void>;
}

export const CAT_COLORS = ['#F59E0B', '#EF4444', '#6366F1', '#10B981', '#EC4899', '#0EA5E9'] as const;

export const DEFAULT_NIGHT: NightWatch = { enabled: false, startMin: 21 * 60, endMin: 7 * 60, intervalS: 300 };

export const isOwner = (cat: Cat, backend: Backend) => cat.ownerId === null || cat.ownerId === backend.userId;
