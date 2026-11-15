/**
 * Alerts tab: one inbox for every cat (left/back home, battery, silent
 * collar, lost, found). Opening it marks everything read; "Load more" pages
 * back in time.
 */
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';

import { alertView, type AlertTone } from '../../src/alerts';
import { useApp } from '../../src/AppProvider';
import type { AlertItem } from '../../src/backend/types';
import { Button, CatAvatar, EmptyState, ErrorText } from '../../src/components/ui';
import { usePhotoUrl } from '../../src/components/usePhotoUrl';
import { messageOf } from '../../src/dialogs';
import { relativeTime } from '../../src/geo';
import { locale, t as tr } from '../../src/i18n';
import { clock } from '../../src/time';
import { fonts, radius, space, useTheme, type Theme } from '../../src/theme';

const PAGE = 40;

const toneColor = (t: Theme, tone: AlertTone) =>
  ({ danger: t.danger, live: t.live, warn: t.warn, accent: t.accent, neutral: t.textMuted })[tone];

/** "Today", "Yesterday" or the date, for section headers. */
function dayHeader(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const y = new Date();
  y.setDate(y.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return tr('Today');
  if (d.toDateString() === y.toDateString()) return tr('Yesterday');
  return d.toLocaleDateString(locale(), { weekday: 'long', day: 'numeric', month: 'long' });
}

export default function AlertsTab() {
  const t = useTheme();
  const router = useRouter();
  const { backend, cats, refreshUnread } = useApp();
  const [items, setItems] = useState<AlertItem[] | null>(null);
  const [more, setMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!backend) return;
    setLoading(true);
    try {
      const list = await backend.listAlerts(PAGE);
      setItems(list);
      setMore(list.length === PAGE);
      setError(null);
      await backend.markAlertsRead();
      await refreshUnread();
    } catch (e) {
      setError(messageOf(e));
      setItems((cur) => cur ?? []);
    } finally {
      setLoading(false);
    }
  }, [backend, refreshUnread]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  const loadMore = async () => {
    if (!backend || !items?.length || loading) return;
    setLoading(true);
    try {
      const next = await backend.listAlerts(PAGE, items[items.length - 1]!.at);
      setItems([...items, ...next]);
      setMore(next.length === PAGE);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setLoading(false);
    }
  };

  if (items === null) {
    return (
      <View style={[styles.center, { backgroundColor: t.bg }]}>
        <ActivityIndicator color={t.accent} />
      </View>
    );
  }

  return (
    <FlatList
      style={{ backgroundColor: t.bg }}
      contentContainerStyle={styles.list}
      data={items}
      keyExtractor={(a) => a.id}
      refreshControl={<RefreshControl refreshing={loading && items.length > 0} onRefresh={() => void load()} tintColor={t.accent} />}
      ListHeaderComponent={
        <View style={{ gap: space.sm }}>
          <ErrorText>{error}</ErrorText>
          <Pressable accessibilityRole="button" onPress={() => router.push('/alert-settings')} style={styles.settingsLink}>
            <Ionicons name="options-outline" size={16} color={t.accent} />
            <Text style={{ color: t.accent, fontFamily: fonts.bodySemibold }}>{tr('Choose which alerts you get')}</Text>
          </Pressable>
        </View>
      }
      ListEmptyComponent={
        <EmptyState icon="notifications-outline" title={tr('No alerts yet')} body={tr("You'll see here when a cat leaves or comes home, a collar needs charging, or a cat is lost or found.")} />
      }
      renderItem={({ item, index }) => {
        const header = index === 0 || dayHeader(items[index - 1]!.at) !== dayHeader(item.at);
        const cat = cats.find((c) => c.id === item.catId);
        return (
          <View>
            {header && <Text style={[styles.day, { color: t.textMuted }]}>{dayHeader(item.at)}</Text>}
            <AlertRow
              item={item}
              catName={cat?.name ?? tr('Your cat')}
              color={cat?.color ?? t.textMuted}
              photoPath={cat?.photoPath ?? null}
              onPress={cat ? () => router.push({ pathname: item.kind === 'lost_mode' ? '/lost/[id]' : '/cat/[id]', params: { id: cat.id } }) : undefined}
            />
          </View>
        );
      }}
      ListFooterComponent={
        items.length > 0 && more ? <Button title={tr('Load older alerts')} variant="ghost" busy={loading} onPress={() => void loadMore()} /> : undefined
      }
    />
  );
}

function AlertRow({ item, catName, color, photoPath, onPress }: { item: AlertItem; catName: string; color: string; photoPath: string | null; onPress?: () => void }) {
  const t = useTheme();
  const v = alertView(item, catName);
  const photoUrl = usePhotoUrl(photoPath);
  const c = toneColor(t, v.tone);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${v.title}. ${relativeTime(item.at)}`}
      disabled={!onPress}
      onPress={onPress}
      style={({ pressed }) => [styles.row, { backgroundColor: item.unread ? t.accentSoft : t.surface, opacity: pressed ? 0.85 : 1 }]}
    >
      <View>
        <CatAvatar name={catName} color={color} size={40} photoUrl={photoUrl} />
        <View style={[styles.kindIcon, { backgroundColor: c }]}>
          <Ionicons name={v.icon} size={12} color="#fff" />
        </View>
      </View>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={{ color: t.text, fontFamily: fonts.bodySemibold, fontSize: 15 }}>{v.title}</Text>
        <Text style={{ color: t.textMuted, fontSize: 13, lineHeight: 18 }}>{v.body}</Text>
      </View>
      <View style={{ alignItems: 'flex-end', gap: 4 }}>
        <Text style={{ color: t.textMuted, fontSize: 12, fontFamily: fonts.mono }}>{clock(item.at)}</Text>
        {item.unread && <View style={[styles.unreadDot, { backgroundColor: t.accent }]} />}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  list: { padding: space.lg, gap: space.sm, paddingBottom: space.xl * 2, maxWidth: 640, width: '100%', alignSelf: 'center' },
  settingsLink: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-end', paddingVertical: 4 },
  day: { fontSize: 13, fontFamily: fonts.bodySemibold, letterSpacing: 0.6, textTransform: 'uppercase', marginTop: space.md, marginBottom: space.sm },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, padding: space.md, borderRadius: radius.md },
  kindIcon: { position: 'absolute', right: -4, bottom: -2, width: 20, height: 20, borderRadius: 10, alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: '#fff' },
  unreadDot: { width: 8, height: 8, borderRadius: 4 },
});
