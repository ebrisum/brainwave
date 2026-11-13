import assert from 'node:assert/strict';
import { test } from 'node:test';

import { normalizeClaimCode, parseClaimQr } from './claim.ts';

test('reads the link printed on labels', () => {
  // Same string the provisioning script encodes (cloud/provisioning/labels.mjs).
  assert.deepEqual(parseClaimQr('cattracker://add-cat?device=861234567890123&code=ABCDEFGHJKLM'), {
    deviceUid: '861234567890123',
    claimCode: 'ABCDEFGHJKLM',
  });
});

test('also accepts https and Expo Go links with the same parameters', () => {
  assert.equal(parseClaimQr('https://cattracker.app/claim?device=TEST-0001&code=ABCD-EFGH-JKLM')?.claimCode, 'ABCDEFGHJKLM');
  assert.equal(parseClaimQr('exp://192.168.1.4:8081/--/add-cat?device=TEST-0001&code=ABCDEFGHJKLM')?.deviceUid, 'TEST-0001');
});

test('other QR codes are not mistaken for a label', () => {
  for (const text of [
    'https://example.com/menu',
    'WIFI:S:home;T:WPA;P:secret;;',
    'cattracker://add-cat?device=861234567890123',
    'cattracker://add-cat?device=bad id!&code=ABCDEFGHJKLM',
    'ABCDEFGHJKLM',
    'javascript://x?device=TEST-0001&code=ABCDEFGHJKLM',
  ]) {
    assert.equal(parseClaimQr(text), null, text);
  }
});

test('typed codes may contain dashes and spaces', () => {
  assert.equal(normalizeClaimCode(' ABCD-EFGH JKLM '), 'ABCDEFGHJKLM');
});

test('a link made in the app reads back as the same label', async () => {
  const { claimLink, prettyClaimCode } = await import('./claim.ts');
  assert.deepEqual(parseClaimQr(claimLink('CT-ABCDEF', 'ABCDEFGHJKLM')), { deviceUid: 'CT-ABCDEF', claimCode: 'ABCDEFGHJKLM' });
  assert.equal(prettyClaimCode('ABCDEFGHJKLM'), 'ABCD-EFGH-JKLM');
});
