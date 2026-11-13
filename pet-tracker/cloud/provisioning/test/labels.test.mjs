import assert from 'node:assert/strict';
import { test } from 'node:test';

import { claimLink, labelSheet, parseTrackerCsv, prettyClaimCode } from '../labels.mjs';

test('CSV: header and blank lines are skipped, model and ICCID optional', () => {
  assert.deepEqual(parseTrackerCsv('imei,model,iccid\n861234567890123,MT710,8988228066602340000\n\n7364512\n'), [
    { deviceUid: '861234567890123', model: 'MT710', iccid: '8988228066602340000' },
    { deviceUid: '7364512', model: null, iccid: null },
  ]);
  assert.throws(() => parseTrackerCsv('not an id!'), /Not a tracker id/);
});

test('claim link opens Add cat with the collar filled in', () => {
  assert.equal(claimLink('861234567890123', 'ABCDEFGHJKLM'), 'cattracker://add-cat?device=861234567890123&code=ABCDEFGHJKLM');
  assert.equal(prettyClaimCode('ABCDEFGHJKLM'), 'ABCD-EFGH-JKLM');
});

test('label sheet has a QR code and readable code per tracker', async () => {
  const html = await labelSheet([{ deviceUid: '861234567890123', claimCode: 'ABCDEFGHJKLM' }]);
  assert.match(html, /<svg/);
  assert.match(html, /ABCD-EFGH-JKLM/);
});

test('the printed QR code scans back to exactly the claim link', async () => {
  const { default: jsQR } = await import('jsqr');
  const { PNG } = await import('pngjs');
  const { labelPng } = await import('../labels.mjs');
  const png = PNG.sync.read(await labelPng('861234567890123', 'ABCDEFGHJKLM'));
  const found = jsQR(new Uint8ClampedArray(png.data), png.width, png.height);
  assert.equal(found?.data, 'cattracker://add-cat?device=861234567890123&code=ABCDEFGHJKLM');
});
