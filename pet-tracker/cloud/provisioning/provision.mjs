#!/usr/bin/env node
/**
 * Registers ready-made trackers in Supabase and writes claim-code labels.
 *
 *   SUPABASE_URL=https://xxx.supabase.co SUPABASE_SERVICE_ROLE_KEY=... \
 *     node provision.mjs trackers.csv out/
 *
 * trackers.csv: one tracker per line, "imei[,model[,iccid]]", e.g.
 *   861234567890123,MT710,8988228066602340000
 *
 * Writes out/labels.csv (id, claim code, link), out/labels.html (a sheet of
 * QR labels to print) and out/qr/<id>.png (one QR code per tracker, for a
 * label printer). Claim codes are only shown once: keep labels.csv safe.
 * Put the label inside the box: whoever has the code can link the tracker.
 * The service role key stays on your computer; never put it in the app.
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { claimLink, labelPng, labelSheet, parseTrackerCsv } from './labels.mjs';
import { rpcClient } from './supabase.mjs';

const [csvPath, outDir = 'out'] = process.argv.slice(2);
if (!csvPath) {
  console.error('Usage: SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... node provision.mjs trackers.csv [outDir]');
  process.exit(1);
}
const rpc = rpcClient();

const trackers = parseTrackerCsv(readFileSync(csvPath, 'utf8'));
const done = [];
for (const t of trackers) {
  try {
    done.push({ ...t, claimCode: await rpc('provision_tracker', { p_device_uid: t.deviceUid, p_model: t.model, p_iccid: t.iccid }) });
    console.log(`✓ ${t.deviceUid}`);
  } catch (e) {
    console.error(`✗ ${t.deviceUid}: ${e.message}`);
  }
}

mkdirSync(join(outDir, 'qr'), { recursive: true });
for (const d of done) writeFileSync(join(outDir, 'qr', `${d.deviceUid}.png`), await labelPng(d.deviceUid, d.claimCode));
writeFileSync(
  join(outDir, 'labels.csv'),
  ['device,claim_code,link', ...done.map((d) => `${d.deviceUid},${d.claimCode},${claimLink(d.deviceUid, d.claimCode)}`)].join('\n') + '\n',
  { mode: 0o600 },
);
writeFileSync(join(outDir, 'labels.html'), await labelSheet(done));
console.log(`${done.length}/${trackers.length} registered. Labels: ${join(outDir, 'labels.html')}`);
