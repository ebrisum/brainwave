/**
 * Web map: react-native-maps has no web implementation, so the browser build
 * uses MapLibre GL with OpenFreeMap vector tiles (OpenStreetMap data; free,
 * no key, commercial use allowed) and draws the phone map's layers on top:
 * zones, heatmap glow, dotted route, accuracy halos and cats.
 *
 * Other tiles: EXPO_PUBLIC_MAP_STYLE / EXPO_PUBLIC_MAP_STYLE_DARK (a MapLibre
 * style URL, e.g. from MapTiler).
 */
// @ts-expect-error CSS side-effect import (Metro bundles it for the web)
import 'maplibre-gl/dist/maplibre-gl.css';

import maplibregl from 'maplibre-gl';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { Cat } from '../backend/types';
import { distanceM, resamplePath, smoothTrack } from '../geo';
import { t as tr } from '../i18n';
import { useTheme } from '../theme';
import type { CatMapProps } from './CatMap.types';
import { heatBlobs } from './heat';
import { CatAvatar } from './ui';
import { catBadge, usePhotoUrl } from './usePhotoUrl';

const STYLE_LIGHT = process.env.EXPO_PUBLIC_MAP_STYLE ?? 'https://tiles.openfreemap.org/styles/positron';
const STYLE_DARK = process.env.EXPO_PUBLIC_MAP_STYLE_DARK ?? (process.env.EXPO_PUBLIC_MAP_STYLE ? STYLE_LIGHT : 'https://tiles.openfreemap.org/styles/dark');

/** Never zoom closer than this: a cat with its garden and the street around it. */
const MAX_ZOOM = 17.6;
/** Before anything is known: the Netherlands. */
const FALLBACK = { center: [5.3, 52.2] as [number, number], zoom: 6.5 };

const pxPerM = (lat: number, zoom: number) => (512 * 2 ** zoom) / (40_075_016.686 * Math.cos((lat * Math.PI) / 180));

function MapCat({ cat, x, y, onPress }: { cat: Cat; x: number; y: number; onPress?: () => void }) {
  const t = useTheme();
  const photoUrl = usePhotoUrl(cat.photoPath);
  return (
    <Pressable accessibilityLabel={cat.name} onPress={onPress} style={{ position: 'absolute', left: x - 18, top: y - 28 }}>
      <CatAvatar name={cat.name} color={cat.color} size={36} ring={cat.lostMode ? t.danger : '#fff'} photoUrl={photoUrl} badge={catBadge(cat, t)} />
    </Pressable>
  );
}

