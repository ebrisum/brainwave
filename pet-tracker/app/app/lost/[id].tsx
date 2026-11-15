/**
 * Lost cat: switch lost mode on, then everything that helps find the cat -
 * walk to it (compass and directions), a live link for neighbours, a
 * "missing" poster with a QR code, a search checklist, and "Found!".
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons } from '@expo/vector-icons';
import * as Print from 'expo-print';
import { useLocalSearchParams, useRouter } from 'expo-router';
import * as Sharing from 'expo-sharing';
import { useEffect, useState } from 'react';
import { Linking, Platform, ScrollView, Share, StyleSheet, Text, TextInput, View, useWindowDimensions } from 'react-native';

import { useApp } from '../../src/AppProvider';
import type { ShareLink } from '../../src/backend/types';
import { CatMap } from '../../src/components/CatMap';
import { Button, Card, CatAvatar, ErrorText, SectionTitle } from '../../src/components/ui';
import { usePhotoUrl } from '../../src/components/usePhotoUrl';
import { ask, messageOf } from '../../src/dialogs';
import { relativeTime } from '../../src/geo';
import { t as tr, tk } from '../../src/i18n';
import { directionsUrl, hasWebLinks, shareUrl } from '../../src/links';
import { POSTER_PHONE_KEY } from '../../src/onboarding';
import { placeLine } from '../../src/place';
import { posterHtml } from '../../src/poster';
import { clock, shortDate } from '../../src/time';
import { fonts, radius, space, useTheme } from '../../src/theme';

const SHARE_HOURS = 72;

const CHECKLIST = [
  tk('Search at dusk and dawn, when it is quiet. Call softly and shake the food box.'),
  tk('Look in sheds, garages, basements and under cars nearby: scared cats hide close to home.'),
  tk('Ask neighbours to check their sheds, and share the live link in the street app.'),
  tk("Put the poster up and report your cat to the microchip database and the local animal shelter."),
  tk('Put a worn T-shirt and the litter box outside your door: the smell helps your cat find home.'),
] as const;

export default function LostScreen() {
  const t = useTheme();
  const router = useRouter();
  const { height } = useWindowDimensions();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { backend, cats } = useApp();
  const cat = cats.find((c) => c.id === id);
  const photoUrl = usePhotoUrl(cat?.photoPath);
  const [link, setLink] = useState<ShareLink | null>(null);
  const [phone, setPhone] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [found, setFound] = useState(false);

  useEffect(() => {
    if (backend && id) void backend.getShareLink(id).then(setLink).catch(() => undefined);
    void AsyncStorage.getItem(POSTER_PHONE_KEY).then((p) => p && setPhone(p));
  }, [backend, id]);

  if (!backend || !cat) return null;
  const place = placeLine(cat);
  const lastSeen = cat.lastFixAt
    ? `${place?.line ?? tr('Last position')} · ${shortDate(cat.lastFixAt)} ${clock(cat.lastFixAt)}`
    : tr('No position yet');

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

  const ensureLink = async (): Promise<ShareLink> => {
    if (link) return link;
    const l = await backend.createShareLink(cat.id, SHARE_HOURS);
    setLink(l);
    return l;
  };

  const shareLive = () =>
    run('share', async () => {
      const l = await ensureLink();
      await Share.share({
        message: tr('{name} is missing. Follow where {name} is right now: {link}', { name: cat.name, link: shareUrl(l.token) }),
      });
    });

  const poster = () =>
    run('poster', async () => {
      if (phone.trim()) await AsyncStorage.setItem(POSTER_PHONE_KEY, phone.trim());
      const l = hasWebLinks() ? await ensureLink() : null;
      const p = cat.profile;
      const description = [p.breed, p.lifestyle === 'indoor' ? tr('indoor cat, not used to being outside') : null, p.microchip ? tr('chipped') : null, p.notes]
        .filter(Boolean)
        .join(' · ');
      const html = posterHtml({
        name: cat.name, photoUrl, color: cat.color, description, lastSeen, phone: phone.trim(),
        shareUrl: l ? shareUrl(l.token) : null,
      });
      if (Platform.OS === 'web') {
        await Print.printAsync({ html });
        return;
      }
      const { uri } = await Print.printToFileAsync({ html });
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(uri, { mimeType: 'application/pdf', UTI: 'com.adobe.pdf', dialogTitle: tr('Missing poster') });
      } else {
        await Print.printAsync({ uri });
      }
    });

  const turnOn = async () => {
    if (!(await ask(tr('Is {name} lost?', { name: cat.name }), tr('Lost mode makes the collar report as often as possible and alerts everyone who sees {name}. It uses more battery.', { name: cat.name }), tr('Turn on lost mode')))) return;
    await run('on', () => backend.setLostMode(cat.id, true));
  };

  const markFound = async () => {
    await run('found', async () => {
      await backend.setLostMode(cat.id, false);
      await backend.revokeShareLinks(cat.id).catch(() => undefined);
      setLink(null);
      setFound(true);
    });
  };

  if (found) {
    return (
      <View style={[styles.done, { backgroundColor: t.bg }]}>
        <View style={[styles.doneIcon, { backgroundColor: t.liveSoft }]}>
          <Ionicons name="heart" size={56} color={t.live} />
        </View>
        <Text style={[styles.title, { color: t.text, textAlign: 'center' }]}>{tr('Welcome home, {name}!', { name: cat.name })}</Text>
        <Text style={{ color: t.textMuted, textAlign: 'center', lineHeight: 22, maxWidth: 340 }}>
          {tr('Lost mode is off and the live link no longer works. Everyone who sees {name} gets the good news.', { name: cat.name })}
        </Text>
        <Button title={tr('Back to {name}', { name: cat.name })} onPress={() => router.replace({ pathname: '/cat/[id]', params: { id: cat.id } })} />
      </View>
    );
  }

  return (
    <ScrollView style={{ backgroundColor: t.bg }} contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
      <View style={styles.hero}>
        <CatAvatar name={cat.name} color={cat.color} size={64} photoUrl={photoUrl} ring={cat.lostMode ? t.danger : undefined} />
        <View style={{ flex: 1 }}>
          <Text style={[styles.title, { color: cat.lostMode ? t.danger : t.text }]}>
            {cat.lostMode ? tr('Searching for {name}', { name: cat.name }) : tr('Is {name} lost?', { name: cat.name })}
          </Text>
          <Text style={{ color: t.textMuted }}>
            {cat.lostMode && cat.lostModeSince ? tr('Since {when}', { when: relativeTime(cat.lostModeSince) }) : tr('Last seen {when}', { when: relativeTime(cat.lastFixAt) })}
          </Text>
        </View>
      </View>

      {!cat.lostMode && (
        <Card style={{ gap: space.md }}>
          <Text style={{ color: t.text, lineHeight: 22 }}>
            {tr('Lost mode makes the collar report as often as possible, alerts everyone who sees {name}, and gives you a live link and a poster.', { name: cat.name })}
          </Text>
          <Button title={tr('Turn on lost mode')} icon="alert-circle" busy={busy === 'on'} onPress={() => void turnOn()} style={{ backgroundColor: t.danger }} textColor="#fff" />
        </Card>
      )}

      {cat.lastLat !== null && cat.lastLng !== null && (
        <View style={[styles.map, { height: Math.round(height * 0.28) }]}>
          <CatMap cats={[cat]} focusId={cat.id} style={StyleSheet.absoluteFill} />
        </View>
      )}
      <Text style={{ color: t.textMuted }}>{tr('Last seen')}: {lastSeen}</Text>

      <View style={styles.row}>
        <Button title={tr('Find with compass')} icon="compass-outline" style={{ flex: 1 }} onPress={() => router.push({ pathname: '/find/[id]', params: { id: cat.id } })} />
        {cat.lastLat !== null && cat.lastLng !== null && (
          <Button
            title={tr('Directions')}
            icon="walk-outline"
            variant="secondary"
            style={{ flex: 1 }}
            onPress={() => void Linking.openURL(directionsUrl(cat.lastLat!, cat.lastLng!)).catch(() => undefined)}
          />
        )}
      </View>

      <Card style={{ gap: space.md }}>
        <SectionTitle>{tr('Ask neighbours to help')}</SectionTitle>
        <Text style={{ color: t.textMuted, lineHeight: 20 }}>
          {tr('A live link shows where {name} is right now, without an account. It stops after 3 days or when you mark {name} found.', { name: cat.name })}
        </Text>
        {link && <Text style={{ color: t.text, fontSize: 13 }}>{tr('Link active until {when}', { when: `${shortDate(link.expiresAt)} ${clock(link.expiresAt)}` })}</Text>}
        <Button title={link ? tr('Share the live link again') : tr('Share a live link')} icon="share-social-outline" busy={busy === 'share'} onPress={() => void shareLive()} />
        {link && (
          <Button
            title={tr('Stop sharing')}
            variant="ghost"
            busy={busy === 'stop'}
            onPress={() => void run('stop', async () => { await backend.revokeShareLinks(cat.id); setLink(null); })}
          />
        )}
      </Card>

      <Card style={{ gap: space.md }}>
        <SectionTitle>{tr('Missing poster')}</SectionTitle>
        <Text style={{ color: t.textMuted, lineHeight: 20 }}>
          {tr("A printable A4 poster with {name}'s photo, where {name} was last seen, your phone number and a QR code to the live location.", { name: cat.name })}
        </Text>
        <TextInput
          style={[styles.input, { backgroundColor: t.surfaceAlt, color: t.text, borderColor: t.border }]}
          placeholder={tr('Your phone number')}
          placeholderTextColor={t.textMuted}
          keyboardType="phone-pad"
          value={phone}
          onChangeText={setPhone}
          accessibilityLabel={tr('Your phone number')}
        />
        <Button title={tr('Make the poster')} icon="document-outline" variant="secondary" busy={busy === 'poster'} onPress={() => void poster()} />
      </Card>

      <Card style={{ gap: space.sm }}>
        <SectionTitle>{tr('Where to search')}</SectionTitle>
        {CHECKLIST.map((line) => (
          <View key={line} style={styles.check}>
            <Ionicons name="checkmark-circle-outline" size={18} color={t.live} />
            <Text style={{ color: t.text, flex: 1, lineHeight: 20 }}>{tr(line)}</Text>
          </View>
        ))}
      </Card>

      <ErrorText>{error}</ErrorText>
      {cat.lostMode && <Button title={tr('{name} is found!', { name: cat.name })} icon="heart" busy={busy === 'found'} onPress={() => void markFound()} />}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: space.lg, gap: space.lg, paddingBottom: space.xl * 2, maxWidth: 640, width: '100%', alignSelf: 'center' },
  hero: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  title: { fontFamily: fonts.display, fontSize: 26, letterSpacing: -0.5 },
  map: { borderRadius: radius.lg, overflow: 'hidden' },
  row: { flexDirection: 'row', gap: space.sm },
  input: { borderWidth: 1, borderRadius: radius.md, paddingHorizontal: space.md, paddingVertical: 12, fontSize: 16, fontFamily: fonts.body },
  check: { flexDirection: 'row', gap: space.sm, alignItems: 'flex-start' },
  done: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.lg, padding: space.xl },
  doneIcon: { width: 120, height: 120, borderRadius: 60, alignItems: 'center', justifyContent: 'center' },
});
