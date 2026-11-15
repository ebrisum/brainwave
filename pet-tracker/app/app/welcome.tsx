/**
 * First launch: what the app does in three screens, then sign in or try the
 * demo. Permissions are asked later, each with an explanation, at the moment
 * they are needed (location for a zone, notifications in Alerts, camera for
 * the QR scan).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '../src/components/ui';
import { t as tr, tk } from '../src/i18n';
import { WELCOME_KEY } from '../src/onboarding';
import { fonts, radius, space, useTheme } from '../src/theme';

const SLIDES = [
  {
    icon: 'map-outline',
    title: tk('Always know where your cat is'),
    body: tk('The collar sends its position over the mobile network, also far from your phone. See it live on the map, and look back at every route.'),
  },
  {
    icon: 'home-outline',
    title: tk('Know when your cat leaves home'),
    body: tk('Set where home is once. You get an alert when your cat leaves or comes back, and the collar saves battery while your cat is home.'),
  },
  {
    icon: 'heart-outline',
    title: tk('Lost? Everyone helps search'),
    body: tk('Lost mode reports every few seconds, alerts your household and gives you a live link and a poster for the neighbours. No subscription, ever.'),
  },
] as const;

export default function Welcome() {
  const t = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [i, setI] = useState(0);
  const slide = SLIDES[i]!;
  const last = i === SLIDES.length - 1;

  const finish = async () => {
    await AsyncStorage.setItem(WELCOME_KEY, '1').catch(() => undefined);
    router.replace('/login');
  };

  return (
    <View style={[styles.screen, { backgroundColor: t.bg, paddingTop: insets.top + space.lg, paddingBottom: insets.bottom + space.lg }]}>
      <View style={styles.top}>
        <Text style={[styles.brand, { color: t.text }]}>Cat Tracker</Text>
        {!last && (
          <Pressable accessibilityRole="button" onPress={() => void finish()} hitSlop={12}>
            <Text style={{ color: t.textMuted, fontFamily: fonts.bodySemibold }}>{tr('Skip')}</Text>
          </Pressable>
        )}
      </View>

      <View style={styles.body}>
        <View style={[styles.art, { backgroundColor: t.accentSoft }]}>
          <Ionicons name={slide.icon} size={88} color={t.accent} />
        </View>
        <Text style={[styles.title, { color: t.text }]} accessibilityRole="header">{tr(slide.title)}</Text>
        <Text style={[styles.text, { color: t.textMuted }]}>{tr(slide.body)}</Text>
      </View>

      <View style={styles.dots}>
        {SLIDES.map((s, k) => (
          <View key={s.title} style={[styles.dot, { backgroundColor: k === i ? t.text : t.border, width: k === i ? 22 : 8 }]} />
        ))}
      </View>
      <Button title={last ? tr('Get started') : tr('Next')} onPress={() => (last ? void finish() : setI(i + 1))} />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, paddingHorizontal: space.xl, gap: space.lg },
  top: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  brand: { fontFamily: fonts.display, fontSize: 20 },
  body: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.lg, maxWidth: 480, alignSelf: 'center' },
  art: { width: 200, height: 200, borderRadius: radius.sheet * 2, alignItems: 'center', justifyContent: 'center', marginBottom: space.lg },
  title: { fontFamily: fonts.display, fontSize: 30, textAlign: 'center', letterSpacing: -0.6 },
  text: { fontSize: 17, lineHeight: 25, textAlign: 'center' },
  dots: { flexDirection: 'row', gap: 6, alignSelf: 'center' },
  dot: { height: 8, borderRadius: 4 },
});