export function CatMap({
  cats, focusId, track, trackColor, cursor, zones, heat, onSelectCat, onLongPress, onPressMap, draftZone, coverBottom = 0, refitKey = 0, style,
}: CatMapProps) {
  const t = useTheme();
  const host = useRef<unknown>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [, setFrame] = useState(0); // re-render the overlay when the map moves
  const handlers = useRef({ onPressMap, onLongPress });
  handlers.current = { onPressMap, onLongPress };

  const placed = cats.filter((c) => c.lastLat !== null && c.lastLng !== null);
  const focus = focusId ? placed.find((c) => c.id === focusId) : undefined;
  const smooth = useMemo(() => (track && track.length > 1 ? smoothTrack(track) : []), [track]);
  const blobs = useMemo(() => heatBlobs(heat ?? []), [heat]);

  // Create the map once; the style follows the theme.
  useEffect(() => {
    const parent = host.current as unknown as HTMLElement | null;
    if (!parent) return;
    // Our own div: MapLibre's CSS sets position: relative on its container,
    // which would collapse an absolutely positioned React Native view.
    const el = document.createElement('div');
    el.style.cssText = 'position:absolute;top:0;left:0;right:0;bottom:0;';
    parent.appendChild(el);
    const m = new maplibregl.Map({
      container: el,
      style: t.isDark ? STYLE_DARK : STYLE_LIGHT,
      center: FALLBACK.center,
      zoom: FALLBACK.zoom,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      maxZoom: 19,
    });
    m.touchZoomRotate.disableRotation();
    // Top left: the bottom of the map is often under a sheet.
    m.addControl(new maplibregl.AttributionControl({ compact: true }), 'top-left');
    const redraw = () => setFrame((f) => f + 1);
    m.on('move', redraw);
    m.on('resize', redraw);
    m.on('load', () => {
      // Compact attribution starts opened; keep it as the small (i) until tapped.
      el.querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show');
      setReady(true);
      redraw();
    });
    m.on('click', () => handlers.current.onPressMap?.());
    m.on('contextmenu', (e) => handlers.current.onLongPress?.(e.lngLat.lat, e.lngLat.lng));
    map.current = m;
    return () => {
      m.remove();
      el.remove();
      map.current = null;
      setReady(false);
    };
  }, [t.isDark]);

  // Frame: everything drawn, or one cat up close with the zones around it.
  const fit = useMemo(() => {
    const data = [...smooth, ...(heat ?? []).slice(0, 60)];
    const pts: { lat: number; lng: number; r?: number }[] = [
      ...(focus ? [focus] : placed).map((c) => ({ lat: c.lastLat!, lng: c.lastLng! })),
      ...data,
    ];
    const framed = focus && data.length === 0
      ? (zones ?? []).filter((z) => distanceM(z.lat, z.lng, focus.lastLat!, focus.lastLng!) < 400)
      : zones ?? [];
    for (const z of [...framed, ...(draftZone ? [draftZone] : [])]) pts.push({ lat: z.lat, lng: z.lng, r: z.radiusM });
    if (pts.length === 0) return null;
    let s = 90, w = 180, n = -90, e = -180;
    for (const p of pts) {
      const dLat = (p.r ?? 0) / 111_320;
      const dLng = dLat / Math.cos((p.lat * Math.PI) / 180);
      s = Math.min(s, p.lat - dLat);
      n = Math.max(n, p.lat + dLat);
      w = Math.min(w, p.lng - dLng);
      e = Math.max(e, p.lng + dLng);
    }
    return [[w, s], [e, n]] as [[number, number], [number, number]];
  }, [focus, placed, smooth, heat, zones, draftZone]);

  const fitKey = [ready, focusId ?? '', placed.map((c) => c.id).join(','), track?.length ?? 0, zones?.length ?? 0,
    heat?.length ?? 0, draftZone ? `${draftZone.lat},${draftZone.lng},${draftZone.radiusM}` : '', coverBottom, refitKey].join('|');

  useEffect(() => {
    const m = map.current;
    if (!m || !ready || !fit) return;
    const h = (host.current as unknown as HTMLElement | null)?.clientHeight ?? 400;
    const bottom = Math.min(h * 0.7, coverBottom) + 48;
    m.fitBounds(fit, { padding: { top: 88, left: 56, right: 72, bottom }, maxZoom: MAX_ZOOM, duration: 0 });
    // fitKey captures everything that should trigger a re-frame
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey]);

  const m = map.current;
  const zoom = m && ready ? m.getZoom() : 0;
  const project = (lat: number, lng: number) => m!.project([lng, lat]);
  const routeColor = trackColor ?? focus?.color ?? t.accent;
  const circle = (key: string, lat: number, lng: number, radiusM: number, extra: object) => {
    const c = project(lat, lng);
    const r = radiusM * pxPerM(lat, zoom);
    return <View key={key} pointerEvents="none" style={[{ position: 'absolute', left: c.x - r, top: c.y - r, width: r * 2, height: r * 2, borderRadius: r }, extra]} />;
  };

  return (
    <View style={[styles.wrap, { backgroundColor: t.surfaceAlt }, style]}>
      <View ref={host as never} style={StyleSheet.absoluteFill} />
      {m && ready && (
        <View style={StyleSheet.absoluteFill} pointerEvents="box-none">
          {blobs.length > 0 && (
            <View pointerEvents="none" style={[StyleSheet.absoluteFill, { filter: 'blur(8px)' } as object]}>
              {blobs.map((b) => circle(`h${b.key}`, b.lat, b.lng, b.radiusM, { backgroundColor: b.fill }))}
            </View>
          )}

          {(zones ?? []).map((z) => {
            const c = project(z.lat, z.lng);
            const r = z.radiusM * pxPerM(z.lat, zoom);
            return (
              <View key={z.id} pointerEvents="none" style={StyleSheet.absoluteFill}>
                {circle(`z${z.id}`, z.lat, z.lng, z.radiusM, {
                  borderWidth: 2, borderColor: t.live, borderStyle: z.allCats ? 'dashed' : 'solid', backgroundColor: 'rgba(6,116,72,0.10)',
                })}
                <Text style={[styles.zoneLabel, { left: c.x - 40, top: c.y - r - 10, color: t.live, backgroundColor: t.surface, borderColor: t.live }]}>
                  {z.name}
                </Text>
              </View>
            );
          })}
          {draftZone &&
            circle('draft', draftZone.lat, draftZone.lng, draftZone.radiusM, {
              borderWidth: 2, borderStyle: 'dashed', borderColor: t.accent, backgroundColor: 'rgba(36,73,232,0.12)',
            })}

          {/* Route: hollow dots 15 px apart, fading in from the oldest */}
          {(() => {
            const lat = smooth[0]?.lat ?? 0;
            const dots = smooth.length > 1 ? resamplePath(smooth, 15 / pxPerM(lat, zoom)) : [];
            return dots.length > 1
              ? dots.map((p, i) => {
                  const c = project(p.lat, p.lng);
                  return (
                    <View
                      key={`dot${i}`}
                      pointerEvents="none"
                      style={{
                        position: 'absolute', left: c.x - 5, top: c.y - 5, width: 10, height: 10, borderRadius: 5, backgroundColor: '#fff',
                        borderWidth: 2.5, borderColor: routeColor, opacity: 0.4 + (0.6 * i) / (dots.length - 1),
                      }}
                    />
                  );
                })
              : null;
          })()}

          {placed.map((cat) => {
            const c = project(cat.lastLat!, cat.lastLng!);
            const r = (cat.lastAccuracyM ?? 0) * pxPerM(cat.lastLat!, zoom);
            return (
              <View key={cat.id} style={StyleSheet.absoluteFill} pointerEvents="box-none">
                {r > 6 && circle(`acc${cat.id}`, cat.lastLat!, cat.lastLng!, cat.lastAccuracyM!, { backgroundColor: `${cat.color}26`, borderWidth: 1, borderColor: `${cat.color}55` })}
                <MapCat cat={cat} x={c.x} y={c.y} onPress={onSelectCat ? () => onSelectCat(cat.id) : undefined} />
              </View>
            );
          })}

          {cursor && (() => {
            const c = project(cursor.lat, cursor.lng);
            return <View pointerEvents="none" style={[styles.cursor, { left: c.x - 10, top: c.y - 10, borderColor: routeColor }]} />;
          })()}
        </View>
      )}
      {ready && !fit && (
        <View style={styles.empty} pointerEvents="none">
          <Text style={[styles.emptyText, { color: t.textMuted, backgroundColor: t.surface }]}>{tr('No positions yet')}</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { overflow: 'hidden' },
  cursor: { position: 'absolute', width: 20, height: 20, borderRadius: 10, borderWidth: 5, backgroundColor: '#fff' },
  zoneLabel: {
    position: 'absolute', width: 80, textAlign: 'center', fontSize: 11, fontWeight: '700',
    borderWidth: 1, borderRadius: 8, overflow: 'hidden', paddingVertical: 1,
  },
  empty: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, alignItems: 'center', justifyContent: 'center' },
  emptyText: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 12, overflow: 'hidden' },
});
