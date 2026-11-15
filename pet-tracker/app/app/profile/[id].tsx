/**
 * Cat profile: date of birth, breed, weight, microchip, vet, indoor/outdoor
 * and notes. Sitters and the household see it too (vet phone for emergencies);
 * the weight drives the "collar too heavy" warning.
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { Linking, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { useApp } from '../../src/AppProvider';
import { isOwner, type CatProfile, type Lifestyle } from '../../src/backend/types';
import { Button, Card, ErrorText, SectionTitle, Segmented } from '../../src/components/ui';
import { messageOf } from '../../src/dialogs';
import { t as tr } from '../../src/i18n';
import { COLLAR_GRAMS, collarShare } from '../../src/insights';
import { fonts, radius, space, useTheme } from '../../src/theme';

const ageText = (birth: string | null) => {
  if (!birth) return null;
  const months = Math.floor((Date.now() - Date.parse(birth)) / (30.44 * 86400_000));
  return months < 24 ? tr('{n} months old', { n: months }) : tr('{n} years old', { n: Math.floor(months / 12) });
};

export default function ProfileScreen() {
  const t = useTheme();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { backend, cats, refresh } = useApp();
  const cat = cats.find((c) => c.id === id);
  const [p, setP] = useState<CatProfile | null>(cat ? { ...cat.profile } : null);
  const [weight, setWeight] = useState(cat?.profile.weightKg != null ? String(cat.profile.weightKg).replace('.', ',') : '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!backend || !cat || !p) return null;
  const owner = isOwner(cat, backend);
  const input = [styles.input, { backgroundColor: t.surfaceAlt, color: t.text, borderColor: t.border }];
  const weightKg = weight.trim() ? Number(weight.replace(',', '.')) : null;
  const share = collarShare(COLLAR_GRAMS, weightKg && !Number.isNaN(weightKg) ? weightKg : null);
  const birthOk = !p.birthDate || /^\d{4}-\d{2}-\d{2}$/.test(p.birthDate);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      if (weightKg !== null && (Number.isNaN(weightKg) || weightKg < 0.5 || weightKg > 15)) throw new Error(tr('Weight must be between 0.5 and 15 kg.'));
      if (!birthOk) throw new Error(tr('Write the date of birth as YYYY-MM-DD.'));
      await backend.updateProfile(cat.id, { ...p, weightKg });
      await refresh();
      router.back();
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  };

  const field = (key: keyof CatProfile, label: string, opts: { placeholder?: string; keyboard?: 'default' | 'phone-pad' | 'number-pad'; multiline?: boolean; max?: number } = {}) => (
    <View style={{ gap: 4 }}>
      <Text style={[styles.label, { color: t.textMuted }]}>{label}</Text>
      <TextInput
        style={[...input, opts.multiline && { minHeight: 88, textAlignVertical: 'top' }]}
        value={(p[key] as string | null) ?? ''}
        onChangeText={(v) => setP({ ...p, [key]: v })}
        placeholder={opts.placeholder}
        placeholderTextColor={t.textMuted}
        keyboardType={opts.keyboard ?? 'default'}
        multiline={opts.multiline}
        maxLength={opts.max ?? 80}
        editable={owner}
        accessibilityLabel={label}
      />
    </View>
  );

  return (
    <ScrollView style={{ backgroundColor: t.bg }} contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
      <Card style={{ gap: space.md }}>
        <SectionTitle>{tr('About {name}', { name: cat.name })}</SectionTitle>
        {field('birthDate', tr('Date of birth'), { placeholder: 'YYYY-MM-DD', max: 10 })}
        {ageText(birthOk ? p.birthDate : null) && <Text style={{ color: t.textMuted, fontSize: 13 }}>{ageText(p.birthDate)}</Text>}
        {field('breed', tr('Breed or looks'), { placeholder: tr('e.g. black-and-white European shorthair'), max: 60 })}
        <View style={{ gap: 4 }}>
          <Text style={[styles.label, { color: t.textMuted }]}>{tr('Weight (kg)')}</Text>
          <TextInput style={input} value={weight} onChangeText={setWeight} placeholder="4,2" placeholderTextColor={t.textMuted} keyboardType="decimal-pad" editable={owner} accessibilityLabel={tr('Weight (kg)')} maxLength={5} />
          {share !== null && (
            <Text style={{ color: share > 0.04 ? t.warn : t.live, fontSize: 13, lineHeight: 18 }}>
              {share > 0.04
                ? tr('The collar ({g} g) is {pct}% of {name}\'s weight. Vets advise under 4%: watch how {name} copes.', { g: COLLAR_GRAMS, pct: (share * 100).toFixed(1), name: cat.name })
                : tr('The collar ({g} g) is {pct}% of {name}\'s weight: fine.', { g: COLLAR_GRAMS, pct: (share * 100).toFixed(1), name: cat.name })}
            </Text>
          )}
        </View>
        <View style={{ gap: 4 }}>
          <Text style={[styles.label, { color: t.textMuted }]}>{tr('Indoor or outdoor')}</Text>
          <Segmented<Lifestyle>
            options={[
              { value: 'indoor', label: tr('Indoor') },
              { value: 'both', label: tr('Both') },
              { value: 'outdoor', label: tr('Outdoor') },
            ]}
            value={p.lifestyle ?? 'both'}
            onChange={(v) => owner && setP({ ...p, lifestyle: v })}
          />
        </View>
        {field('microchip', tr('Microchip number'), { placeholder: '528…', keyboard: 'number-pad', max: 20 })}
      </Card>

      <Card style={{ gap: space.md }}>
        <SectionTitle>{tr('Vet')}</SectionTitle>
        {field('vetName', tr('Vet practice'), { max: 80 })}
        {field('vetPhone', tr('Vet phone number'), { keyboard: 'phone-pad', max: 24 })}
        {p.vetPhone ? (
          <Button title={tr('Call the vet')} icon="call-outline" variant="secondary" onPress={() => void Linking.openURL(`tel:${p.vetPhone!.replace(/[^0-9+]/g, '')}`).catch(() => undefined)} />
        ) : null}
      </Card>

      <Card style={{ gap: space.md }}>
        <SectionTitle>{tr('Notes for sitters')}</SectionTitle>
        {field('notes', tr('Food, medicine, habits'), { multiline: true, max: 500, placeholder: tr('e.g. 2 scoops of dry food, likes to sleep in the shed') })}
      </Card>

      <ErrorText>{error}</ErrorText>
      {owner ? <Button title={tr('Save')} busy={busy} onPress={() => void save()} /> : <Text style={{ color: t.textMuted, textAlign: 'center' }}>{tr('Only the owner can change the profile.')}</Text>}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: space.lg, gap: space.lg, paddingBottom: space.xl * 2, maxWidth: 640, width: '100%', alignSelf: 'center' },
  label: { fontFamily: fonts.bodySemibold, fontSize: 13 },
  input: { borderWidth: 1, borderRadius: radius.md, paddingHorizontal: space.md, paddingVertical: 12, fontSize: 16, fontFamily: fonts.body },
});
