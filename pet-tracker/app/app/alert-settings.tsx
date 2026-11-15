/**
 * Alerts: push on/off for this phone, which alerts you get, and quiet hours.
 * Stored on the server, so the push function follows them on every phone.
 */
import { Linking, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useState } from 'react';

import { ALERT_TOGGLES } from '../src/alerts';
import { useApp } from '../src/AppProvider';
import { Button, Card, ErrorText, SectionTitle, Toggle } from '../src/components/ui';
import { TimeField } from '../src/components/TimeField';
import { ask, messageOf } from '../src/dialogs';
import { t as tr } from '../src/i18n';
import { isExpoGo } from '../src/runtime';
import { deviceTimezone } from '../src/time';
import { fonts, radius, space, useTheme } from '../src/theme';

export default function AlertSettings() {
  const t = useTheme();
  const { backend, push, enablePush, settings, saveSettings } = useApp();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!backend) return null;
  const demo = backend.mode === 'demo';

  const save = async (key: string, changes: Parameters<typeof saveSettings>[0]) => {
    setBusy(key);
    setError(null);
    try {
      await saveSettings(changes);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(null);
    }
  };

  const pushText = {
    idle: tr('Off on this phone. Turn alerts on to hear when a cat leaves or comes home, a collar needs charging, or a cat is lost.'),
    pending: tr('Checking…'),
    registered: tr('On for this phone.'),
    denied: tr('Blocked for Cat Tracker. Allow notifications in your phone settings to get alerts.'),
    unsupported: demo
      ? tr('Not available in demo mode.')
      : isExpoGo
        ? tr('Needs the installed app. Expo Go cannot receive push alerts.')
        : tr('Not set up for this build yet.'),
    error: tr('Could not turn on alerts: {error}', { error: push.error ?? '?' }),
  }[push.status];

  const turnOn = async () => {
    const yes = await ask(
      tr('Turn on alerts?'),
      tr('Your phone asks for permission next. We only use it to tell you about your cats: leaving or coming home, battery, lost and found.'),
      tr('Continue'),
    );
    if (!yes) return;
    setBusy('push');
    try {
      await enablePush();
    } finally {
      setBusy(null);
    }
  };

  return (
    <ScrollView style={{ backgroundColor: t.bg }} contentContainerStyle={styles.scroll}>
      <Card style={{ gap: space.md }}>
        <View style={styles.rowBetween}>
          <Text style={{ color: t.text, fontFamily: fonts.display, fontSize: 18 }}>{tr('Push alerts')}</Text>
          <View style={[styles.onPill, { backgroundColor: push.status === 'registered' ? t.liveSoft : t.surfaceAlt }]}>
            <Text style={{ color: push.status === 'registered' ? t.live : t.textMuted, fontFamily: fonts.bodySemibold, fontSize: 12 }}>
              {push.status === 'registered' ? tr('On') : tr('Off')}
            </Text>
          </View>
        </View>
        <Text style={{ color: t.textMuted, lineHeight: 20 }}>{pushText}</Text>
        {!demo && push.status === 'idle' && <Button title={tr('Turn on alerts')} icon="notifications-outline" busy={busy === 'push'} onPress={() => void turnOn()} />}
        {!demo && push.status === 'denied' && (
          <Button title={tr('Open phone settings')} variant="secondary" icon="settings-outline" onPress={() => void Linking.openSettings().catch(() => undefined)} />
        )}
      </Card>

      {settings && (
        <>
          <Card style={{ gap: space.sm }}>
            <SectionTitle>{tr('Which alerts')}</SectionTitle>
            <Toggle label={tr('Lost mode')} hint={tr('Always on: everyone who sees the cat hears about it.')} value onChange={() => undefined} disabled />
            {ALERT_TOGGLES.map((a) => (
              <Toggle
                key={a.kind}
                label={tr(a.label)}
                hint={tr(a.hint)}
                value={settings.notify[a.kind]}
                disabled={busy !== null}
                onChange={(on) => void save(a.kind, { notify: { [a.kind]: on } })}
              />
            ))}
          </Card>

          <Card style={{ gap: space.md }}>
            <SectionTitle>{tr('Quiet hours')}</SectionTitle>
            <Toggle
              label={tr('Mute alerts at night')}
              hint={tr('Lost mode still comes through. Everything else waits in the Alerts tab.')}
              value={settings.quietEnabled}
              disabled={busy !== null}
              onChange={(on) => void save('quiet', { quietEnabled: on, timezone: deviceTimezone() })}
            />
            {settings.quietEnabled && (
              <View style={styles.row}>
                <View style={{ flex: 1 }}>
                  <TimeField label={tr('From')} minutes={settings.quietStartMin} onChange={(m) => void save('qs', { quietStartMin: m, timezone: deviceTimezone() })} />
                </View>
                <View style={{ flex: 1 }}>
                  <TimeField label={tr('Until')} minutes={settings.quietEndMin} onChange={(m) => void save('qe', { quietEndMin: m, timezone: deviceTimezone() })} />
                </View>
              </View>
            )}
          </Card>
        </>
      )}
      <ErrorText>{error}</ErrorText>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: space.lg, gap: space.lg, paddingBottom: space.xl * 2, maxWidth: 640, width: '100%', alignSelf: 'center' },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  onPill: { paddingHorizontal: space.md, paddingVertical: 4, borderRadius: radius.pill },
  row: { flexDirection: 'row', gap: space.md },
});
