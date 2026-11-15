/**
 * Insights: this week in numbers (distance, active time, night roaming,
 * how far from home) with a bar per day and a comparison to last week.
 */
import { useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';

import { useApp } from '../../src/AppProvider';
import type { ActivityDay } from '../../src/backend/types';
import { Card, EmptyState, ErrorText, SectionTitle } from '../../src/components/ui';
import { messageOf } from '../../src/dialogs';
import { formatDistance } from '../../src/geo';
import { locale, t as tr } from '../../src/i18n';
import { weekSummary } from '../../src/insights';
import { fmtDuration } from '../../src/time';
import { fonts, radius, space, useTheme } from '../../src/theme';

export default function InsightsScreen() {
  const t = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { backend, cats } = useApp();
  const cat = cats.find((c) => c.id === id);
  const [days, setDays] = useState<ActivityDay[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!backend || !id) return;
    void backend.getActivity(id, 14).then(setDays).catch((e) => (setError(messageOf(e)), setDays([])));
  }, [backend, id]);

  if (!cat) return null;
  if (days === null) return <ActivityIndicator color={t.accent} style={{ marginTop: space.xl * 2 }} />;
  const s = weekSummary(days);
  const week = [...days].sort((a, b) => a.day.localeCompare(b.day)).slice(-7);
  const max = Math.max(1, ...week.map((d) => d.distanceM));

  const story = [
    s.trend !== null
      ? s.trend >= 0.1
        ? tr('{name} walked {pct}% more than last week.', { name: cat.name, pct: Math.round(s.trend * 100) })
        : s.trend <= -0.1
          ? tr('{name} walked {pct}% less than last week.', { name: cat.name, pct: Math.round(-s.trend * 100) })
          : tr('About as active as last week.')
      : null,
    s.nightShare !== null && s.nightShare >= 0.5 ? tr('{name} is mostly out at night.', { name: cat.name }) : null,
    s.busiestDay
      ? tr('Busiest day: {day} ({distance}).', {
          day: new Date(`${s.busiestDay.day}T12:00:00`).toLocaleDateString(locale(), { weekday: 'long' }),
          distance: formatDistance(s.busiestDay.distanceM),
        })
      : null,
  ].filter(Boolean);

  return (
    <ScrollView style={{ backgroundColor: t.bg }} contentContainerStyle={styles.scroll}>
      <Text style={[styles.title, { color: t.text }]}>{tr("{name}'s week", { name: cat.name })}</Text>
      {s.daysWithData === 0 ? (
        <EmptyState icon="stats-chart-outline" title={tr('Not enough data yet')} body={tr('After a few days with the collar on, you see here how active {name} is.', { name: cat.name })} />
      ) : (
        <>
          <View style={styles.grid}>
            <Tile label={tr('Walked')} value={formatDistance(s.distanceM)} />
            <Tile label={tr('Active')} value={fmtDuration(s.activeMinutes * 60)} />
            <Tile label={tr('At night')} value={s.nightShare !== null ? `${Math.round(s.nightShare * 100)}%` : '–'} />
            <Tile label={tr('Farthest from home')} value={s.maxRoamM !== null ? formatDistance(s.maxRoamM) : '–'} />
          </View>

          <Card style={{ gap: space.md }}>
            <SectionTitle>{tr('Distance per day')}</SectionTitle>
            <View style={styles.bars}>
              {week.map((d) => (
                <View key={d.day} style={styles.barCol}>
                  <View style={[styles.barTrack, { backgroundColor: t.surfaceAlt }]}>
                    <View style={{ height: `${Math.round((d.distanceM / max) * 100)}%`, backgroundColor: cat.color, borderRadius: 6 }} />
                  </View>
                  <Text style={{ color: t.textMuted, fontSize: 12 }}>
                    {new Date(`${d.day}T12:00:00`).toLocaleDateString(locale(), { weekday: 'narrow' })}
                  </Text>
                </View>
              ))}
            </View>
          </Card>

          {story.length > 0 && (
            <Card style={{ gap: space.sm }}>
              <SectionTitle>{tr('What stands out')}</SectionTitle>
              {story.map((line) => (
                <Text key={line} style={{ color: t.text, lineHeight: 22 }}>• {line}</Text>
              ))}
            </Card>
          )}
        </>
      )}
      <ErrorText>{error}</ErrorText>
    </ScrollView>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  const t = useTheme();
  return (
    <View style={[styles.tile, { backgroundColor: t.surface }]}>
      <Text style={{ color: t.text, fontFamily: fonts.display, fontSize: 24 }}>{value}</Text>
      <Text style={{ color: t.textMuted, fontSize: 13 }}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: space.lg, gap: space.lg, paddingBottom: space.xl * 2, maxWidth: 640, width: '100%', alignSelf: 'center' },
  title: { fontFamily: fonts.display, fontSize: 26 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  tile: { width: '48.5%', borderRadius: radius.lg, padding: space.lg, gap: 4 },
  bars: { flexDirection: 'row', gap: space.sm, height: 140, alignItems: 'flex-end' },
  barCol: { flex: 1, alignItems: 'center', gap: 6, height: '100%' },
  barTrack: { flex: 1, width: '100%', borderRadius: 6, justifyContent: 'flex-end', overflow: 'hidden' },
});
