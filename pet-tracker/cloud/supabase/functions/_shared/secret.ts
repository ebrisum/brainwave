/** Constant-time comparison of a shared secret (at least 32 characters). */
const encoder = new TextEncoder();

export async function secretMatches(candidate: string | null, secret: string): Promise<boolean> {
  if (!candidate || secret.length < 32) return false;
  const [a, b] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(candidate)),
    crypto.subtle.digest("SHA-256", encoder.encode(secret)),
  ]);
  const x = new Uint8Array(a);
  const y = new Uint8Array(b);
  let diff = 0;
  for (let i = 0; i < x.length; i++) diff |= x[i]! ^ y[i]!;
  return diff === 0;
}
