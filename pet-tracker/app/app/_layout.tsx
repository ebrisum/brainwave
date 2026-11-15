// Background location task must be defined at startup (expo-task-manager).
import '../src/tracking/background';

import { BricolageGrotesque_700Bold } from '@expo-google-fonts/bricolage-grotesque';
import { Geist_400Regular, Geist_500Medium, Geist_600SemiBold } from '@expo-google-fonts/geist';
import { GeistMono_500Medium } from '@expo-google-fonts/geist-mono';
import { Stack } from 'expo-router';
import { useFonts } from 'expo-font';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AppProvider } from '../src/AppProvider';
import { t as tr } from '../src/i18n';
import { LangProvider } from '../src/i18n/LangProvider';
import { configureNotifications } from '../src/notifications/push';
import { fonts, ThemePrefProvider, useTheme } from '../src/theme';

configureNotifications();

function ThemedStack() {
  const t = useTheme();
  return (
    <>
      <StatusBar style={t.isDark ? 'light' : 'dark'} />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: t.bg },
          headerTintColor: t.text,
          headerTitleStyle: { fontFamily: fonts.display, fontSize: 18 },
          headerShadowVisible: false,
          headerBackTitle: tr('Back'),
          contentStyle: { backgroundColor: t.bg },
        }}
      >
        <Stack.Screen name="(tabs)" options={{ headerShown: false, title: tr('Map') }} />
        <Stack.Screen name="welcome" options={{ headerShown: false }} />
        <Stack.Screen name="login" options={{ headerShown: false }} />
        <Stack.Screen name="reset-password" options={{ title: tr('Reset password') }} />
        <Stack.Screen name="add-cat" options={{ title: tr('Add a cat'), presentation: 'modal' }} />
        <Stack.Screen name="cat/[id]" options={{ title: '' }} />
        <Stack.Screen name="edit-cat/[id]" options={{ title: tr('Edit cat'), presentation: 'modal' }} />
        <Stack.Screen name="profile/[id]" options={{ title: tr('Cat profile'), presentation: 'modal' }} />
        <Stack.Screen name="collar/[id]" options={{ title: tr('Collar') }} />
        <Stack.Screen name="lost/[id]" options={{ title: tr('Lost cat') }} />
        <Stack.Screen name="find/[id]" options={{ title: tr('Find') }} />
        <Stack.Screen name="history/[id]" options={{ title: tr('History') }} />
        <Stack.Screen name="insights/[id]" options={{ title: tr('Insights') }} />
        <Stack.Screen name="zone/new" options={{ title: tr('New zone'), presentation: 'modal' }} />
        <Stack.Screen name="alert-settings" options={{ title: tr('Alerts') }} />
        <Stack.Screen name="household" options={{ title: tr('Households & sharing') }} />
        <Stack.Screen name="help" options={{ title: tr('Help & support') }} />
        <Stack.Screen name="privacy" options={{ title: tr('Privacy & data') }} />
        <Stack.Screen name="join" options={{ title: tr('Join') }} />
        <Stack.Screen name="share/[token]" options={{ title: tr('Live location') }} />
        <Stack.Screen name="staff" options={{ title: tr('Trackers & labels') }} />
      </Stack>
    </>
  );
}

export default function RootLayout() {
  // Fonts are bundled from @expo-google-fonts, so the first frame waits for them.
  const [loaded] = useFonts({
    BricolageGrotesque_700Bold,
    Geist_400Regular,
    Geist_500Medium,
    Geist_600SemiBold,
    GeistMono_500Medium,
  });
  if (!loaded) return null;
  return (
    <SafeAreaProvider>
      <ThemePrefProvider>
        <LangProvider>
          <AppProvider>
            <ThemedStack />
          </AppProvider>
        </LangProvider>
      </ThemePrefProvider>
    </SafeAreaProvider>
  );
}
