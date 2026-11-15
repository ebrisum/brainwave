/**
 * Places tab: every zone in one list (per household, plus zones for a single
 * cat), with which cats are inside right now, on a map. Add or delete here.
 */
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';

import { useApp } from '../../src/AppProvider';
import { isOwner, type HomeZone, type Household } from '../../src/backend/types';
import { CatMap } from '../../src/components/CatMap';
import { Button, Card, EmptyState, ErrorText, ListRow, SectionTitle } from '../../src/components/ui';
import { ask, messageOf } from '../../src/dialogs';
import { distanceM, formatDistance } from '../../src/geo';
import { t as tr } from '../../src/i18n';
import { space, useTheme } from '../../src/theme';

interface Group {
  key: string;
  title: string;
  zones: HomeZone[];
  /** For "add": a household, or a cat the zone would be for. */
  add: { householdId: string } | { catId: string } | null;
  canDelete: boolean;
}

export default function PlacesTab() {
  const t = useTheme();
  const router = useRouter();
  const { height } = useWindowDimensions();
  const { backend, cats } = useApp();
  const [groups, setGroups] = useState<Group[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!backend) return;
    try {
      const households: Household[] = await backend.listHouseholds().catch(() => []);
      const out: Group[] = [];
      const seen = new Set<string>();
      for (const h of households) {
        const zones = await backend.getHouseholdZones(h.id).catch(() => []);
        zones.forEach((z) => seen.add(z.id));
        out.push({ key: h.id, title: h.name, zones, add: { householdId: h.id }, canDelete: true });
      }
      // Zones for one cat (and older "all my cats" zones), per cat you own.
      for (const c of cats.filter((x) => isOwner(x, backend))) {
        const zones = (await backend.getZones(c.id).catch(() => [])).filter((z) => !z.householdId && !seen.has(z.id));
        zones.forEach((z) => seen.add(z.id));
        if (zones.length) out.push({ key: c.id, title: tr('Only {name}', { name: c.name }), zones, add: { catId: c.id }, canDelete: true });
      }
      setGroups(out);
      setError(null);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setLoaded(true);
    }
  }, [backend, cats]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  if (!backend) return null;
  const allZones = groups.flatMap((g) => g.zones);
  const catsInside = (z: HomeZone) =>
    cats.filter((c) => c.lastLat !== null && c.lastLng !== null && distanceM(z.lat, z.lng, c.lastLat, c.lastLng) <= z.radiusM);
  const firstAdd = groups.find((g) => g.add)?.add ?? (cats[0] ? { catId: cats[0].id } : null);

  const remove = async (z: HomeZone) => {
    if (!(await ask(tr('Delete {zone}?', { zone: z.name }), tr('Alerts for this zone stop.'), tr('Delete zone'), true))) return;
    setBusy(z.id);
    try {
      await backend.removeZone(z.id);
      await load();
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <ScrollView style={{ backgroundColor: t.bg }} contentContainerStyle={styles.scroll}>
      {allZones.length > 0 && (
        <View style={[styles.map, { height: Math.round(height * 0.3) }]}>
          <CatMap cats={cats} zones={allZones} style={StyleSheet.absoluteFill} />
        </View>
      )}
      <ErrorText>{error}</ErrorText>

      {loaded && allZones.length === 0 && (
        <EmptyState
          icon="location-outline"
          title={tr('No places yet')}
          body={tr('Add a zone around your home: you get an alert when a cat leaves or comes back, and the collar saves battery there.')}
        >
          {firstAdd && <Button title={tr('Add your home')} icon="home-outline" onPress={() => router.push({ pathname: '/zone/new', params: firstAdd })} />}
        </EmptyState>
      )}

      {groups.map((g) => (
        <Card key={g.key} style={{ gap: 0 }}>
          <SectionTitle>{g.title}</SectionTitle>
          {g.zones.length === 0 && <Text style={{ color: t.textMuted, marginBottom: space.sm }}>{tr('No zones in this household yet.')}</Text>}
          {g.zones.map((z, i) => {
            const inside = catsInside(z);
            return (
              <ListRow
                key={z.id}
                icon={/home|thuis/i.test(z.name) ? 'home-outline' : 'location-outline'}
                title={z.name}
                subtitle={[
                  tr('{distance} radius', { distance: formatDistance(z.radiusM) }),
                  inside.length ? tr('Inside now: {names}', { names: inside.map((c) => c.name).join(', ') }) : tr('Nobody inside now'),
                ].join(' · ')}
                last={i === g.zones.length - 1 && !g.add}
                right={
                  g.canDelete ? (
                    <Button title={tr('Delete')} variant="ghost" busy={busy === z.id} onPress={() => void remove(z)} />
                  ) : undefined
                }
              />
            );
          })}
          {g.add && (
            <Button
              title={tr('Add a zone')}
              icon="add"
              variant="secondary"
              style={{ marginTop: space.md }}
              onPress={() => router.push({ pathname: '/zone/new', params: g.add! })}
            />
          )}
        </Card>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: space.lg, gap: space.lg, paddingBottom: space.xl * 2, maxWidth: 640, width: '100%', alignSelf: 'center' },
  map: { borderRadius: 24, overflow: 'hidden' },
});
