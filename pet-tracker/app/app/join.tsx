/**
 * Joining a household or cat sitting from an invite link
 * (cattracker://join?code=… or https://<web>/join?code=…), a scanned QR code
 * or a typed code. Signed-out people log in first and come back here.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { useApp } from '../src/AppProvider';
import { Button, Card, ErrorText } from '../src/components/ui';
import { messageOf } from '../src/dialogs';
import { t as tr } from '../src/i18n';
import { inviteCodeFrom } from '../src/links';
import { PENDING_INVITE_KEY } from '../src/onboarding';
import { fonts, radius, space, useTheme } from '../src/theme';

export default function Join() {
  const t = useTheme();
  const router = useRouter();
  const params = useLocalSearchParams<{ code?: string }>();
  const { backend, ready, refresh } = useApp();
  const [code, setCode] = useState(params.code ? inviteCodeFrom(params.code) ?? '' : '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  // Not signed in yet: remember the code, log in, then come back.
  useEffect(() => {
    if (ready && !backend && params.code) {
      void AsyncStorage.setItem(PENDING_INVITE_KEY, params.code).finally(() => router.replace('/login'));
    }
  }, [ready, backend, params.code, router]);

  useEffect(() => {
    if (!params.code) {
      void AsyncStorage.getItem(PENDING_INVITE_KEY).then((c) => {
        if (c) {
          setCode(inviteCodeFrom(c) ?? '');
          void AsyncStorage.removeItem(PENDING_INVITE_KEY);
        }
      });
    }
  }, [params.code]);

  const join = async () => {
    if (!backend) return;
    setBusy(true);
    setError(null);
    try {
      const r = await backend.acceptInvite(code.replace(/[^A-Za-z0-9]/g, ''));
      await refresh();
      setDone(
        r.kind === 'household'
          ? tr('You joined {household}. Its cats are now in your list.', { household: r.name })
          : tr("You're now looking after {name}.", { name: r.name }),
      );
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  };

  const valid = code.replace(/[^A-Za-z0-9]/g, '').length === 8;
  return (
    <ScrollView style={{ backgroundColor: t.bg }} contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
      <Card style={{ gap: space.md }}>
        <Text style={{ color: t.text, fontFamily: fonts.display, fontSize: 22 }}>{tr('Join with an invite')}</Text>
        <Text style={{ color: t.textMuted, lineHeight: 20 }}>
          {tr('A household invite shows you all cats in that household. A cat-sitter invite lets you follow one cat for a while.')}
        </Text>
        {done ? (
          <>
            <Text style={{ color: t.live, fontFamily: fonts.bodySemibold, lineHeight: 22 }}>{done}</Text>
            <Button title={tr('See the cats')} onPress={() => router.replace('/cats')} />
          </>
        ) : (
          <>
            <View style={styles.row}>
              <TextInput
                style={[styles.input, { flex: 1, backgroundColor: t.surfaceAlt, color: t.text, borderColor: t.border }]}
                placeholder="ABCD-2345"
                placeholderTextColor={t.textMuted}
                accessibilityLabel={tr('Invite code')}
                autoCapitalize="characters"
                value={code}
                onChangeText={(v) => setCode(inviteCodeFrom(v) ?? v)}
                maxLength={64}
              />
            </View>
            <ErrorText>{error}</ErrorText>
            <Button title={tr('Join')} busy={busy} disabled={!valid || !backend || backend.mode === 'demo'} onPress={() => void join()} />
            {backend?.mode === 'demo' && <Text style={{ color: t.textMuted, fontSize: 13 }}>{tr('Invites need an account. Exit the demo and sign in.')}</Text>}
          </>
        )}
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: space.lg, gap: space.lg, paddingBottom: space.xl * 2, maxWidth: 640, width: '100%', alignSelf: 'center' },
  row: { flexDirection: 'row', gap: space.sm },
  input: { borderWidth: 1, borderRadius: radius.md, paddingHorizontal: space.md, paddingVertical: 12, fontSize: 20, fontFamily: 'GeistMono_500Medium', letterSpacing: 2 },
});
