#!/usr/bin/env node
/**
 * A label for the app's demo collar (DEMO-0001), to try scanning without a
 * real tracker: open the app in demo mode → Add cat → GPS collar → Scan.
 *   node demo-label.mjs   → out/demo-label.html and out/demo-label.png
 */
import { mkdirSync, writeFileSync } from 'node:fs';

import { labelPng, labelSheet } from './labels.mjs';

// Keep in sync with DEMO_COLLAR in app/src/backend/demoBackend.ts.
const DEMO = { deviceUid: 'DEMO-0001', claimCode: 'DEMOCODE2345' };

mkdirSync('out', { recursive: true });
writeFileSync('out/demo-label.png', await labelPng(DEMO.deviceUid, DEMO.claimCode));
writeFileSync('out/demo-label.html', await labelSheet([DEMO]));
console.log('Wrote out/demo-label.html and out/demo-label.png');
