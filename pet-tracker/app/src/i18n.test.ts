import assert from 'node:assert/strict';
import { test } from 'node:test';

import { getLang, setLang, t, tn } from './i18n/core.ts';
import { NL } from './i18n/nl.ts';
// @ts-expect-error plain ESM helper without types
import { extractKeys } from './i18n/extract.mjs';

const placeholders = (s: string) => [...new Set(s.match(/\{\w+\}/g) ?? [])].sort();

test('every text in the app has a Dutch translation', () => {
  const keys: Map<string, string> = extractKeys();
  assert.ok(keys.size > 500, `found only ${keys.size} keys`);
  const missing = [...keys].filter(([k]) => !(k in NL)).map(([k, f]) => `${k}  (${f})`);
  assert.deepEqual(missing, []);
});

test('Dutch keeps every {placeholder}', () => {
  const wrong = Object.entries(NL).filter(([en, nl]) => placeholders(en).join() !== placeholders(nl).join());
  assert.deepEqual(wrong, []);
});

test('t() fills in placeholders and switches language', () => {
  const before = getLang();
  setLang('en');
  assert.equal(t('{name} left {zone}', { name: 'Minoes', zone: 'Home' }), 'Minoes left Home');
  assert.equal(tn(1, '{n} cat', '{n} cats'), '1 cat');
  assert.equal(tn(3, '{n} cat', '{n} cats'), '3 cats');
  setLang('nl');
  assert.equal(t('{name} left {zone}', { name: 'Minoes', zone: 'Thuis' }), 'Minoes is Thuis uit');
  assert.equal(tn(3, '{n} cat', '{n} cats'), '3 katten');
  assert.equal(t('Not a translated text'), 'Not a translated text');
  setLang(before);
});
