/**
 * Supabase Edge Function: send queued settings to ready-made trackers.
 *
 * Trigger: Database Webhook on INSERT into public.device_commands
 * (Dashboard -> Database -> Webhooks -> "Supabase Edge Functions" ->
 * tracker-commands), like send-push. Keep JWT verification ON.
 *
 * Rows are queued by the database when lost mode or the report interval of
 * a Traccar tracker changes. This function sends them through Traccar's API
 * as a "custom" command whose text comes from TRACKER_INTERVAL_COMMAND,
 * e.g. "TIMER,{seconds}#" - take the exact syntax from the tracker's manual.
 * Traccar delivers it while the tracker is connected, or queues it.
 *
 * Secrets:  TRACCAR_URL (e.g. https://traccar.example.com), TRACCAR_USER,
 *           TRACCAR_PASSWORD, TRACKER_INTERVAL_COMMAND
 */
import { createClient } from "npm:@supabase/supabase-js@2.45.4";

import { buildCommand } from "../_shared/traccar.ts";

const MAX_ATTEMPTS = 5;
const TRACCAR_URL = (Deno.env.get("TRACCAR_URL") ?? "").replace(/\/+$/, "");
const AUTH = "Basic " + btoa(`${Deno.env.get("TRACCAR_USER") ?? ""}:${Deno.env.get("TRACCAR_PASSWORD") ?? ""}`);
const TEMPLATE = Deno.env.get("TRACKER_INTERVAL_COMMAND") ?? "";

const db = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  { auth: { persistSession: false } },
);

interface CommandRow {
  id: number;
  attempts: number;
  payload: { seconds: number; lost_mode: boolean };
  devices: { device_uid: string } | null;
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

async function traccar(path: string, init?: RequestInit): Promise<Response> {
  return await fetch(`${TRACCAR_URL}${path}`, {
    ...init,
    headers: { authorization: AUTH, "content-type": "application/json", accept: "application/json", ...init?.headers },
  });
}

async function send(row: CommandRow): Promise<string | null> {
  if (!TRACCAR_URL || !TEMPLATE) return "TRACCAR_URL or TRACKER_INTERVAL_COMMAND is not set";
  const uid = row.devices?.device_uid;
  if (!uid) return "device not found";

  const found = await traccar(`/api/devices?uniqueId=${encodeURIComponent(uid)}`);
  if (!found.ok) return `traccar devices: HTTP ${found.status}`;
  const [device] = (await found.json()) as Array<{ id: number }>;
  if (!device) return "tracker not known to Traccar yet (it has never connected)";

  const res = await traccar("/api/commands/send", {
    method: "POST",
    body: JSON.stringify({
      deviceId: device.id,
      type: "custom",
      attributes: { data: buildCommand(TEMPLATE, row.payload.seconds) },
    }),
  });
  // 200: sent now; 202: queued until the tracker connects.
  return res.ok ? null : `traccar command: HTTP ${res.status} ${(await res.text()).slice(0, 200)}`;
}

Deno.serve(async () => {
  const { data, error } = await db
    .from("device_commands")
    .select("id, attempts, payload, devices(device_uid)")
    .is("sent_at", null)
    .lt("attempts", MAX_ATTEMPTS)
    .order("created_at")
    .limit(20);
  if (error) return json(500, { error: error.message });

  let sent = 0;
  for (const row of (data ?? []) as unknown as CommandRow[]) {
    const problem = await send(row).catch((e: unknown) => String(e));
    await db
      .from("device_commands")
      .update(problem ? { attempts: row.attempts + 1, last_error: problem } : { sent_at: new Date().toISOString(), last_error: null })
      .eq("id", row.id);
    if (!problem) sent++;
    else console.warn(JSON.stringify({ msg: "tracker command failed", id: row.id, problem }));
  }
  return json(200, { sent });
});
