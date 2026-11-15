// Lists every translation key in the app (t/tr/tk('...') and tn(n, '...', '...')).
// Used by i18n.test.ts and to find keys missing from nl.ts:
//   node src/i18n/extract.mjs --missing
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = new URL('../../', import.meta.url).pathname;
const DIRS = ['app', 'src'];

function files(dir) {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) return n === 'node_modules' ? [] : files(p);
    return /\.(ts|tsx)$/.test(n) && !/\.test\.ts$/.test(n) && !p.includes('/i18n/') ? [p] : [];
  });
}

const STR = String.raw`'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"`;
const ONE = new RegExp(String.raw`\b(?:t|tr|tk)\(\s*(?:${STR})`, 'g');
const TN = new RegExp(String.raw`\btn\([^,()]+(?:\([^()]*\))?[^,()]*,\s*(?:${STR})\s*,\s*(?:${STR})`, 'g');
const unescape = (s) => s.replace(/\\(['"\\])/g, '$1');

export function extractKeys() {
  const keys = new Map();
  for (const f of DIRS.flatMap((d) => files(join(ROOT, d)))) {
    const src = readFileSync(f, 'utf8');
    for (const m of src.matchAll(ONE)) keys.set(unescape(m[1] ?? m[2]), f);
    for (const m of src.matchAll(TN)) {
      keys.set(unescape(m[1] ?? m[2]), f);
      keys.set(unescape(m[3] ?? m[4]), f);
    }
  }
  return keys;
}

if (process.argv.includes('--missing') || process.argv.includes('--all')) {
  const { NL } = await import('./nl.ts');
  const keys = extractKeys();
  for (const [k] of keys) if (process.argv.includes('--all') || !(k in NL)) console.log(JSON.stringify(k));
}
