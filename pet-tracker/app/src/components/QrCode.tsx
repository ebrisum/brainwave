/**
 * QR code drawn with plain Views: no native module, so it works in Expo Go
 * and on the web. Dark modules in a row are merged into one View.
 */
// The core encoder only: the package's main entry pulls in Node/canvas renderers.
import QRCodeCore from 'qrcode/lib/core/qrcode';
import { useMemo } from 'react';
import { View } from 'react-native';

export function QrCode({ value, size = 220, color = '#000000', background = '#FFFFFF' }: {
  value: string;
  size?: number;
  color?: string;
  background?: string;
}) {
  const rows = useMemo(() => {
    const { modules } = QRCodeCore.create(value, { errorCorrectionLevel: 'M' });
    const n = modules.size;
    const runs: { x: number; w: number }[][] = [];
    for (let y = 0; y < n; y++) {
      const row: { x: number; w: number }[] = [];
      for (let x = 0; x < n; x++) {
        if (!modules.data[y * n + x]) continue;
        const last = row[row.length - 1];
        if (last && last.x + last.w === x) last.w++;
        else row.push({ x, w: 1 });
      }
      runs.push(row);
    }
    return { n, runs };
  }, [value]);

  const quiet = 4; // modules of white border scanners need
  const cell = size / (rows.n + quiet * 2);
  return (
    <View
      style={{ width: size, height: size, backgroundColor: background }}
      accessibilityRole="image"
      accessibilityLabel="QR code"
    >
      {rows.runs.map((row, y) =>
        row.map((r) => (
          <View
            key={`${y}-${r.x}`}
            style={{
              position: 'absolute', backgroundColor: color,
              left: (quiet + r.x) * cell, top: (quiet + y) * cell,
              width: r.w * cell + 0.5, height: cell + 0.5,
            }}
          />
        )),
      )}
    </View>
  );
}
