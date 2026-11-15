/**
 * Cats tab: every cat as a card, grouped by household, with its place,
 * battery and collar status and the actions people look for most.
 */
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { useApp } from '../../src/AppProvider';
import type { Cat } from '../../src/backend/types';
import { AccessPill } from '../../src/components/AccessPill';
import { Button, CatAvatar, EmptyState, Pill } from '../../src/components/ui';
import { catBadge, usePhotoUrl } from '../../src/components/usePhotoUrl';
import { isLive, relativeTime } from '../../src/geo';
import { t as tr } from '../../src/i18n';
import { placeLine } from '../../src/place';
import { fonts, radius, space, useTheme } from '../../src/theme';

export default function CatsTab() {
  const t = useTheme();
  const router = useRouter();
  const { cats, trackedCatId } = useApp();

  const groups = new Map<string, { title: string; cats: Cat[] }>();
  for (const c of cats) {
    const key = c.access === 'sitter' ? 'sitter' : c.householdId ?? 'private';
    const title = c.access === 'sitter' ? tr('Cat sitting') : c.householdName ?? tr('Only you');
    if (!groups.has(key)) groups.set(key, { title, cats: [] });
    groups.get(key)!.cats.push(c);
  }

  return (
    <ScrollView style={{ backgroundColor: t.bg }} contentContainerStyle={styles.scroll}>
      {cats.length === 0 ? (
        <EmptyState icon="paw-outline" title={tr('No cats yet')} body={tr('Add your cat and pair its collar, or join a household with an invite code.')}>
          <Button title={tr('Add a cat')} icon="add" onPress={() => router.push('/add-cat')} />
          <Button title={tr('I have an invite code')} variant="ghost" onPress={() => router.push('/join')} />
        </EmptyState>
      ) : (
        <>
          {[...groups.values()].map((g) => (
            <View key={g.title} style={{ gap: space.sm }}>
              {groups.size > 1 && <Text style={[styles.group, { color: t.textMuted }]}>{g.title}</Text>}
              {g.cats.map((c) => (
                <CatCard key={c.id} cat={c} tracked={c.id === trackedCatId} />
              ))}
            </View>
          ))}
          <Button title={tr('Add a cat')} icon="add" variant="secondary" onPress={() => router.push('/add-cat')} />
        </>
      )}
    </ScrollView>
  );
}

function CatCard({ cat, tracked }: { cat: Cat; tracked: boolean }) {
  const t = useTheme();
  const router = useRouter();
  const photoUrl = usePhotoUrl(cat.photoPath);
  const live = isLive(cat.lastFixAt, tracked || cat.lostMode ? 5 * 60 : 20 * 60);
  const place = placeLine(cat);
  const low = cat.lastBatteryPct !== null && cat.lastBatteryPct > 0 && cat.lastBatteryPct < 20;
  const go = (pathname: '/cat/[id]' | '/lost/[id]' | '/find/[id]' | '/history/[id]' | '/collar/[id]') =>
    router.push({ pathname, params: { id: cat.id } });

  const actions: Array<{ icon: keyof typeof Ionicons.glyphMap; label: string; onPress: () => void; danger?: boolean }> = [
    { icon: 'alert-circle-outline', label: cat.lostMode ? tr('Searching') : tr('Lost?'), onPress: () => go('/lost/[id]'), danger: true },
    { icon: 'compass-outline', label: tr('Find'), onPress: () => go('/find/[id]') },
    { icon: 'calendar-outline', label: tr('History'), onPress: () => go('/history/[id]') },
    ...(cat.kind === 'collar' ? [{ icon: 'radio-outline' as const, label: tr('Collar'), onPress: () => go('/collar/[id]') }] : []),
  ];

  return (
    <View style={[styles.card, { backgroundColor: cat.lostMode ? t.dangerSoft : t.surface, shadowColor: t.shadow }]}>
      <Pressable accessibilityRole="button" accessibilityLabel={tr('Open {name}', { name: cat.name })} onPress={() => go('/cat/[id]')} style={styles.top}>
        <CatAvatar name={cat.name} color={cat.color} size={56} photoUrl={photoUrl} ring={cat.lostMode ? t.danger : undefined} badge={catBadge(cat, t)} />
        <View style={{ flex: 1, gap: 4 }}>
          <View style={styles.nameRow}>
            <Text style={[styles.name, { color: t.text }]} numberOfLines={1}>{cat.name}</Text>
            {cat.lostMode && <Pill label={tr('Lost')} tone="danger" icon="alert-circle" />}
            <AccessPill cat={cat} />
          </View>
          <Text style={{ color: place?.inside ? t.live : t.text, fontFamily: fonts.bodySemibold }} numberOfLines={1}>
            {place?.line ?? (cat.lastFixAt ? (live ? tr('Live') : tr('Last seen')) : tr('Waiting for first location'))}
          </Text>
          <Text style={{ color: t.textMuted, fontSize: 13 }} numberOfLines={1}>
            {[
              cat.lastFixAt ? relativeTime(cat.lastFixAt) : null,
              cat.lastBatteryPct ? (low ? tr('Battery low: {pct}%', { pct: cat.lastBatteryPct }) : tr('Battery {pct}%', { pct: cat.lastBatteryPct })) : null,
              cat.kind === 'phone' ? tr('Phone tracker') : null,
            ].filter(Boolean).join(' · ')}
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={18} color={t.textMuted} />
      </Pressable>
      <View style={[styles.actions, { borderTopColor: t.border }]}>
        {actions.map((a) => (
          <Pressable key={a.label} accessibilityRole="button" accessibilityLabel={`${a.label} · ${cat.name}`} onPress={a.onPress} style={styles.action}>
            <Ionicons name={a.icon} size={20} color={a.danger ? t.danger : t.text} />
            <Text style={{ color: a.danger ? t.danger : t.text, fontSize: 12, fontFamily: fonts.bodySemibold }}>{a.label}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: space.lg, gap: space.lg, paddingBottom: space.xl * 2, maxWidth: 640, width: '100%', alignSelf: 'center' },
  group: { fontSize: 13, fontFamily: fonts.bodySemibold, letterSpacing: 0.6, textTransform: 'uppercase' },
  card: { borderRadius: radius.lg, shadowOpacity: 1, shadowRadius: 16, shadowOffset: { width: 0, height: 4 }, elevation: 1 },
  top: { flexDirection: 'row', alignItems: 'center', gap: space.md, padding: space.lg },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: space.xs, flexWrap: 'wrap' },
  name: { fontFamily: fonts.display, fontSize: 20, flexShrink: 1, marginRight: space.xs },
  actions: { flexDirection: 'row', borderTopWidth: StyleSheet.hairlineWidth },
  action: { flex: 1, alignItems: 'center', gap: 4, paddingVertical: space.md },
});
