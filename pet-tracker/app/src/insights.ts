/** Weekly numbers for the insights screen, from get_pet_activity's days. */
import type { ActivityDay } from './backend/types';

export interface WeekSummary {
  distanceM: number;
  activeMinutes: number;
  /** Average share of movement at night (21:00-06:00), 0..1, or null without data. */
  nightShare: number | null;
  /** Largest roaming radius of the week. */
  maxRoamM: number | null;
  busiestDay: ActivityDay | null;
  /** Change in distance against the week before, as a fraction (+0.2 = 20 % more), or null. */
  trend: number | null;
  daysWithData: number;
}

const sum = (xs: readonly number[]) => xs.reduce((a, b) => a + b, 0);

/** days: newest or oldest first, any order; the last 7 calendar days form "this week". */
export function weekSummary(days: readonly ActivityDay[]): WeekSummary {
  const sorted = [...days].sort((a, b) => b.day.localeCompare(a.day));
  const week = sorted.slice(0, 7).filter((d) => d.fixes > 0);
  const before = sorted.slice(7, 14).filter((d) => d.fixes > 0);
  const nights = week.map((d) => d.nightShare).filter((x): x is number => x !== null);
  const roams = week.map((d) => d.roamRadiusM).filter((x): x is number => x !== null);
  const dist = sum(week.map((d) => d.distanceM));
  const prev = sum(before.map((d) => d.distanceM));
  return {
    distanceM: dist,
    activeMinutes: sum(week.map((d) => d.activeMinutes)),
    nightShare: nights.length ? sum(nights) / nights.length : null,
    maxRoamM: roams.length ? Math.max(...roams) : null,
    busiestDay: week.reduce<ActivityDay | null>((best, d) => (!best || d.distanceM > best.distanceM ? d : best), null),
    trend: before.length >= 3 && prev > 0 ? (dist - prev) / prev : null,
    daysWithData: week.length,
  };
}

/** How heavy a collar is for this cat: share of body weight (vets advise staying under ~4 %). */
export function collarShare(collarGrams: number, weightKg: number | null): number | null {
  return weightKg && weightKg > 0 ? collarGrams / (weightKg * 1000) : null;
}

/** Weight of our collar, used for the warning on the profile (grams). */
export const COLLAR_GRAMS = 19;
