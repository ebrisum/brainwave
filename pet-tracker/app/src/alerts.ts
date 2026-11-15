/** How an alert reads in the inbox: words from kind + facts, in the app's language. */
import type { AlertItem, AlertKind } from './backend/types';
import { t, tk } from './i18n/core.ts';
import { clock } from './time.ts';

export type AlertTone = 'danger' | 'live' | 'warn' | 'accent' | 'neutral';

export interface AlertView {
  title: string;
  body: string;
  icon: 'exit-outline' | 'home-outline' | 'battery-dead-outline' | 'alert-circle' | 'cloud-offline-outline' | 'heart-outline';
  tone: AlertTone;
}

export function alertView(a: Pick<AlertItem, 'kind' | 'meta'>, catName: string): AlertView {
  const zone = a.meta.zone ?? t('a zone');
  switch (a.kind) {
    case 'zone_exit':
      return { title: t('{name} left {zone}', { name: catName, zone }), body: t('Tap to see where {name} is now.', { name: catName }), icon: 'exit-outline', tone: 'danger' };
    case 'zone_enter':
      return { title: t('{name} is back in {zone}', { name: catName, zone }), body: t('All good, {name} came home.', { name: catName }), icon: 'home-outline', tone: 'live' };
    case 'low_battery':
      return {
        title: t("{name}'s collar battery is low", { name: catName }),
        body: a.meta.battery != null ? t('Battery at {pct}%. Charge it soon.', { pct: a.meta.battery }) : t('Charge it soon.'),
        icon: 'battery-dead-outline',
        tone: 'warn',
      };
    case 'lost_mode':
      return { title: t('Lost mode on for {name}', { name: catName }), body: t('Positions update as often as possible.'), icon: 'alert-circle', tone: 'danger' };
    case 'tracker_silent':
      return {
        title: t("{name}'s collar is silent", { name: catName }),
        body: a.meta.lastSeenAt ? t('No check-in since {time}.', { time: clock(a.meta.lastSeenAt) }) : t('No check-in for a while.'),
        icon: 'cloud-offline-outline',
        tone: 'neutral',
      };
    case 'found':
      return { title: t('{name} is found', { name: catName }), body: t('Lost mode is off again.'), icon: 'heart-outline', tone: 'live' };
  }
}

/** The alert kinds people can switch off, in the order the settings show them. */
export const ALERT_TOGGLES: ReadonlyArray<{ kind: Exclude<AlertKind, 'lost_mode'>; label: string; hint: string }> = [
  { kind: 'zone_exit', label: tk('Left a zone'), hint: tk('When a cat leaves home or another zone.') },
  { kind: 'zone_enter', label: tk('Back in a zone'), hint: tk('When a cat comes back.') },
  { kind: 'low_battery', label: tk('Battery low'), hint: tk('When a collar drops below 20%.') },
  { kind: 'tracker_silent', label: tk('Collar silent'), hint: tk("When a collar hasn't checked in for hours.") },
  { kind: 'found', label: tk('Cat found'), hint: tk('When lost mode is switched off again.') },
];
