/**
 * Privacy & data: privacy policy and terms, how long location history is
 * kept, exporting everything (GDPR), and deleting the account.
 */
import { File, Paths } from 'expo-file-system';
import { useRouter } from 'expo-router';
import * as Sharing from 'expo-sharing';
import { useState } from 'react';
import { Linking, Platform, ScrollView, StyleSheet, Text } from 'react-native';

import { useApp } from '../src/AppProvider';
import type { HistoryDays } from '../src/backend/types';
import { Button, Card, ErrorText, ListRow, SectionTitle, Segmented } from '../src/components/ui';
import { ask, messageOf } from '../src/dialogs';
import { t as tr } from '../src/i18n';
import { PRIVACY_URL, TERMS_URL } from '../src/links';
import { space, useTheme } from '../src/theme';

const HISTORY: ReadonlyArray<{ value: HistoryDays; label: string }> = [
  { value: 30, label: '30' },
  { value: 90, label: '90' },
  { value: 180, label: '180' },
  { value: 365, label: '365' },
];

export default function Privacy() {
  const t = useTheme();
  const router = useRouter();
  const { backend, settings, saveSettings, signOut } = useApp();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  if (!backend) return null;
  const demo = backend.mode === 'demo';

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    setInfo(null);
    try {
      await fn();
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(null);
    }
  };

  const exportData = () =>
    run('export', async () => {
      const json = JSON.stringify(await backend.exportMyData(), null, 2);
      const name = `cat-tracker-export-${new Date().toISOString().slice(0, 10)}.json`;
      if (Platform.OS === 'web') {
        const url = URL.createObjectURL(new Blob([json], { type: 'application/json' }));
        const a = document.createElement('a');
        a.href = url;
        a.download = name;
        a.click();
        URL.revokeObjectURL(url);
        return;
      }
      const file = new File(Paths.cache, name);
      file.create({ overwrite: true });
      await file.write(json);
      if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(file.uri, { mimeType: 'application/json', dialogTitle: tr('Your data') });
      else setInfo(tr('Saved as {file}.', { file: name }));
    });

  const deleteAccount = async () => {
    const yes = await ask(
      tr('Delete your account?'),
      tr('This permanently deletes your account, location history, zones, photos and household links. Collars are released so they can be claimed again. This cannot be undone.'),
      tr('Delete everything'),
      true,
    );
    if (!yes) return;
    await run('delete', async () => {
      await backend.deleteAccount();
      await signOut();
      router.replace('/login');
    });
  };

  return (
    <ScrollView style={{ backgroundColor: t.bg }} contentContainerStyle={styles.scroll}>
      <Card style={{ gap: 0, paddingVertical: space.sm }}>
        <ListRow
          icon="document-text-outline"
          title={tr('Privacy policy')}
          subtitle={PRIVACY_URL ? null : tr('Not published yet')}
          onPress={PRIVACY_URL ? () => void Linking.openURL(PRIVACY_URL) : undefined}
        />
        <ListRow
          icon="reader-outline"
          title={tr('Terms of use')}
          subtitle={TERMS_URL ? null : tr('Not published yet')}
          onPress={TERMS_URL ? () => void Linking.openURL(TERMS_URL) : undefined}
          last
        />
      </Card>

      <Card style={{ gap: space.md }}>
        <SectionTitle>{tr('Location history')}</SectionTitle>
        <Text style={{ color: t.textMuted, lineHeight: 20 }}>
          {tr('How many days of routes we keep for your cats. Older positions are deleted every night, for good.')}
        </Text>
        {settings && (
          <Segmented<HistoryDays>
            options={HISTORY.map((h) => ({ value: h.value, label: tr('{n} days', { n: h.label }) }))}
            value={settings.historyDays}
            onChange={(v) => void run('history', async () => void (await saveSettings({ historyDays: v })))}
          />
        )}
      </Card>

      <Card style={{ gap: space.md }}>
        <SectionTitle>{tr('Your data')}</SectionTitle>
        <Text style={{ color: t.textMuted, lineHeight: 20 }}>
          {tr('Download everything we store about you and your cats: account, cats, zones, alerts and every position, as one file.')}
        </Text>
        <Button title={tr('Export my data')} icon="download-outline" variant="secondary" busy={busy === 'export'} onPress={() => void exportData()} />
        {info && <Text style={{ color: t.live }}>{info}</Text>}
      </Card>

      {!demo && (
        <Card style={{ gap: space.md }}>
          <SectionTitle>{tr('Delete account')}</SectionTitle>
          <Text style={{ color: t.textMuted, lineHeight: 20 }}>{tr('Removes your account and everything in it. Your collars become free to add again.')}</Text>
          <Button title={tr('Delete account')} variant="danger" icon="trash-outline" busy={busy === 'delete'} onPress={() => void deleteAccount()} />
        </Card>
      )}
      <ErrorText>{error}</ErrorText>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: space.lg, gap: space.lg, paddingBottom: space.xl * 2, maxWidth: 640, width: '100%', alignSelf: 'center' },
});
