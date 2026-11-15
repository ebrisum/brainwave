/**
 * The five tabs: Map, Cats, Alerts, Places, Me. Signed-out people go to the
 * welcome screens (first launch) or the login.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons } from '@expo/vector-icons';
import { Redirect, Tabs, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, View } from 'react-native';

import { useApp } from '../../src/AppProvider';
import { t as tr } from '../../src/i18n';
import { PENDING_INVITE_KEY, WELCOME_KEY } from '../../src/onboarding';
import { fonts, useTheme } from '../../src/theme';


type Icon = keyof typeof Ionicons.glyphMap;
const icon = (name: Icon, active: Icon) =>
  function TabIcon({ color, focused, size }: { color: unknown; focused: boolean; size: number }) {
    return <Ionicons name={focused ? active : name} size={size - 2} color={typeof color === 'string' ? color : undefined} />;
  };

export default function TabsLayout() {
  const t = useTheme();
  const { ready, backend, unread } = useApp();
  const router = useRouter();
  const [welcomeSeen, setWelcomeSeen] = useState<boolean | null>(null);

  // An invite link opened before signing in: continue with it now.
  useEffect(() => {
    if (!backend) return;
    void AsyncStorage.getItem(PENDING_INVITE_KEY).then((code) => code && router.push('/join'));
  }, [backend, router]);

  useEffect(() => {
    AsyncStorage.getItem(WELCOME_KEY)
      .then((v) => setWelcomeSeen(v === '1'))
      .catch(() => setWelcomeSeen(true));
  }, []);

  if (!ready || welcomeSeen === null) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: t.bg }}>
        <ActivityIndicator color={t.accent} />
      </View>
    );
  }
  if (!backend) return <Redirect href={welcomeSeen ? '/login' : '/welcome'} />;

  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: t.bg },
        headerTintColor: t.text,
        headerTitleStyle: { fontFamily: fonts.display, fontSize: 18 },
        headerShadowVisible: false,
        tabBarActiveTintColor: t.text,
        tabBarInactiveTintColor: t.textMuted,
        tabBarStyle: { backgroundColor: t.surface, borderTopColor: t.border },
        tabBarLabelStyle: { fontFamily: fonts.bodySemibold, fontSize: 11 },
        sceneStyle: { backgroundColor: t.bg },
      }}
    >
      <Tabs.Screen name="index" options={{ title: tr('Map'), headerTitle: tr('My cats'), tabBarIcon: icon('map-outline', 'map') }} />
      <Tabs.Screen name="cats" options={{ title: tr('Cats'), tabBarIcon: icon('paw-outline', 'paw') }} />
      <Tabs.Screen
        name="alerts"
        options={{
          title: tr('Alerts'),
          tabBarIcon: icon('notifications-outline', 'notifications'),
          tabBarBadge: unread > 0 ? (unread > 99 ? '99+' : unread) : undefined,
          tabBarBadgeStyle: { backgroundColor: t.danger, color: '#fff', fontSize: 11 },
        }}
      />
      <Tabs.Screen name="places" options={{ title: tr('Places'), tabBarIcon: icon('location-outline', 'location') }} />
      <Tabs.Screen name="me" options={{ title: tr('Me'), tabBarIcon: icon('person-circle-outline', 'person-circle') }} />
    </Tabs>
  );
}
