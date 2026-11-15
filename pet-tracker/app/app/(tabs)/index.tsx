/**
 * Map tab: every cat on the map with the cat list below, lost-mode and zone
 * alerts, a sync status line, map controls (show all, me, satellite) and a
 * short first-run guide.
 */
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, FlatList, Linking, Platform, Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useApp } from '../../src/AppProvider';
import type { Cat } from '../../src/backend/types';
import { AccessPill } from '../../src/components/AccessPill';
import { CatMap } from '../../src/components/CatMap';
import { CatRow } from '../../src/components/CatRow';
import { TrackerBanner } from '../../src/components/TrackerBanner';
import { Button, CatAvatar, Pill } from '../../src/components/ui';
import { catBadge, usePhotoUrl } from '../../src/components/usePhotoUrl';
import { isLive, relativeTime } from '../../src/geo';
import { t as tr, tn } from '../../src/i18n';
import { directionsUrl } from '../../src/links';
import { placeLine } from '../../src/place';
import { fonts, radius, space, useTheme } from '../../src/theme';

/** Zone alerts fade out after this long; they stay in the Alerts tab. */
const ALERT_TTL_MS = 30_000;

function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}

export default function MapTab() {
  const t = useTheme();
  const router = useRouter();
  const { height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const now = useNow(15_000);
  const { ready, backend, cats, alert, dismissAlert, trackedCatId, tracker, openCatRequest, clearOpenCatRequest, lastSyncAt, syncFailed } = useApp();
  // Cat tapped on the map: zoom to it and show its card.
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [satellite, setSatellite] = useState(false);
  const [refitKey, setRefitKey] = useState(0);
  const [locateKey, setLocateKey] = useState(0);

  // Tapped a push notification -> open that cat.
  useEffect(() => {
    if (openCatRequest) {
      clearOpenCatRequest();
      router.push({ pathname: '/cat/[id]', params: { id: openCatRequest } });
    }
  }, [openCatRequest, clearOpenCatRequest, router]);

  useEffect(() => {
    if (!alert) return;
    const timer = setTimeout(dismissAlert, ALERT_TTL_MS);
    return () => clearTimeout(timer);
  }, [alert, dismissAlert]);

  if (!ready || !backend) {
    return (
      <View style={[styles.center, { backgroundColor: t.bg }]}>
        <ActivityIndicator color={t.accent} />
      </View>
    );
  }

  const alertCat = alert ? cats.find((c) => c.id === alert.catId) : undefined;
  const lost = cats.filter((c) => c.lostMode);
  const open = (id: string) => router.push({ pathname: '/cat/[id]', params: { id } });
  const selected = selectedId ? cats.find((c) => c.id === selectedId && c.lastLat !== null) : undefined;
  const liveCount = cats.filter((c) => isLive(c.lastFixAt, 20 * 60, now)).length;

  const syncLine =
    backend.mode === 'demo'
      ? tr('Demo · simulated positions')
      : syncFailed
        ? tr('Cannot reach the server · showing the last positions we have')
        : lastSyncAt
          ? tr('Updated {when}', { when: relativeTime(new Date(lastSyncAt).toISOString(), now) })
          : tr('Connecting…');

  const mapButtons: Array<{ icon: keyof typeof Ionicons.glyphMap; label: string; onPress: () => void; on?: boolean }> = [
    { icon: 'scan-outline', label: tr('Show all cats'), onPress: () => { setSelectedId(null); setRefitKey((k) => k + 1); } },
    ...(Platform.OS === 'web' ? [] : [
      { icon: 'navigate-outline' as const, label: tr('Show me'), onPress: () => setLocateKey((k) => k + 1) },
      { icon: 'earth-outline' as const, label: tr('Satellite'), onPress: () => setSatellite((v) => !v), on: satellite },
    ]),
  ];

  return (
    <View style={{ flex: 1, backgroundColor: t.bg }}>
      <View style={styles.map}>
        <CatMap
          cats={cats}
          style={StyleSheet.absoluteFill}
          focusId={selected?.id}
          onSelectCat={(catId) => setSelectedId((cur) => (cur === catId ? null : catId))}
          onPressMap={() => setSelectedId(null)}
          coverBottom={selected ? SELECTED_CARD_PX : 0}
          satellite={satellite}
          refitKey={refitKey}
          locateKey={locateKey}
        />
        {cats.length > 0 && (
          <View style={[styles.mapButtons, { top: insets.top + 64 }]}>
            {mapButtons.map((b) => (
              <Pressable
                key={b.label}
                accessibilityRole="button"
                accessibilityLabel={b.label}
                accessibilityState={b.on !== undefined ? { selected: b.on } : undefined}
                onPress={b.onPress}
                style={({ pressed }) => [styles.mapBtn, { backgroundColor: b.on ? t.primary : t.surface, opacity: pressed ? 0.8 : 1 }]}
              >
                <Ionicons name={b.icon} size={20} color={b.on ? t.primaryText : t.text} />
              </Pressable>
            ))}
          </View>
        )}
        {selected && (
          <SelectedCat cat={selected} now={now} onOpen={() => open(selected.id)} onClose={() => setSelectedId(null)} />
        )}
      </View>

      <View style={[styles.overlays, { top: insets.top + space.md }]} pointerEvents="box-none">
        {cats.length > 0 && (
          <View style={[styles.statusPill, { backgroundColor: t.surface }]}>
            <View style={[styles.dot, { backgroundColor: liveCount ? t.liveDot : t.border }]} />
            <Text style={{ color: t.text, fontFamily: fonts.bodySemibold, fontSize: 13 }}>
              {tn(cats.length, '{n} cat', '{n} cats')} · {tr('{n} live', { n: liveCount })}
            </Text>
          </View>
        )}
        {lost.map((c) => (
          <Pressable
            key={c.id}
            accessibilityRole="button"
            onPress={() => router.push({ pathname: '/lost/[id]', params: { id: c.id } })}
            style={[styles.banner, styles.stacked, { backgroundColor: t.danger }]}
          >
            <View style={styles.bannerRow}>
              <Ionicons name="alert-circle" size={20} color="#fff" />
              <Text style={styles.bannerText}>{tr('{name} is in lost mode', { name: c.name })}</Text>
            </View>
            <Text style={styles.bannerSub}>
              {c.lostModeSince ? `${tr('Since {when}', { when: relativeTime(c.lostModeSince, now) })} · ` : ''}
              {tr('Tap to search')}
            </Text>
          </Pressable>
        ))}
        {alert && (
          <View style={[styles.banner, { backgroundColor: alert.transition === 'exit' ? t.danger : t.live }]}>
            <Pressable
              accessibilityRole="button"
              style={styles.bannerMain}
              onPress={() => {
                dismissAlert();
                open(alert.catId);
              }}
            >
              <View style={styles.bannerRow}>
                <Ionicons name={alert.transition === 'exit' ? 'exit-outline' : 'home-outline'} size={20} color="#fff" />
                <Text style={styles.bannerText}>
                  {alert.transition === 'exit'
                    ? tr('{name} left {zone}', { name: alertCat?.name ?? tr('A cat'), zone: alert.zoneName })
                    : tr('{name} is back in {zone}', { name: alertCat?.name ?? tr('A cat'), zone: alert.zoneName })}
                </Text>
              </View>
              <Text style={styles.bannerSub}>{relativeTime(alert.at, now)} · {tr('Tap to view')}</Text>
            </Pressable>
            <Pressable accessibilityRole="button" accessibilityLabel={tr('Dismiss alert')} onPress={dismissAlert} hitSlop={12}>
              <Ionicons name="close" size={20} color="#fff" />
            </Pressable>
          </View>
        )}
      </View>

      <View style={[styles.sheet, { backgroundColor: t.surface }]}>
        <View style={[styles.grabber, { backgroundColor: t.border }]} />
        <View style={styles.sheetHeader}>
          <View style={{ flex: 1 }}>
            <Text style={[styles.sheetTitle, { color: t.text }]}>{tr('My cats')}</Text>
            <View style={styles.syncRow} accessibilityLiveRegion="polite">
              <Ionicons
                name={syncFailed ? 'cloud-offline-outline' : 'checkmark-circle-outline'}
                size={14}
                color={syncFailed ? t.danger : t.textMuted}
              />
              <Text style={{ color: syncFailed ? t.danger : t.textMuted, fontSize: 13, flex: 1 }}>{syncLine}</Text>
            </View>
          </View>
          {backend.mode === 'demo' && <Pill label={tr('Demo')} tone="accent" />}
          <Pressable accessibilityRole="button" onPress={() => router.push('/add-cat')} style={[styles.addPill, { backgroundColor: t.primary }]}>
            <Ionicons name="add" size={18} color={t.primaryText} />
            <Text style={{ color: t.primaryText, fontFamily: fonts.bodySemibold }}>{tr('Add cat')}</Text>
          </Pressable>
        </View>
        {tracker.state !== 'off' && (
          <View style={{ paddingHorizontal: space.lg, paddingBottom: space.sm }}>
            <TrackerBanner onPress={() => tracker.catId && open(tracker.catId)} />
          </View>
        )}
        <FlatList
          data={cats}
          keyExtractor={(c) => c.id}
          renderItem={({ item }) => <CatRow cat={item} trackedByPhone={item.id === trackedCatId} onPress={() => open(item.id)} />}
          ItemSeparatorComponent={() => <View style={[styles.sep, { backgroundColor: t.border }]} />}
          ListEmptyComponent={<FirstRun onAdd={() => router.push('/add-cat')} onJoin={() => router.push('/join')} />}
          style={{ flexGrow: 0, maxHeight: Math.round(height * 0.34) }}
        />
      </View>
    </View>
  );
}

/** Height the selected-cat card takes from the bottom of the map. */
const SELECTED_CARD_PX = 120;

/** Card for the cat tapped on the map: photo, name and status; tap to open, or get directions. */
function SelectedCat({ cat, now, onOpen, onClose }: { cat: Cat; now: number; onOpen: () => void; onClose: () => void }) {
  const t = useTheme();
  const photoUrl = usePhotoUrl(cat.photoPath);
  const live = isLive(cat.lastFixAt, 20 * 60, now);
  return (
    <View style={[styles.selected, { backgroundColor: t.surface }]}>
      <Pressable accessibilityRole="button" accessibilityLabel={tr('Open {name}', { name: cat.name })} onPress={onOpen} style={styles.selectedMain}>
        <CatAvatar name={cat.name} color={cat.color} size={64} photoUrl={photoUrl} ring={cat.lostMode ? t.danger : undefined} badge={catBadge(cat, t)} />
        <View style={{ flex: 1, gap: 4 }}>
          <Text style={[styles.selectedName, { color: t.text }]} numberOfLines={1}>{cat.name}</Text>
          <Text style={{ color: live ? t.live : t.textMuted, fontFamily: fonts.bodyMedium }} numberOfLines={1}>
            {cat.lostMode ? `${tr('Lost mode')} · ` : ''}{placeLine(cat)?.line ?? (live ? tr('Live') : tr('Last seen'))} · {relativeTime(cat.lastFixAt, now)}
            {cat.lastBatteryPct ? ` · ${cat.lastBatteryPct}%` : ''}
          </Text>
          <View style={{ flexDirection: 'row' }}>
            <AccessPill cat={cat} own />
          </View>
        </View>
      </Pressable>
      <View style={styles.selectedActions}>
        <Pressable accessibilityRole="button" accessibilityLabel={tr('Close')} onPress={onClose} hitSlop={10}>
          <Ionicons name="close" size={18} color={t.textMuted} />
        </Pressable>
        {cat.lastLat !== null && cat.lastLng !== null && (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={tr('Directions to {name}', { name: cat.name })}
            onPress={() => void Linking.openURL(directionsUrl(cat.lastLat!, cat.lastLng!)).catch(() => undefined)}
            style={[styles.routeBtn, { backgroundColor: t.surfaceAlt }]}
          >
            <Ionicons name="walk-outline" size={20} color={t.text} />
          </Pressable>
        )}
      </View>
    </View>
  );
}

/** Shown instead of an empty list: the three steps to a working tracker. */
function FirstRun({ onAdd, onJoin }: { onAdd: () => void; onJoin: () => void }) {
  const t = useTheme();
  const steps: [string, string][] = [
    [tr('Add your cat'), tr('Give it a name and a colour. A photo can come later.')],
    [tr('Choose its tracker'), tr('Use this phone for a quick test, or pair a GPS collar with the code on its label.')],
    [tr('Share with your household'), tr('Under Me, invite people to your household, or invite a cat sitter from a cat\'s edit screen.')],
  ];
  return (
    <View style={styles.firstRun}>
      <Text style={[styles.firstRunTitle, { color: t.text }]}>{tr("Let's get your cat on the map")}</Text>
      {steps.map(([title, body], i) => (
        <View key={title} style={styles.step}>
          <View style={[styles.stepNumber, { backgroundColor: t.primary }]}>
            <Text style={{ color: t.primaryText, fontFamily: fonts.bodySemibold }}>{i + 1}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ color: t.text, fontFamily: fonts.bodySemibold }}>{title}</Text>
            <Text style={{ color: t.textMuted, lineHeight: 20 }}>{body}</Text>
          </View>
        </View>
      ))}
      <Button title={tr('Add your first cat')} icon="add" onPress={onAdd} />
      <Button title={tr('I have an invite code')} variant="ghost" onPress={onJoin} />
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  map: { flex: 1 },
  mapButtons: { position: 'absolute', right: space.lg, gap: space.sm },
  mapBtn: {
    width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center',
    shadowColor: '#000', shadowOpacity: 0.14, shadowRadius: 10, elevation: 4,
  },
  selected: {
    position: 'absolute', left: space.lg, right: space.lg, bottom: radius.sheet + space.md, flexDirection: 'row',
    borderRadius: radius.lg, shadowColor: '#000', shadowOpacity: 0.16, shadowRadius: 16, elevation: 6,
  },
  selectedMain: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: space.md, padding: space.md },
  selectedActions: { justifyContent: 'space-between', alignItems: 'center', paddingVertical: space.sm, paddingRight: space.md },
  routeBtn: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  selectedName: { fontFamily: fonts.display, fontSize: 20 },
  overlays: { position: 'absolute', top: space.md, left: space.lg, right: space.lg, gap: space.sm },
  sheet: {
    borderTopLeftRadius: radius.sheet, borderTopRightRadius: radius.sheet, marginTop: -radius.sheet,
    paddingTop: space.sm, paddingBottom: space.sm, shadowColor: '#000', shadowOpacity: 0.12, shadowRadius: 16, elevation: 8,
  },
  statusPill: {
    alignSelf: 'center', flexDirection: 'row', alignItems: 'center', gap: space.sm,
    paddingHorizontal: space.md, paddingVertical: 8, borderRadius: radius.pill, shadowColor: '#000', shadowOpacity: 0.1, shadowRadius: 8, elevation: 3,
  },
  dot: { width: 8, height: 8, borderRadius: 4 },
  sheetHeader: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingHorizontal: space.lg, paddingBottom: space.sm },
  sheetTitle: { fontFamily: fonts.display, fontSize: 26, letterSpacing: -0.5 },
  addPill: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: space.md, paddingVertical: 10, borderRadius: radius.pill },
  grabber: { width: 40, height: 5, borderRadius: 3, alignSelf: 'center', marginBottom: space.sm },
  syncRow: { flexDirection: 'row', alignItems: 'center', gap: space.xs, marginTop: 2 },
  sep: { height: StyleSheet.hairlineWidth, marginLeft: 76 },
  firstRun: { padding: space.lg, gap: space.md },
  firstRunTitle: { fontFamily: fonts.display, fontSize: 22, letterSpacing: -0.4 },
  step: { flexDirection: 'row', gap: space.md, alignItems: 'flex-start' },
  stepNumber: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  banner: { borderRadius: radius.md, padding: space.md, flexDirection: 'row', alignItems: 'center', gap: space.sm, shadowColor: '#000', shadowOpacity: 0.2, shadowRadius: 10, elevation: 6 },
  stacked: { flexDirection: 'column', alignItems: 'stretch', gap: 0 },
  bannerMain: { flex: 1 },
  bannerRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  bannerText: { color: '#fff', fontFamily: fonts.bodySemibold, fontSize: 15, flexShrink: 1 },
  bannerSub: { color: 'rgba(255,255,255,0.88)', marginTop: 2, fontSize: 12, marginLeft: 28 },
});
