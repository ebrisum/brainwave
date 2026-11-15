/**
 * Live location from a share link, for people without an account
 * (neighbours helping to search). Works in the app and in the web build at
 * <EXPO_PUBLIC_WEB_URL>/share/<token>. Refreshes every 20 seconds.
 */
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Linking, StyleSheet, Text, View } from 'react-native';

import { supabase } from '../../src/backend/supabaseClient';
import { DEFAULT_NIGHT, EMPTY_PROFILE, type Cat } from '../../src/backend/types';
import { CatMap } from '../../src/components/CatMap';
import { Button, EmptyState } from '../../src/components/ui';
import { relativeTime } from '../../src/geo';
import { t as tr } from '../../src/i18n';
import { directionsUrl } from '../../src/links';
import { clock, shortDate } from '../../src/time';
import { fonts, radius, space, useTheme } from '../../src/theme';

interface Shared {
  name: string;
  color: string;
  lat: number | null;
  lng: number | null;
  accuracy_m: number | null;
  fix_at: string | null;
  lost_mode: boolean;
  expires_at: string;
}

const asCat = (s: Shared): Cat => ({
  id: 'shared', name: s.name, color: s.color, kind: 'collar', ownerId: null,
  lastLat: s.lat, lastLng: s.lng, lastAccuracyM: s.accuracy_m, lastBatteryPct: null, lastFixAt: s.fix_at,
  lostMode: s.lost_mode, lostModeSince: null, night: DEFAULT_NIGHT, photoPath: null, householdId: null, householdName: null,
  access: 'household', sitterUntil: null, lastSeenAt: s.fix_at, place: null, powerMode: 'normal', model: null, fwVersion: null,
  profile: EMPTY_PROFILE,
});

export default function SharedLocation() {
  const t = useTheme();
  const { token } = useLocalSearchParams<{ token: string }>();
  const [data, setData] = useState<Shared | null | 'gone'>(null);

  const load = useCallback(async () => {
    if (!supabase || !token) return setData('gone');
    const { data: r, error } = await supabase.rpc('get_shared_cat', { p_token: token });
    setData(error || !r ? 'gone' : (r as Shared));
  }, [token]);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 20_000);
    return () => clearInterval(timer);
  }, [load]);

  if (data === null) {
    return (
      <View style={[styles.center, { backgroundColor: t.bg }]}>
        <ActivityIndicator color={t.accent} />
      </View>
    );
  }
  if (data === 'gone') {
    return (
      <View style={[styles.center, { backgroundColor: t.bg }]}>
        <EmptyState icon="link-outline" title={tr('This link no longer works')} body={tr('The owner stopped sharing, or the cat has been found. Thank you for helping!')} />
      </View>
    );
  }

  const cat = asCat(data);
  return (
    <View style={{ flex: 1, backgroundColor: t.bg }}>
      <View style={{ flex: 1 }}>
        <CatMap cats={cat.lastLat !== null ? [cat] : []} focusId="shared" style={StyleSheet.absoluteFill} />
      </View>
      <View style={[styles.sheet, { backgroundColor: t.surface }]}>
        {data.lost_mode && (
          <View style={[styles.lost, { backgroundColor: t.dangerSoft }]}>
            <Ionicons name="alert-circle" size={18} color={t.danger} />
            <Text style={{ color: t.danger, fontFamily: fonts.bodySemibold }}>{tr('{name} is missing. Thank you for looking!', { name: data.name })}</Text>
          </View>
        )}
        <Text style={{ color: t.text, fontFamily: fonts.display, fontSize: 24 }}>{data.name}</Text>
        <Text style={{ color: t.textMuted, lineHeight: 20 }}>
          {data.fix_at
            ? tr('Position from {when} ({time}), accurate to about {m} m.', {
                when: relativeTime(data.fix_at), time: clock(data.fix_at), m: Math.round(data.accuracy_m ?? 20),
              })
            : tr('No position yet.')}
        </Text>
        <Text style={{ color: t.textMuted, fontSize: 13 }}>
          {tr('Seen {name}? Do not chase: stay calm and tell the owner.', { name: data.name })} {tr('This link works until {when}.', { when: `${shortDate(data.expires_at)} ${clock(data.expires_at)}` })}
        </Text>
        {data.lat !== null && data.lng !== null && (
          <Button title={tr('Directions')} icon="walk-outline" onPress={() => void Linking.openURL(directionsUrl(data.lat!, data.lng!)).catch(() => undefined)} />
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.lg },
  sheet: { padding: space.lg, gap: space.sm, borderTopLeftRadius: radius.sheet, borderTopRightRadius: radius.sheet, marginTop: -radius.sheet },
  lost: { flexDirection: 'row', alignItems: 'center', gap: space.sm, padding: space.md, borderRadius: radius.md },
});
