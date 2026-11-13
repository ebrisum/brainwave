/**
 * The tracker itself: is it checking in, how much battery is left (and for
 * how long), and what to do when it goes silent.
 */
import { Ionicons } from '@expo/vector-icons';
import { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { useApp } from '../AppProvider';
import type { Cat, TrackerHealth } from '../backend/types';
import { relativeTime } from '../geo';
import { fonts, radius, space, useTheme } from '../theme';
import { Card, Pill, SectionTitle } from './ui';

const LOW_PCT = 25;

function daysText(days: number): string {
  if (days < 1) return 'less than a day left';
  const d = Math.round(days);
  return `about ${d} ${d === 1 ? 'day' : 'days'} left`;
}

function intervalText(s: number): string {
  return s < 60 ? `every ${s} s` : `every ${Math.round(s / 60)} min`;
}

export function TrackerHealthCard({ cat }: { cat: Cat }) {
  const t = useTheme();
  const { backend } = useApp();
  const [health, setHealth] = useState<TrackerHealth | null>(null);

  // Reload whenever the tracker checks in.
  useEffect(() => {
    let active = true;
    void backend?.getTrackerHealth(cat.id).then((h) => active && setHealth(h)).catch(() => undefined);
    return () => {
      active = false;
    };
  }, [backend, cat.id, cat.lastSeenAt, cat.lastBatteryPct]);

  const battery = health?.batteryPct ?? cat.lastBatteryPct;
  const low = battery !== null && battery < LOW_PCT;
  const silent = health?.silent ?? false;
  const lastSeen = health?.lastSeenAt ?? cat.lastSeenAt ?? cat.lastFixAt;
  const name = cat.kind === 'phone' ? 'Phone tracker' : 'Collar';

  return (
    <Card style={{ gap: space.md }}>
      <View style={styles.header}>
        <SectionTitle>{name}</SectionTitle>
        {silent ? (
          <Pill label="Silent" tone="danger" icon="cloud-offline-outline" />
        ) : health?.resting ? (
          <Pill label="Resting" tone="night" icon="moon-outline" />
        ) : lastSeen ? (
          <Pill label="Checking in" tone="live" />
        ) : (
          <Pill label="Waiting for first check-in" />
        )}
      </View>

      {silent && (
        <View style={[styles.notice, { backgroundColor: t.dangerSoft }]}>
          <Ionicons name="alert-circle" size={20} color={t.danger} />
          <Text style={{ color: t.text, flex: 1, lineHeight: 20 }}>
            No check-in since {relativeTime(lastSeen)}.{' '}
            {low ? 'The battery was low: charge it and put it back on.' : `It may be out of mobile coverage (a cellar or shed), or switched off.`}
          </Text>
        </View>
      )}

      {health?.resting && !silent && (
        <View style={[styles.notice, { backgroundColor: t.nightSoft }]}>
          <Ionicons name="moon-outline" size={20} color={t.night} />
          <Text style={{ color: t.text, flex: 1, lineHeight: 20 }}>
            {cat.name} hasn't moved since {health.lastFixAt ? relativeTime(health.lastFixAt) : 'the last position'}, so the collar
            saves its battery: it checks in every few hours and sends a new position the moment {cat.name} moves.
          </Text>
        </View>
      )}

      {battery !== null && battery > 0 && (
        <View style={{ gap: 6 }}>
          <View style={styles.row}>
            <Ionicons name={low ? 'battery-dead-outline' : 'battery-half-outline'} size={20} color={low ? t.warn : t.text} />
            <Text style={[styles.big, { color: low ? t.warn : t.text }]}>{battery}%</Text>
            <Text style={{ color: t.textMuted, flex: 1 }} numberOfLines={1}>
              {health?.daysLeft != null
                ? daysText(health.daysLeft)
                : cat.kind === 'collar'
                  ? 'estimate after a few hours of use'
                  : ''}
            </Text>
          </View>
          <View style={[styles.bar, { backgroundColor: t.surfaceAlt }]}>
            <View style={[styles.fill, { width: `${battery}%`, backgroundColor: low ? t.warn : t.liveDot }]} />
          </View>
          {low && cat.kind === 'collar' && (
            <Text style={{ color: t.warn, fontFamily: fonts.bodySemibold }}>Charge {cat.name}'s collar tonight.</Text>
          )}
        </View>
      )}

      <View style={styles.facts}>
        <Fact label="Last check-in" value={lastSeen ? relativeTime(lastSeen) : '—'} />
        <Fact label="Positions today" value={health ? String(health.fixes24h) : '—'} />
        <Fact label="Reports" value={health ? intervalText(health.reportIntervalS) : '—'} />
      </View>
    </Card>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  const t = useTheme();
  return (
    <View style={{ flex: 1, gap: 2 }}>
      <Text style={{ color: t.textMuted, fontSize: 12 }}>{label}</Text>
      <Text style={{ color: t.text, fontFamily: fonts.bodySemibold }} numberOfLines={1}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  notice: { flexDirection: 'row', gap: space.sm, padding: space.md, borderRadius: radius.md, alignItems: 'flex-start' },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  big: { fontFamily: fonts.display, fontSize: 22 },
  bar: { height: 8, borderRadius: 4, overflow: 'hidden' },
  fill: { height: '100%', borderRadius: 4 },
  facts: { flexDirection: 'row', gap: space.md },
});
