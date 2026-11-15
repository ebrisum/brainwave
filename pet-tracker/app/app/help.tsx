/**
 * Help & support: getting started with the collar, battery tips, answers to
 * common questions, warranty, and how to reach us.
 */
import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Button, Card, SectionTitle } from '../src/components/ui';
import { t as tr, tk } from '../src/i18n';
import { SUPPORT_EMAIL } from '../src/links';
import { fonts, space, useTheme } from '../src/theme';

const COLLAR_STEPS = [
  [tk('Charge it fully'), tk('Put the collar on the magnetic charger until the light stays green (about 2 hours).')],
  [tk('Add it in the app'), tk('Cats → Add a cat → GPS collar, and scan the QR code on the label or box.')],
  [tk('Test it outside'), tk('Take the collar outside for 5 minutes so it finds GPS and checks in. The cat appears on the map.')],
  [tk('Set home'), tk('Places → Add your home. At home the collar saves battery, and you get "left home" alerts.')],
  [tk('Fit the collar'), tk('Use a breakaway collar with two fingers of room. Let your cat wear it indoors first, with you around.')],
] as const;

const BATTERY_TIPS = [
  tk('A home zone saves the most: the collar barely uses GPS while your cat is at home.'),
  tk('Battery saver (Collar → Power mode) reports every 30 minutes instead of 15.'),
  tk('Lost mode and Live use far more battery: switch them off when you no longer need them.'),
  tk('Charge when the app says 20%. The collar warns you, and so does the Alerts tab.'),
] as const;

const FAQ = [
  [tk('Is there really no subscription?'), tk('Yes. The SIM in the collar is paid for 10 years, included in the price. The app is free.')],
  [tk('How accurate is the position?'), tk('Outdoors usually 5-15 m. Indoors and under roofs it is less precise; the circle on the map shows how sure the collar is.')],
  [tk('Why does my cat show "Resting"?'), tk("The collar's motion sensor says your cat hasn't moved, so it skips GPS to save battery. As soon as your cat moves, positions come in again.")],
  [tk('My collar is "silent". What now?'), tk('It has not checked in for hours: the battery may be empty, or it is somewhere without mobile network. Charge it, or go outside with it.')],
  [tk('Who can see my cat?'), tk('Only you, the people in its household and cat sitters you invite. A live link for a lost cat works only until it expires or you stop it.')],
  [tk('Can I move my cat to a new collar?'), tk('Yes: Collar → New collar for this cat. The profile, zones and history move along.')],
] as const;

export default function Help() {
  const t = useTheme();
  const [open, setOpen] = useState<number | null>(null);
  const mail = (subject: string) =>
    void Linking.openURL(`mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(subject)}`).catch(() => undefined);

  return (
    <ScrollView style={{ backgroundColor: t.bg }} contentContainerStyle={styles.scroll}>
      <Card style={{ gap: space.md }}>
        <SectionTitle>{tr('Getting started with the collar')}</SectionTitle>
        {COLLAR_STEPS.map(([title, body], i) => (
          <View key={title} style={styles.step}>
            <View style={[styles.num, { backgroundColor: t.primary }]}>
              <Text style={{ color: t.primaryText, fontFamily: fonts.bodySemibold }}>{i + 1}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: t.text, fontFamily: fonts.bodySemibold }}>{tr(title)}</Text>
              <Text style={{ color: t.textMuted, lineHeight: 20 }}>{tr(body)}</Text>
            </View>
          </View>
        ))}
      </Card>

      <Card style={{ gap: space.sm }}>
        <SectionTitle>{tr('Battery tips')}</SectionTitle>
        {BATTERY_TIPS.map((tip) => (
          <View key={tip} style={styles.tip}>
            <Ionicons name="battery-charging-outline" size={18} color={t.live} />
            <Text style={{ color: t.text, flex: 1, lineHeight: 20 }}>{tr(tip)}</Text>
          </View>
        ))}
      </Card>

      <Card style={{ gap: 0 }}>
        <SectionTitle>{tr('Questions')}</SectionTitle>
        {FAQ.map(([q, a], i) => (
          <View key={q} style={[styles.faq, { borderBottomColor: t.border }, i === FAQ.length - 1 && { borderBottomWidth: 0 }]}>
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ expanded: open === i }}
              onPress={() => setOpen(open === i ? null : i)}
              style={styles.faqQ}
            >
              <Text style={{ color: t.text, fontFamily: fonts.bodySemibold, flex: 1 }}>{tr(q)}</Text>
              <Ionicons name={open === i ? 'chevron-up' : 'chevron-down'} size={18} color={t.textMuted} />
            </Pressable>
            {open === i && <Text style={{ color: t.textMuted, lineHeight: 20, paddingBottom: space.md }}>{tr(a)}</Text>}
          </View>
        ))}
      </Card>

      <Card style={{ gap: space.md }}>
        <SectionTitle>{tr('Warranty and returns')}</SectionTitle>
        <Text style={{ color: t.textMuted, lineHeight: 20 }}>
          {tr('Your collar has a 2-year warranty. Within 14 days of delivery you can return it without giving a reason. Mail us your order number and what went wrong; we send a replacement or a return label.')}
        </Text>
        <Button title={tr('Report a problem with my collar')} icon="construct-outline" variant="secondary" onPress={() => mail(tr('Collar problem'))} />
      </Card>

      <Card style={{ gap: space.md }}>
        <SectionTitle>{tr('Contact')}</SectionTitle>
        <Text style={{ color: t.textMuted, lineHeight: 20 }}>{tr('We usually answer within one working day.')}</Text>
        <Button title={tr('Mail support')} icon="mail-outline" onPress={() => mail(tr('Question about Cat Tracker'))} />
        <Text selectable style={{ color: t.textMuted, textAlign: 'center' }}>{SUPPORT_EMAIL}</Text>
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: space.lg, gap: space.lg, paddingBottom: space.xl * 2, maxWidth: 640, width: '100%', alignSelf: 'center' },
  step: { flexDirection: 'row', gap: space.md, alignItems: 'flex-start' },
  num: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  tip: { flexDirection: 'row', gap: space.sm, alignItems: 'flex-start' },
  faq: { borderBottomWidth: StyleSheet.hairlineWidth },
  faqQ: { flexDirection: 'row', alignItems: 'center', gap: space.sm, paddingVertical: space.md },
});
