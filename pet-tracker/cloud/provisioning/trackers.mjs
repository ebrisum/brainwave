#!/usr/bin/env node
/**
 * Sales and support: which tracker (and SIM) belongs to which customer.
 *
 *   node trackers.mjs list [search]      search: tracker id, ICCID or email
 *   node trackers.mjs csv > trackers.csv everything, for a spreadsheet
 *   node trackers.mjs reset <tracker id> a returned tracker: removes the owner
 *                                        and history, prints a new label
 *
 * Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the environment.
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { labelPng, labelSheet, prettyClaimCode } from './labels.mjs';
import { rpcClient } from './supabase.mjs';

const [command, arg] = process.argv.slice(2);
const rpc = rpcClient();
const day = (iso) => (iso ? iso.slice(0, 16).replace('T', ' ') : '');
const COLUMNS = ['device_uid', 'model', 'iccid', 'status', 'owner_email', 'cat_name', 'household_name', 'claimed_at', 'last_seen_at', 'battery_pct'];

if (command === 'list') {
  const rows = await rpc('list_trackers', { p_search: arg ?? null });
  console.table(rows.map((r) => ({
    tracker: r.device_uid, model: r.model ?? '', sim: r.iccid ?? '', owner: r.owner_email ?? '— not claimed —',
    cat: r.cat_name ?? '', claimed: day(r.claimed_at), 'last check-in': day(r.last_seen_at), battery: r.battery_pct ?? '',
  })));
  console.log(`${rows.length} tracker(s)`);
} else if (command === 'csv') {
  const rows = await rpc('list_trackers', { p_search: null });
  const cell = (v) => (v == null ? '' : /[",\n]/.test(String(v)) ? `"${String(v).replaceAll('"', '""')}"` : String(v));
  console.log([COLUMNS.join(','), ...rows.map((r) => COLUMNS.map((c) => cell(r[c])).join(','))].join('\n'));
} else if (command === 'reset' && arg) {
  const code = await rpc('reset_tracker', { p_device_uid: arg });
  const dir = join('out', 'reset');
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, `${arg}.png`), await labelPng(arg, code));
  writeFileSync(join(dir, `${arg}.html`), await labelSheet([{ deviceUid: arg, claimCode: code }]));
  console.log(`${arg} is free again. New code: ${prettyClaimCode(code)}. New label: ${join(dir, `${arg}.html`)}`);
} else {
  console.error('Usage: node trackers.mjs list [search] | csv | reset <tracker id>');
  process.exit(1);
}
