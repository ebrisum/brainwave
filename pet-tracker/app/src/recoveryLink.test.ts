import assert from 'node:assert/strict';
import { test } from 'node:test';

import { parseRecoveryLink } from './recoveryLink.ts';

test('the link in the standard reset e-mail gives the token hash', () => {
  const link = 'https://cioraxkasfsbqocbqmmf.supabase.co/auth/v1/verify?token=pkce_0a1b2c3d4e5f60718293a4b5c6d7e8f9a0b1c2d3e4f5&type=recovery&redirect_to=http://localhost:3000';
  assert.deepEqual(parseRecoveryLink(link), { kind: 'token_hash', tokenHash: 'pkce_0a1b2c3d4e5f60718293a4b5c6d7e8f9a0b1c2d3e4f5' });
});

test('an already opened link (browser address) gives the session', () => {
  const opened = 'http://localhost:3000/#access_token=eyJhbGciOi.abc.def&expires_in=3600&refresh_token=r3fr35h&token_type=bearer&type=recovery';
  assert.deepEqual(parseRecoveryLink(opened), { kind: 'session', accessToken: 'eyJhbGciOi.abc.def', refreshToken: 'r3fr35h' });
});

test('other text and other link types are not mistaken for a reset link', () => {
  assert.equal(parseRecoveryLink('123456'), null);
  assert.equal(parseRecoveryLink('https://example.com/'), null);
  assert.equal(parseRecoveryLink('https://x.supabase.co/auth/v1/verify?token=abcdefghijkl&type=signup'), null);
});
