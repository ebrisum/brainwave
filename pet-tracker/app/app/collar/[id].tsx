/**
 * Collar: health (battery, check-ins, resting/silent), power mode, the
 * fitting and charging guide, moving the cat to a new collar, and giving the
 * collar back (sold, returned).
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { useApp } from '../../src/AppProvider';
import { isOwner, type PowerMode } from '../../src/backend/types';
import { normalizeClaimCode } from '../../src/claim';
import { QrScanner } from '../../src/components/QrScanner';
import { TrackerHealthCard } from '../../src/components/TrackerHealthCard';
import { Button, Card, ErrorText, ListRow, SectionTitle, Segmented } from '../../src/components/ui';
import { ask, messageOf } from '../../src/dialogs';
import { relativeTime } from '../../src/geo';
import { t as tr, tk } from '../../src/i18n';
import { fonts, radius, space, useTheme } from '../../src/theme';

const MODES: ReadonlyArray<{ value: PowerMode; label: string; hint: string }> = [
  { value: 'saver', label: tk('Battery saver'), hint: tk('A position every 30 minutes while your cat is out. Lasts longest.') },
  { value: 'normal', label: tk('Normal'), hint: tk('A position every 15 minutes while your cat is out, nothing extra at home.') },
  { value: 'live', label: tk('Live'), hint: tk('A position every 5 minutes. Uses about three times as much battery.') },
];

export default function CollarScreen() {
  const t = useTheme();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { backend, cats, refresh, removeCatLocal } = useApp();
  const cat = cats.find((c) => c.id === id);
  const [scan, setScan] = useState(false);
  const [newUid, setNewUid] = useState('');
  const [newCode, setNewCode] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!backend || !cat) return null;
  const owner = isOwner(cat, backend);
  const mode = MODES.find((m) => m.value === cat.powerMode) ?? MODES[1]!;
  const input = [styles.input, { backgroundColor: t.surfaceAlt, color: t.text, borderColor: t.border }];

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(null);
    }
  };

  const replace = async () => {
    const yes = await ask(
      tr('Move {name} to the new collar?', { name: cat.name }),
      tr("{name}'s profile, zones, cat sitters and history move to the new collar. The old collar is removed from your account.", { name: cat.name }),
      tr('Move'),
    );
    if (!yes) return;
    await run('replace', async () => {
      const newId = await backend.replaceCollar(cat.id, newUid, newCode);
      await refresh();
      router.replace({ pathname: '/cat/[id]', params: { id: newId } });
    });
  };

  const giveBack = async () => {
    const yes = await ask(
      tr('Remove this collar from your account?'),
      tr("Do this when you sell or return the collar. {name} and the collar's history are deleted from your account. This cannot be undone.", { name: cat.name }),
      tr('Remove collar'),
      true,
    );
    if (!yes) return;
    await run('release', async () => {
      await backend.removeCat(cat.id);
      removeCatLocal(cat.id);
      router.replace('/cats');
    });
  };

  return (
    <ScrollView style={{ backgroundColor: t.bg }} contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
      <TrackerHealthCard cat={cat} />

      <Card style={{ gap: 0, paddingVertical: space.sm }}>
        <ListRow icon="hardware-chip-outline" title={tr('Model')} subtitle={cat.model ?? tr('Unknown')} />
        <ListRow icon="code-slash-outline" title={tr('Firmware')} subtitle={cat.fwVersion ?? tr('Unknown')} />
        <ListRow icon="pulse-outline" title={tr('Last check-in')} subtitle={relativeTime(cat.lastSeenAt)} last />
      </Card>

      {cat.kind === 'collar' && (
        <Card style={{ gap: space.md }}>
          <SectionTitle>{tr('Power mode')}</SectionTitle>
          <Segmented<PowerMode>
            options={MODES.map((m) => ({ value: m.value, label: tr(m.label) }))}
            value={cat.powerMode}
            onChange={(v) => owner && void run('mode', () => backend.setPowerMode(cat.id, v))}
          />
          <Text style={{ color: t.textMuted, lineHeight: 20 }}>{tr(mode.hint)}</Text>
          {!owner && <Text style={{ color: t.textMuted, fontSize: 13 }}>{tr('Only the owner can change this.')}</Text>}
          {cat.lostMode && <Text style={{ color: t.danger, fontSize: 13 }}>{tr('Lost mode is on: the collar reports as often as it can until you switch it off.')}</Text>}
        </Card>
      )}

      <Card style={{ gap: space.sm }}>
        <SectionTitle>{tr('Fitting and charging')}</SectionTitle>
        {[
          tr('Breakaway collar, two fingers of room. Check the fit every week.'),
          tr('Charge on the magnetic charger when the app says 20%. A full charge takes about 2 hours.'),
          tr('The collar is waterproof for rain and puddles, not for swimming.'),
        ].map((line) => (
          <Text key={line} style={{ color: t.text, lineHeight: 20 }}>• {line}</Text>
        ))}
        <Button title={tr('Full guide and tips')} variant="ghost" onPress={() => router.push('/help')} />
      </Card>

      {owner && cat.kind === 'collar' && (
        <Card style={{ gap: space.md }}>
          <SectionTitle>{tr('New collar for this cat')}</SectionTitle>
          <Text style={{ color: t.textMuted, lineHeight: 20 }}>
            {tr('Broken or lost collar? Scan the label of the new one. Everything about {name} moves along.', { name: cat.name })}
          </Text>
          <Button title={tr('Scan the new label')} icon="qr-code-outline" variant="secondary" onPress={() => setScan(true)} />
          <TextInput style={input} placeholder={tr('Collar ID')} placeholderTextColor={t.textMuted} value={newUid} onChangeText={setNewUid} autoCapitalize="characters" autoCorrect={false} accessibilityLabel={tr('Collar ID')} />
          <TextInput style={input} placeholder={tr('Code')} placeholderTextColor={t.textMuted} value={newCode} onChangeText={setNewCode} autoCapitalize="characters" autoCorrect={false} accessibilityLabel={tr('Code')} />
          <Button
            title={tr('Move {name} to this collar', { name: cat.name })}
            busy={busy === 'replace'}
            disabled={newUid.trim().length < 3 || normalizeClaimCode(newCode).length < 8 || backend.mode === 'demo'}
            onPress={() => void replace()}
          />
        </Card>
      )}

      {owner && (
        <View style={{ gap: space.sm }}>
          <Button title={tr('Remove collar from my account')} variant="danger" icon="trash-outline" busy={busy === 'release'} onPress={() => void giveBack()} />
          <Text style={{ color: t.textMuted, fontSize: 13, textAlign: 'center' }}>{tr('For selling or returning the collar.')}</Text>
        </View>
      )}
      <ErrorText>{error}</ErrorText>

      <QrScanner
        visible={scan}
        onClose={() => setScan(false)}
        onScanned={(label) => {
          setScan(false);
          setNewUid(label.deviceUid);
          setNewCode(label.claimCode);
        }}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: space.lg, gap: space.lg, paddingBottom: space.xl * 2, maxWidth: 640, width: '100%', alignSelf: 'center' },
  input: { borderWidth: 1, borderRadius: radius.md, paddingHorizontal: space.md, paddingVertical: 12, fontSize: 16, fontFamily: fonts.body },
});
