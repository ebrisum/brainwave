/**
 * Find: an arrow that points to the cat and the distance, from this phone's
 * GPS and compass. For the last few hundred metres, where a map is too coarse.
 */
import { Ionicons } from '@expo/vector-icons';
import * as Location from 'expo-location';
import { useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Linking, Platform, StyleSheet, Text, View } from 'react-native';

import { useApp } from '../../src/AppProvider';
import { Button, CatAvatar, ErrorText } from '../../src/components/ui';
import { usePhotoUrl } from '../../src/components/usePhotoUrl';
import { bearingDeg, distanceM, formatDistance, relativeTime } from '../../src/geo';
import { t as tr, tk } from '../../src/i18n';
import { directionsUrl } from '../../src/links';
import { fonts, space, useTheme } from '../../src/theme';

const COMPASS = [tk('north'), tk('north-east'), tk('east'), tk('south-east'), tk('south'), tk('south-west'), tk('west'), tk('north-west')];

export default function FindScreen() {
  const t = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { cats } = useApp();
  const cat = cats.find((c) => c.id === id);
  const photoUrl = usePhotoUrl(cat?.photoPath);
  const [me, setMe] = useState<{ lat: number; lng: number; acc: number } | null>(null);
  const [heading, setHeading] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let pos: Location.LocationSubscription | null = null;
    let head: Location.LocationSubscription | null = null;
    let cancelled = false;
    void (async () => {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (!perm.granted) {
        setError(tr('Allow location so the arrow can point from where you are.'));
        return;
      }
      pos = await Location.watchPositionAsync({ accuracy: Location.Accuracy.BestForNavigation, timeInterval: 1000, distanceInterval: 1 }, (p) =>
        setMe({ lat: p.coords.latitude, lng: p.coords.longitude, acc: p.coords.accuracy ?? 30 }),
      );
      if (Platform.OS !== 'web') {
        head = await Location.watchHeadingAsync((h) => setHeading(h.trueHeading >= 0 ? h.trueHeading : h.magHeading));
      }
      if (cancelled) {
        pos.remove();
        head?.remove();
      }
    })().catch(() => setError(tr('Could not read your location.')));
    return () => {
      cancelled = true;
      pos?.remove();
      head?.remove();
    };
  }, []);

  if (!cat) return null;
  const hasCat = cat.lastLat !== null && cat.lastLng !== null;
  const dist = me && hasCat ? distanceM(me.lat, me.lng, cat.lastLat!, cat.lastLng!) : null;
  const bearing = me && hasCat ? bearingDeg(me.lat, me.lng, cat.lastLat!, cat.lastLng!) : null;
  const rotate = bearing !== null ? bearing - (heading ?? 0) : 0;
  const close = dist !== null && dist < Math.max(15, (me?.acc ?? 10) + (cat.lastAccuracyM ?? 10));

  return (
    <View style={[styles.screen, { backgroundColor: t.bg }]}>
      <View style={styles.head}>
        <CatAvatar name={cat.name} color={cat.color} size={48} photoUrl={photoUrl} ring={cat.lostMode ? t.danger : undefined} />
        <View style={{ flex: 1 }}>
          <Text style={{ color: t.text, fontFamily: fonts.display, fontSize: 20 }}>{tr('Find {name}', { name: cat.name })}</Text>
          <Text style={{ color: t.textMuted }}>{tr('Position {when}', { when: relativeTime(cat.lastFixAt) })}</Text>
        </View>
      </View>

      <View style={styles.center}>
        {!hasCat ? (
          <Text style={{ color: t.textMuted, textAlign: 'center' }}>{tr('{name} has no position yet.', { name: cat.name })}</Text>
        ) : close ? (
          <>
            <Ionicons name="paw" size={120} color={t.live} />
            <Text style={[styles.big, { color: t.live }]}>{tr('Very close')}</Text>
            <Text style={{ color: t.textMuted, textAlign: 'center' }}>{tr('Look around and listen. Call softly.')}</Text>
          </>
        ) : (
          <>
            <View style={{ transform: [{ rotate: `${rotate}deg` }] }}>
              <Ionicons name="arrow-up-circle" size={200} color={cat.lostMode ? t.danger : t.text} />
            </View>
            <Text style={[styles.big, { color: t.text }]}>{dist !== null ? formatDistance(dist) : '…'}</Text>
            <Text style={{ color: t.textMuted, textAlign: 'center' }}>
              {bearing !== null
                ? heading === null
                  ? tr('To the {direction}', { direction: tr(COMPASS[Math.round(bearing / 45) % 8]!) })
                  : tr('Walk in the direction of the arrow')
                : tr('Finding your position…')}
            </Text>
          </>
        )}
      </View>

      <ErrorText>{error}</ErrorText>
      {hasCat && (
        <Button
          title={tr('Directions in maps')}
          icon="map-outline"
          variant="secondary"
          onPress={() => void Linking.openURL(directionsUrl(cat.lastLat!, cat.lastLng!)).catch(() => undefined)}
        />
      )}
      <Text style={{ color: t.textMuted, fontSize: 12, textAlign: 'center' }}>
        {tr('Hold the phone flat. Metal and magnets nearby can confuse the compass.')}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, padding: space.lg, gap: space.lg },
  head: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.md },
  big: { fontFamily: fonts.display, fontSize: 48, letterSpacing: -1 },
});
