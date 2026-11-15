/**
 * History: pick any day (or open the calendar further back) and see the
 * route on the map with the day as a timeline - at home, out (how far),
 * and the places the cat stopped.
 */
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';

import { useApp } from '../../src/AppProvider';
import type { HomeZone, TrackPoint } from '../../src/backend/types';
import { CatMap } from '../../src/components/CatMap';
import { Card, EmptyState, ErrorText } from '../../src/components/ui';
import { messageOf } from '../../src/dialogs';
import { distanceM, formatDistance } from '../../src/geo';
import { locale, t as tr } from '../../src/i18n';
import { clock, fmtDuration } from '../../src/time';
import { buildTimeline, dayRange, type TimelineEntry } from '../../src/timeline';
import { fonts, radius, space, useTheme } from '../../src/theme';

const DAYS_SHOWN = 30;

export default function HistoryScreen() {
  const t = useTheme();
  const { height } = useWindowDimensions();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { backend, cats, settings } = useApp();
  const cat = cats.find((c) => c.id === id);
  const [day, setDay] = useState(() => new Date());
  const [track, setTrack] = useState<TrackPoint[] | null>(null);
  const [zones, setZones] = useState<HomeZone[]>([]);
  const [error, setError] = useState<string | null>(null);

  const keep = Math.min(DAYS_SHOWN, settings?.historyDays ?? DAYS_SHOWN);
  const days = useMemo(
    () =>
      Array.from({ length: keep }, (_, i) => {
        const d = new Date();
        d.setHours(12, 0, 0, 0);
        d.setDate(d.getDate() - i);
        return d;
      }),
    [keep],
  );

  useEffect(() => {
    if (!backend || !id) return;
    let active = true;
    setTrack(null);
    const { from, to } = dayRange(day);
    void Promise.all([backend.getTrackRange(id, from, to), backend.getZones(id).catch(() => [])])
      .then(([tr2, zs]) => {
        if (!active) return;
        setTrack(tr2);
        setZones(zs);
        setError(null);
      })
      .catch((e) => active && (setError(messageOf(e)), setTrack([])));
    return () => {
      active = false;
    };
  }, [backend, id, day]);

  const timeline = useMemo(() => (track ? buildTimeline(track, zones) : []), [track, zones]);
  if (!cat) return null;

  const walked = (track ?? []).reduce((s, p, i, a) => (i === 0 ? 0 : s + distanceM(a[i - 1]!.lat, a[i - 1]!.lng, p.lat, p.lng)), 0);
  const outS = timeline.filter((e) => e.kind === 'out').reduce((s, e) => s + (Date.parse(e.to) - Date.parse(e.from)) / 1000, 0);
  const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();

  return (
    <ScrollView style={{ backgroundColor: t.bg }} contentContainerStyle={styles.scroll}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.days}>
        {days.map((d) => {
          const on = sameDay(d, day);
          return (
            <Pressable
              key={d.toISOString()}
              accessibilityRole="button"
              accessibilityState={{ selected: on }}
              onPress={() => setDay(d)}
              style={[styles.day, { backgroundColor: on ? t.primary : t.surface }]}
            >
              <Text style={{ color: on ? t.primaryText : t.textMuted, fontSize: 12, fontFamily: fonts.bodySemibold }}>
                {d.toLocaleDateString(locale(), { weekday: 'short' })}
              </Text>
              <Text style={{ color: on ? t.primaryText : t.text, fontFamily: fonts.display, fontSize: 20 }}>{d.getDate()}</Text>
            </Pressable>
          );
        })}
      </ScrollView>

      <Text style={[styles.title, { color: t.text }]}>
        {sameDay(day, new Date()) ? tr('Today') : day.toLocaleDateString(locale(), { weekday: 'long', day: 'numeric', month: 'long' })}
      </Text>

      {track === null ? (
        <ActivityIndicator color={t.accent} style={{ marginTop: space.xl }} />
      ) : track.length === 0 ? (
        <EmptyState icon="calendar-clear-outline" title={tr('No positions on this day')} body={tr('The collar was at rest, switched off, or this day is older than your history setting.')} />
      ) : (
        <>
          <View style={[styles.map, { height: Math.round(height * 0.32) }]}>
            <CatMap cats={[]} track={track} trackColor={cat.color} zones={zones} style={StyleSheet.absoluteFill} />
          </View>
          <View style={styles.stats}>
            <Stat label={tr('Walked')} value={formatDistance(walked)} />
            <Stat label={tr('Out')} value={outS > 0 ? fmtDuration(outS) : '–'} />
            <Stat label={tr('Positions')} value={String(track.length)} />
          </View>
          <Card style={{ gap: 0 }}>
            {timeline.map((e, i) => (
              <Row key={`${e.kind}-${e.from}-${i}`} e={e} last={i === timeline.length - 1} />
            ))}
          </Card>
        </>
      )}
      <ErrorText>{error}</ErrorText>
    </ScrollView>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  const t = useTheme();
  return (
    <View style={[styles.stat, { backgroundColor: t.surface }]}>
      <Text style={{ color: t.text, fontFamily: fonts.display, fontSize: 20 }}>{value}</Text>
      <Text style={{ color: t.textMuted, fontSize: 12 }}>{label}</Text>
    </View>
  );
}

