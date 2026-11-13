/**
 * Supabase Edge Function: positions from ready-made trackers via Traccar.
 *
 *   tracker (e.g. Mictrack MT710) --TCP/UDP--> Traccar --HTTPS POST--> this
 *   function --> public.ingest_tracker_position() / tracker_heartbeat()
 *
 * Traccar decodes the tracker's own protocol and forwards every position as
 * JSON (see cloud/traccar/traccar.xml). The tracker id is the IMEI that
 * Traccar reports as device.uniqueId; only trackers registered with
 * provision_tracker() and claimed in the app are stored.
 *
 * Deploy:  supabase functions deploy traccar-ingest --no-verify-jwt
 *          supabase secrets set TRACCAR_FORWARD_SECRET=<32+ random characters>
 * (Traccar cannot mint Supabase JWTs; it sends the shared secret in the
 *  x-pt-ingest-secret header instead.)
 */
import { createClient } from "npm:@supabase/supabase-js@2.45.4";

import { secretMatches } from "../_shared/secret.ts";
import { parseTraccarForward } from "../_shared/traccar.ts";

const SECRET = Deno.env.get("TRACCAR_FORWARD_SECRET") ?? "";
const supabase = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  { auth: { persistSession: false } },
);

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

Deno.serve(async (req) => {
  if (req.method !== "POST") return json(405, { error: "method not allowed" });
  // Header first; ?key= in forward.url is the fallback for Traccar versions
  // that don't send forward.header.
  const given = req.headers.get("x-pt-ingest-secret") ?? new URL(req.url).searchParams.get("key");
  if (!(await secretMatches(given, SECRET))) {
    return json(401, { error: "unauthorized" });
  }

  const raw = await req.text();
  if (raw.length > 16_384) return json(413, { error: "payload too large" });
  let body: unknown;
  try {
    body = JSON.parse(raw);
  } catch {
    return json(400, { error: "invalid JSON" });
  }

  const msg = parseTraccarForward(body);
  // 200 for anything that will never become valid, so Traccar doesn't retry it.
  if (msg.kind === "ignore") return json(200, { status: "ignored", reason: msg.reason });

  const { data, error } =
    msg.kind === "position"
      ? await supabase.rpc("ingest_tracker_position", {
          p_device_uid: msg.deviceUid,
          p_lat: msg.lat,
          p_lng: msg.lng,
          p_accuracy_m: msg.accuracyM,
          p_battery_pct: msg.batteryPct,
          p_recorded_at: msg.recordedAt,
        })
      : await supabase.rpc("tracker_heartbeat", { p_device_uid: msg.deviceUid, p_battery_pct: msg.batteryPct });

  if (error) {
    console.error(JSON.stringify({ msg: "tracker ingest failed", device: msg.deviceUid, error: error.message }));
    return json(503, { error: "storage unavailable" }); // Traccar retries (forward.retry.enable)
  }
  return json(200, { kind: msg.kind, status: (data as { status?: string } | null)?.status ?? "ok" });
});
