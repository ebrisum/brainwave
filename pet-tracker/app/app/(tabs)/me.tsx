/**
 * Me tab: account, households and sharing, alerts, appearance and language,
 * help, privacy and data, and the staff tools for staff accounts.
 */
import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';
import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { useApp } from '../../src/AppProvider';
import { supabase } from '../../src/backend/supabaseClient';
import { Button, Card, ErrorText, ListRow, SectionTitle } from '../../src/components/ui';
import { messageOf } from '../../src/dialogs';
import { t as tr } from '../../src/i18n';
import { useLang } from '../../src/i18n/LangProvider';
import { capabilities, isExpoGo } from '../../src/runtime';
import { fonts, radius, space, useTheme, useThemePref, type ThemePref } from '../../src/theme';

type Icon = keyof typeof Ionicons.glyphMap;

function Tiles<T extends string>({ value, options, onChange }: { value: T; options: ReadonlyArray<{ value: T; label: string; icon: Icon }>; onChange: (v: T) => void }) {
  const t = useTheme();
  return (
    <View style={styles.tiles}>
      {options.map((o) => {
        const selected = value === o.value;
        return (
          <Pressable
            key={o.value}
            accessibilityRole="radio"
            accessibilityState={{ selected }}
            onPress={() => onChange(o.value)}
            style={[styles.tile, { backgroundColor: t.surfaceAlt, borderColor: selected ? t.primary : 'transparent' }]}
          >
            <Ionicons name={o.icon} size={22} color={t.text} />
            <Text style={{ color: t.text, fontFamily: selected ? fonts.bodySemibold : fonts.bodyMedium }}>{o.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export default function MeTab() {
  const t = useTheme();
  const router = useRouter();
  const { pref, setPref } = useThemePref();
  const lang = useLang();
  const { backend, signOut, push, cats } = useApp();
  const [newPassword, setNewPassword] = useState('');
  const [staff, setStaff] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ text: string; tone: 'error' | 'info' } | null>(null);

  useEffect(() => {
    void backend?.isStaff().then(setStaff).catch(() => setStaff(false));
  }, [backend]);

  if (!backend) return null;
  const demo = backend.mode === 'demo';
  const input = [styles.input, { backgroundColor: t.surfaceAlt, color: t.text, borderColor: t.border }];

  const changePassword = async () => {
    setBusy('pw');
    setMessage(null);
    try {
      const { error } = await supabase!.auth.updateUser({ password: newPassword });
      if (error) throw new Error(error.message);
      setNewPassword('');
      setMessage({ text: tr('Password changed.'), tone: 'info' });
    } catch (e) {
      setMessage({ text: messageOf(e), tone: 'error' });
    } finally {
      setBusy(null);
    }
  };

  return (
    <ScrollView style={{ backgroundColor: t.bg }} contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
      <View style={styles.account}>
        <View style={[styles.accountAvatar, { backgroundColor: t.primary }]}>
          <Text style={{ color: t.primaryText, fontFamily: fonts.display, fontSize: 22 }}>{(backend.userLabel ?? 'D').slice(0, 1).toUpperCase()}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: t.text, fontFamily: fonts.display, fontSize: 20 }} numberOfLines={1}>
            {demo ? tr('Demo mode') : backend.userLabel}
          </Text>
          <Text style={{ color: t.textMuted }}>{demo ? tr('Nothing is stored') : tr('{n} cats on your account', { n: cats.length })}</Text>
        </View>
      </View>

      <Card style={{ gap: 0, paddingVertical: space.sm }}>
        <ListRow icon="people-outline" title={tr('Households & sharing')} subtitle={tr('People who see your cats, invites, cat sitters')} onPress={() => router.push('/household')} />
        <ListRow
          icon="notifications-outline"
          title={tr('Alerts')}
          subtitle={push.status === 'registered' ? tr('Push alerts on · choose which ones') : tr('Push alerts off')}
          onPress={() => router.push('/alert-settings')}
        />
        <ListRow icon="help-buoy-outline" title={tr('Help & support')} subtitle={tr('Collar guide, questions, contact')} onPress={() => router.push('/help')} />
        <ListRow
          icon="shield-checkmark-outline"
          title={tr('Privacy & data')}
          subtitle={tr('History, export, delete account')}
          onPress={() => router.push('/privacy')}
          last={!staff}
        />
        {staff && <ListRow icon="qr-code-outline" title={tr('Trackers & labels')} subtitle={tr('Staff: make QR labels, see who has which tracker')} onPress={() => router.push('/staff')} last />}
      </Card>

      <Card style={{ gap: space.md }}>
        <SectionTitle>{tr('Appearance')}</SectionTitle>
        <Tiles<ThemePref>
          value={pref}
          onChange={setPref}
          options={[
            { value: 'system', label: tr('System'), icon: 'phone-portrait-outline' },
            { value: 'light', label: tr('Light'), icon: 'sunny-outline' },
            { value: 'dark', label: tr('Dark'), icon: 'moon-outline' },
          ]}
        />
        <SectionTitle>{tr('Language')}</SectionTitle>
        <Tiles
          value={lang.pref}
          onChange={lang.setPref}
          options={[
            { value: 'system', label: tr('System'), icon: 'phone-portrait-outline' },
            { value: 'en', label: 'English', icon: 'language-outline' },
            { value: 'nl', label: 'Nederlands', icon: 'language-outline' },
          ]}
        />
      </Card>

      <Card style={{ gap: space.md }}>
        <SectionTitle>{tr('Account')}</SectionTitle>
        <ErrorText>{message?.tone === 'error' ? message.text : null}</ErrorText>
        {message?.tone === 'info' && <Text style={{ color: t.live, lineHeight: 20 }}>{message.text}</Text>}
        {!demo && supabase && (
          <View style={styles.row}>
            <TextInput
              style={[input, { flex: 1 }]}
              placeholder={tr('New password')}
              placeholderTextColor={t.textMuted}
              accessibilityLabel={tr('New password')}
              secureTextEntry
              value={newPassword}
              onChangeText={setNewPassword}
            />
            <Button title={tr('Change')} variant="secondary" busy={busy === 'pw'} disabled={newPassword.length < 8} onPress={() => void changePassword()} />
          </View>
        )}
        {!demo && newPassword.length > 0 && newPassword.length < 8 && (
          <Text style={{ color: t.textMuted, fontSize: 13 }}>{tr('A new password needs at least 8 characters.')}</Text>
        )}
        <Button
          title={demo ? tr('Exit demo') : tr('Sign out')}
          variant="secondary"
          icon="log-out-outline"
          onPress={() => void signOut().then(() => router.replace('/login'))}
        />
      </Card>

      <Text style={{ color: t.textMuted, textAlign: 'center', fontSize: 12 }}>
        Cat Tracker {Constants.expoConfig?.version ?? ''} · {isExpoGo ? 'Expo Go' : tr('installed app')}
        {capabilities.backgroundLocation ? ` · ${tr('background tracking available')}` : ''}
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: space.lg, gap: space.lg, paddingBottom: space.xl * 2, maxWidth: 640, width: '100%', alignSelf: 'center' },
  input: { borderWidth: 1, borderRadius: radius.md, paddingHorizontal: space.md, paddingVertical: 12, fontSize: 16 },
  row: { flexDirection: 'row', gap: space.sm, alignItems: 'center' },
  tiles: { flexDirection: 'row', gap: space.sm },
  tile: { flex: 1, alignItems: 'center', gap: space.xs, paddingVertical: space.md, borderRadius: radius.lg, borderWidth: 1.5 },
  account: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  accountAvatar: { width: 52, height: 52, borderRadius: 26, alignItems: 'center', justifyContent: 'center' },
});
