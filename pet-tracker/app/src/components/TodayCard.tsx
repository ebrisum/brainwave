/** Today at a glance: when the cat left and came back, and how far it walked. */
import { Ionicons } from '@expo/vector-icons';
import { StyleSheet, Text, View } from 'react-native';

import type { ActivityDay, Cat, CatEvent } from '../backend/types';
import { formatDistance } from '../geo';
import { todayStory } from '../place';
import { fmtDuration } from '../time';
import { fonts, space, useTheme } from '../theme';
import { Card, SectionTitle } from './ui';

const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

export function TodayCard({ cat, events, activity, hasZones }: { cat: Cat; events: CatEvent[]; activity: ActivityDay[]; hasZones: boolean }) {
  const t = useTheme();
  const story = todayStory(events);
  const today = activity[activity.length - 1];
  const isToday = today && today.day === new Date().toLocaleDateString('en-CA'); // YYYY-MM-DD, local
  const summary = isToday
    ? [
        `${formatDistance(today.distanceM)} walked`,
        today.activeMinutes >= 1 ? `${fmtDuration(today.activeMinutes * 60)} active` : null,
        today.roamRadiusM ? `furthest ${formatDistance(today.roamRadiusM)} from home` : null,
      ].filter(Boolean).join(' · ')
    : null;

  return (
    <Card style={{ gap: space.md }}>
      <SectionTitle>Today</SectionTitle>
      {summary && <Text style={{ color: t.text, fontFamily: fonts.bodyMedium, lineHeight: 20 }}>{summary}</Text>}

      {story.length === 0 ? (
        <Text style={{ color: t.textMuted, lineHeight: 20 }}>
          {hasZones
            ? cat.place?.zoneName
              ? `${cat.name} hasn't left ${cat.place.zoneName} today.`
              : `No zone changes today.`
            : `Set a home zone to see when ${cat.name} leaves and comes back.`}
        </Text>
      ) : (
        <View>
          {story.map((s, i) => {
            const last = i === story.length - 1;
            if (s.kind === 'away') {
              return (
                <View key={s.id} style={styles.item}>
                  <View style={styles.rail}>
                    <View style={[styles.dashed, { borderColor: t.border }]} />
                  </View>
                  <Text style={[styles.away, { color: s.ongoing ? t.text : t.textMuted }]}>
                    {s.ongoing ? `Out for ${fmtDuration(s.minutes * 60)} so far` : `Out for ${fmtDuration(s.minutes * 60)}`}
                  </Text>
                </View>
              );
            }
            const exit = s.transition === 'exit';
            return (
              <View key={s.id} style={styles.item}>
                <View style={styles.rail}>
                  <View style={[styles.dot, { borderColor: exit ? t.danger : t.live, backgroundColor: t.surface }]} />
                  {!last && <View style={[styles.line, { backgroundColor: t.border }]} />}
                </View>
                <View style={styles.eventText}>
                  <Ionicons name={exit ? 'exit-outline' : 'home-outline'} size={16} color={exit ? t.danger : t.live} />
                  <Text style={{ color: t.text, fontFamily: fonts.bodySemibold, flex: 1 }}>
                    {exit ? 'Left' : 'Back in'} {s.zoneName}
                  </Text>
                  <Text style={{ color: t.textMuted, fontFamily: 'GeistMono_500Medium', fontSize: 13 }}>{clock(s.at)}</Text>
                </View>
              </View>
            );
          })}
        </View>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  item: { flexDirection: 'row', gap: space.md, minHeight: 34 },
  rail: { width: 14, alignItems: 'center' },
  dot: { width: 14, height: 14, borderRadius: 7, borderWidth: 3, marginTop: 3 },
  line: { width: 2, flex: 1, marginTop: 2 },
  dashed: { width: 0, flex: 1, borderLeftWidth: 2, borderStyle: 'dashed' },
  eventText: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: space.sm, paddingBottom: space.sm },
  away: { fontSize: 13, paddingVertical: 4 },
});