function Row({ e, last }: { e: TimelineEntry; last: boolean }) {
  const t = useTheme();
  const minutes = Math.max(1, Math.round((Date.parse(e.to) - Date.parse(e.from)) / 60_000));
  const span = `${clock(e.from)}–${clock(e.to)}`;
  const view =
    e.kind === 'zone'
      ? { icon: 'home' as const, color: t.live, title: tr('At {zone}', { zone: e.zoneName }), sub: fmtDuration(minutes * 60) }
      : e.kind === 'out'
        ? {
            icon: 'walk' as const,
            color: t.accent,
            title: tr('Out for {time}', { time: fmtDuration(minutes * 60) }),
            sub: [formatDistance(e.distanceM), e.farthestM > 0 ? tr('up to {distance} from home', { distance: formatDistance(e.farthestM) }) : null].filter(Boolean).join(' · '),
          }
        : { icon: 'pause-circle' as const, color: t.night, title: tr('Stopped for {time}', { time: fmtDuration(minutes * 60) }), sub: tr('A favourite spot?') };
  return (
    <View style={[styles.row, { paddingLeft: e.kind === 'stop' ? space.xl : 0 }]}>
      <View style={styles.rail}>
        <View style={[styles.dot, { backgroundColor: view.color }]}>
          <Ionicons name={view.icon} size={14} color="#fff" />
        </View>
        {!last && <View style={[styles.line, { backgroundColor: t.border }]} />}
      </View>
      <View style={{ flex: 1, paddingBottom: space.md }}>
        <Text style={{ color: t.textMuted, fontFamily: fonts.mono, fontSize: 12 }}>{span}</Text>
        <Text style={{ color: t.text, fontFamily: fonts.bodySemibold }}>{view.title}</Text>
        {view.sub ? <Text style={{ color: t.textMuted, fontSize: 13 }}>{view.sub}</Text> : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: space.lg, gap: space.lg, paddingBottom: space.xl * 2, maxWidth: 640, width: '100%', alignSelf: 'center' },
  days: { gap: space.sm },
  day: { width: 52, paddingVertical: space.sm, borderRadius: radius.md, alignItems: 'center', gap: 2 },
  title: { fontFamily: fonts.display, fontSize: 22 },
  map: { borderRadius: radius.lg, overflow: 'hidden' },
  stats: { flexDirection: 'row', gap: space.sm },
  stat: { flex: 1, borderRadius: radius.md, padding: space.md, gap: 2 },
  row: { flexDirection: 'row', gap: space.md },
  rail: { alignItems: 'center', width: 26 },
  dot: { width: 26, height: 26, borderRadius: 13, alignItems: 'center', justifyContent: 'center' },
  line: { width: 2, flex: 1, marginVertical: 2 },
});
