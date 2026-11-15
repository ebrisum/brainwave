/** Households & sharing: who sees your cats, invites (QR, link or code) and joining. */
import { ScrollView, StyleSheet } from 'react-native';

import { HouseholdsCard } from '../src/components/HouseholdsCard';
import { space, useTheme } from '../src/theme';

export default function HouseholdScreen() {
  const t = useTheme();
  return (
    <ScrollView style={{ backgroundColor: t.bg }} contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
      <HouseholdsCard />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: space.lg, gap: space.lg, paddingBottom: space.xl * 2, maxWidth: 640, width: '100%', alignSelf: 'center' },
});
