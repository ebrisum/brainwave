/** Calls a database function as service_role (only from your own computer or server). */
export function rpcClient(env = process.env) {
  const url = env.SUPABASE_URL?.replace(/\/+$/, '');
  const key = env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    console.error('Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (Supabase → Settings → API). Never put the service role key in the app.');
    process.exit(1);
  }
  return async function rpc(name, args) {
    const res = await fetch(`${url}/rest/v1/rpc/${name}`, {
      method: 'POST',
      headers: { apikey: key, authorization: `Bearer ${key}`, 'content-type': 'application/json' },
      body: JSON.stringify(args),
    });
    const text = await res.text();
    if (!res.ok) throw new Error(`${name}: ${res.status} ${text}`);
    return text ? JSON.parse(text) : null;
  };
}
