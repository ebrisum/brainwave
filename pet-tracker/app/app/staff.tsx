/**
 * Staff: make tracker labels and see who has which tracker. Every label is
 * registered in the backend the moment it is made (staff_create_tracker),
 * so scanning it in the app recognises it; claiming links it to the
 * customer, which the overview below shows. Only accounts in public.staff.
 */
import { Ionicons } from '@expo/vector-icons';
import { Stack, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ScrollView, Share, StyleSheet, Text, TextInput, View } from 'react-native';

import { useApp } from '../src/AppProvider';
import type { NewTrackerLabel, StaffTracker } from '../src/backend/types';
import { claimLink, prettyClaimCode } from '../src/claim';
import { QrCode } from '../src/components/QrCode';
import { Button, Card, ErrorText, Pill, SectionTitle } from '../src/components/ui';
import { ask, messageOf } from '../src/dialogs';
import { relativeTime } from '../src/geo';
import { fonts, radius, space, useTheme } from '../src/theme';

const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' }) : '');

export default function Staff() {
  const t = useTheme();
  const { backend } = useApp();
  const [model, setModel] = useState('Test collar');
  const [deviceUid, setDeviceUid] = useState('');
  const [iccid, setIccid] = useState('');
  const [label, setLabel] = useState<(NewTrackerLabel & { reissued?: boolean }) | null>(null);
  const [search, setSearch] = useState('');
  const [trackers, setTrackers] = useState<StaffTracker[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!backend) return;
    try {
      setTrackers(await backend.staffListTrackers(search));
    } catch (e) {
      setError(messageOf(e));
    }
  }, [backend, search]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  if (!backend) return null;
  const input = [styles.input, { backgroundColor: t.surfaceAlt, color: t.text, borderColor: t.border }];

  const make = async () => {
    setBusy('make');
    setError(null);
    try {
      setLabel(await backend.staffCreateTracker(model, iccid, deviceUid));
      setDeviceUid('');
      setIccid('');
      await load();
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(null);
    }
  };

  const reset = async (tr: StaffTracker) => {
    const yes = await ask(
      `Take back ${tr.deviceUid}?`,
      `${tr.ownerEmail ? `${tr.ownerEmail} loses this tracker and its history. ` : ''}It gets a new code; the old label stops working.`,
      'Take back',
      true,
    );
    if (!yes) return;
    setBusy(`reset-${tr.deviceUid}`);
    setError(null);
    try {
      const code = await backend.staffResetTracker(tr.deviceUid);
      setLabel({ deviceUid: tr.deviceUid, claimCode: code, model: tr.model, reissued: true });
      await load();
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: t.bg }} contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
      <Stack.Screen options={{ title: 'Trackers & labels' }} />
        <ErrorText>{error}</ErrorText>

        {label ? (
          <Card style={{ gap: space.md, alignItems: 'center' }}>
            <SectionTitle>{label.reissued ? 'New label (old one no longer works)' : 'New label'}</SectionTitle>
            <View style={[styles.label, { borderColor: t.border }]}>
              <QrCode value={claimLink(label.deviceUid, label.claimCode)} size={200} />
              <Text style={styles.labelBrand}>Cat Tracker</Text>
              <Text style={styles.labelHint}>Open the app → Add cat → GPS collar → Scan</Text>
              <Text style={styles.labelKey}>COLLAR ID</Text>
              <Text selectable style={styles.labelValue}>{label.deviceUid}</Text>
              <Text style={styles.labelKey}>CODE</Text>
              <Text selectable style={styles.labelValue}>{prettyClaimCode(label.claimCode)}</Text>
            </View>
            <Text style={{ color: t.textMuted, fontSize: 13, textAlign: 'center', lineHeight: 18 }}>
              Registered{label.model ? ` as ${label.model}` : ''}. Whoever has this code can add the tracker, so put
              the label inside the box.
            </Text>
            <View style={styles.row}>
              <Button
                title="Share"
                icon="share-outline"
                variant="secondary"
                style={{ flex: 1 }}
                onPress={() =>
                  void Share.share({
                    message: `Cat Tracker collar ${label.deviceUid}, code ${prettyClaimCode(label.claimCode)}\n${claimLink(label.deviceUid, label.claimCode)}`,
                  })
                }
              />
              <Button title="Done" style={{ flex: 1 }} onPress={() => setLabel(null)} />
            </View>
          </Card>
        ) : (
          <Card style={{ gap: space.sm }}>
            <SectionTitle>New label</SectionTitle>
            <Text style={{ color: t.textMuted, lineHeight: 20 }}>
              The tracker is registered right away and its QR code appears here. Leave the collar ID empty for a test
              label.
            </Text>
            <Text style={[styles.field, { color: t.textMuted }]}>Model</Text>
            <TextInput style={input} value={model} onChangeText={setModel} maxLength={32} accessibilityLabel="Model" />
            <Text style={[styles.field, { color: t.textMuted }]}>Collar ID (IMEI), optional</Text>
            <TextInput
              style={input}
              value={deviceUid}
              onChangeText={setDeviceUid}
              placeholder="e.g. 861234567890123"
              placeholderTextColor={t.textMuted}
              autoCapitalize="none"
              autoCorrect={false}
              accessibilityLabel="Collar ID"
            />
            <Text style={[styles.field, { color: t.textMuted }]}>SIM number (ICCID), optional</Text>
            <TextInput
              style={input}
              value={iccid}
              onChangeText={(v) => setIccid(v.replace(/\D/g, ''))}
              placeholder="8988…"
              placeholderTextColor={t.textMuted}
              keyboardType="number-pad"
              maxLength={22}
              accessibilityLabel="SIM number"
            />
            <Button title="Make label" icon="qr-code-outline" busy={busy === 'make'} onPress={() => void make()} />
          </Card>
        )}

        <Card style={{ gap: space.sm }}>
          <SectionTitle>Who has which tracker</SectionTitle>
          <TextInput
            style={input}
            value={search}
            onChangeText={setSearch}
            onSubmitEditing={() => void load()}
            placeholder="Search: collar ID, SIM or e-mail"
            placeholderTextColor={t.textMuted}
            autoCapitalize="none"
            returnKeyType="search"
            accessibilityLabel="Search trackers"
          />
          {trackers.length === 0 && <Text style={{ color: t.textMuted }}>No trackers yet.</Text>}
          {trackers.map((tr) => (
            <View key={tr.deviceUid} style={[styles.tracker, { borderBottomColor: t.border }]}>
              <View style={styles.row}>
                <Text style={[styles.trackerId, { color: t.text }]} selectable>{tr.deviceUid}</Text>
                {tr.model && <Pill label={tr.model} />}
                <View style={{ flex: 1 }} />
                {tr.ownerEmail ? <Pill label="Claimed" tone="live" /> : <Pill label="Not claimed yet" />}
              </View>
              {tr.ownerEmail && (
                <View style={styles.row}>
                  <Ionicons name="person-outline" size={14} color={t.textMuted} />
                  <Text style={{ color: t.text, flex: 1 }} numberOfLines={1}>
                    {tr.ownerEmail}
                    {tr.catName ? ` · ${tr.catName}` : ''}
                    {tr.householdName ? ` · ${tr.householdName}` : ''}
                  </Text>
                </View>
              )}
              <Text style={{ color: t.textMuted, fontSize: 12, lineHeight: 17 }}>
                Made {day(tr.registeredAt)}{tr.registeredBy ? ` by ${tr.registeredBy}` : ''}
                {tr.claimedAt ? ` · claimed ${day(tr.claimedAt)}` : ''}
                {tr.lastSeenAt ? ` · last check-in ${relativeTime(tr.lastSeenAt)}` : ''}
                {tr.iccid ? ` · SIM …${tr.iccid.slice(-6)}` : ''}
              </Text>
              {tr.ownerEmail && (
                <Button
                  title="Take back (return)"
                  variant="ghost"
                  textColor={t.danger}
                  busy={busy === `reset-${tr.deviceUid}`}
                  onPress={() => void reset(tr)}
                  style={{ alignSelf: 'flex-start' }}
                />
              )}
            </View>
          ))}
        </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: space.lg, gap: space.lg, paddingBottom: space.xl * 2, maxWidth: 640, width: '100%', alignSelf: 'center' },
  input: { borderWidth: 1, borderRadius: radius.md, paddingHorizontal: space.md, paddingVertical: 12, fontSize: 16, fontFamily: fonts.body },
  field: { fontFamily: fonts.bodySemibold, fontSize: 13, marginTop: space.xs },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  label: { backgroundColor: '#FFFFFF', borderWidth: 1, borderStyle: 'dashed', borderRadius: radius.md, padding: space.md, alignItems: 'center', gap: 2 },
  labelBrand: { color: '#111', fontFamily: fonts.display, fontSize: 18, marginTop: space.sm },
  labelHint: { color: '#555', fontSize: 12, marginBottom: space.xs },
  labelKey: { color: '#666', fontSize: 10, letterSpacing: 0.6, marginTop: space.xs },
  labelValue: { color: '#111', fontFamily: 'GeistMono_500Medium', fontSize: 18 },
  tracker: { gap: 4, paddingVertical: space.sm, borderBottomWidth: StyleSheet.hairlineWidth },
  trackerId: { fontFamily: 'GeistMono_500Medium', fontSize: 15 },
});
