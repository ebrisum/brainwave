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
 * Writes out/labels.csv (id, claim code, link) and out/labels.html (QR
 * labels to print). Claim codes are only shown once: keep labels.csv safe.
 * The service role key stays on your computer; never put it in the app.
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { claimLink, labelSheet, parseTrackerCsv } from './labels.mjs';

const [csvPath, outDir = 'out'] = process.argv.slice(2);
const url = process.env.SUPABASE_URL?.replace(/\/+$/, '');
const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
if (!csvPath || !url || !key) {
  console.error('Usage: SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... node provision.mjs trackers.csv [outDir]');
  process.exit(1);
}

const trackers = parseTrackerCsv(readFileSync(csvPath, 'utf8'));
const done = [];
for (const t of trackers) {
  const res = await fetch(`${url}/rest/v1/rpc/provision_tracker`, {
    method: 'POST',
    headers: { apikey: key, authorization: `Bearer ${key}`, 'content-type': 'application/json' },
    body: JSON.stringify({ p_device_uid: t.deviceUid, p_model: t.model, p_iccid: t.iccid }),
  });
  if (!res.ok) {
    console.error(`✗ ${t.deviceUid}: ${res.status} ${await res.text()}`);
    continue;
  }
  done.push({ ...t, claimCode: await res.json() });
  console.log(`✓ ${t.deviceUid}`);
}

mkdirSync(outDir, { recursive: true });
writeFileSync(
  join(outDir, 'labels.csv'),
  ['device,claim_code,link', ...done.map((d) => `${d.deviceUid},${d.claimCode},${claimLink(d.deviceUid, d.claimCode)}`)].join('\n') + '\n',
  { mode: 0o600 },
);
writeFileSync(join(outDir, 'labels.html'), await labelSheet(done));
console.log(`${done.length}/${trackers.length} registered. Labels: ${join(outDir, 'labels.html')}`);
