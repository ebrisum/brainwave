-- =============================================================================
-- Ready-made trackers, tracker health and "where is my cat".
--
--   * Trackers bought ready-made (e.g. Mictrack MT710) report through a
--     Traccar server, which forwards each position to the `traccar-ingest`
--     Edge Function. They are registered with provision_tracker(), which
--     returns the claim code for the label.
--   * A tracker that stops checking in raises a "tracker silent" alert once
--     (pg_cron, every 15 minutes) and re-arms when it reports again.
--   * get_cat_status(): is the cat in one of its zones, or how far away.
--   * get_tracker_health(): battery drain and days left, check-ins, silence.
--   * device_commands: settings to send to Traccar trackers (report interval,
--     faster in lost mode), delivered by the `tracker-commands` Edge Function.
-- =============================================================================

alter type public.notification_kind add value if not exists 'tracker_silent';

alter table public.devices
  add column protocol          text not null default 'pt-v1' check (protocol in ('pt-v1', 'traccar')),
  add column model             text check (char_length(model) <= 32),
  add column iccid             text check (iccid ~ '^[0-9]{18,22}$'),
  add column silent_after_s    integer not null default 10800 check (silent_after_s between 1800 and 172800),
  add column silent_alerted_at timestamptz;

comment on column public.devices.protocol is
  'pt-v1: our own firmware over MQTT; traccar: a ready-made tracker reporting through Traccar.';

-- -----------------------------------------------------------------------------
-- Registering ready-made trackers (service_role: provisioning script)
-- -----------------------------------------------------------------------------
create or replace function public.new_claim_code()
returns text
language sql
volatile
set search_path = ''
as $$
  -- 12 characters from 32 unambiguous ones: 60 bits.
  select string_agg(substr('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', (get_byte(b, i) % 32) + 1, 1), '')
    from (select extensions.gen_random_bytes(12) as b) r, generate_series(0, 11) i;
$$;
revoke execute on function public.new_claim_code() from public, anon, authenticated;

-- Returns the claim code to print on the label. The device id is the IMEI
-- (or another id the tracker reports to Traccar, e.g. the Traccar Client app).
create or replace function public.provision_tracker(
  p_device_uid text,
  p_model      text default null,
  p_iccid      text default null
)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_code text := public.new_claim_code();
  v_id   uuid;
begin
  v_id := public.provision_device(
    p_device_uid,
    case when p_device_uid ~ '^[0-9]{15}$' then p_device_uid end,
    v_code);
  update public.devices
     set protocol = 'traccar', model = p_model, iccid = p_iccid
   where id = v_id;
  return v_code;
end;
$$;
revoke execute on function public.provision_tracker(text, text, text) from public, anon, authenticated;
grant execute on function public.provision_tracker(text, text, text) to service_role;

-- A position from Traccar. Trackers that don't send a battery level keep the
-- last known one (0 % would fire low-battery alerts).
create or replace function public.ingest_tracker_position(
  p_device_uid   text,
  p_lat          double precision,
  p_lng          double precision,
  p_accuracy_m   real,
  p_battery_pct  smallint default null,
  p_recorded_at  timestamptz default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_battery smallint;
begin
  select coalesce(p_battery_pct, d.last_battery_pct, 100) into v_battery
    from public.devices d where d.device_uid = p_device_uid and d.protocol = 'traccar';
  if not found then
    return jsonb_build_object('status', 'unknown_device');
  end if;
  return public.ingest_telemetry(
    p_device_uid, p_lat, p_lng,
    least(greatest(coalesce(p_accuracy_m, 0), 0), 100000)::real,
    least(greatest(v_battery, 0), 100)::smallint,
    null,
    least(coalesce(p_recorded_at, now()), now()));
end;
$$;
revoke execute on function public.ingest_tracker_position(text, double precision, double precision, real, smallint, timestamptz) from public, anon, authenticated;
grant execute on function public.ingest_tracker_position(text, double precision, double precision, real, smallint, timestamptz) to service_role;

-- A check-in without a position (no GPS fix indoors): the tracker is alive.
create or replace function public.tracker_heartbeat(p_device_uid text, p_battery_pct smallint default null)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.devices
     set last_seen_at     = now(),
         last_battery_pct = coalesce(p_battery_pct, last_battery_pct)
   where device_uid = p_device_uid
     and status = 'active'
     and owner_id is not null;
  return jsonb_build_object('status', case when found then 'ok' else 'unknown_or_inactive_device' end);
end;
$$;
revoke execute on function public.tracker_heartbeat(text, smallint) from public, anon, authenticated;
grant execute on function public.tracker_heartbeat(text, smallint) to service_role;

-- -----------------------------------------------------------------------------
-- "Tracker silent"
-- -----------------------------------------------------------------------------
create or replace function public.devices_rearm_silent()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.last_seen_at is distinct from old.last_seen_at then
    new.silent_alerted_at := null;
  end if;
  return new;
end;
$$;

create trigger devices_rearm_silent
  before update of last_seen_at on public.devices
  for each row execute function public.devices_rearm_silent();

-- Collars only: a phone tracker stops whenever its owner stops it.
create or replace function public.check_silent_trackers()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  n integer;
begin
  with silent as (
    update public.devices d
       set silent_alerted_at = now()
     where d.kind = 'collar'
       and d.status = 'active'
       and d.owner_id is not null
       and d.last_seen_at is not null
       and d.last_seen_at < now() - make_interval(secs => d.silent_after_s)
       and d.silent_alerted_at is null
    returning d.id, d.owner_id, d.display_name, d.last_seen_at, d.timezone, d.last_battery_pct
  )
  insert into public.notification_outbox (owner_id, device_id, kind, title, body)
  select s.owner_id, s.id, 'tracker_silent',
         coalesce(s.display_name, 'Your cat') || '''s tracker is silent',
         'No check-in since ' || to_char(s.last_seen_at at time zone s.timezone, 'HH24:MI') ||
         case when s.last_battery_pct is not null and s.last_battery_pct < 25
              then '. The battery was low: charge it and put it back on.'
              else '. It may be out of range, or switched off.' end
    from silent s;
  get diagnostics n = row_count;
  return n;
end;
$$;
revoke execute on function public.check_silent_trackers() from public, anon, authenticated;
grant execute on function public.check_silent_trackers() to service_role;

do $$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule('pet-tracker-silent-trackers', '*/15 * * * *',
                          'select public.check_silent_trackers();');
  end if;
end;
$$;

-- -----------------------------------------------------------------------------
-- Where is the cat: inside one of its zones, or how far from the nearest
-- -----------------------------------------------------------------------------
-- Same rule as ingest_telemetry: the household's zones, the cat's own zones,
-- and its owner's older "all my cats" zones.
create or replace function public.zone_applies(p_g public.geofences, p_d public.devices)
returns boolean
language sql
immutable
set search_path = ''
as $$
  select p_g.enabled
     and (   (p_g.household_id is not null and p_g.household_id = p_d.household_id)
          or (p_g.household_id is null and p_g.owner_id = p_d.owner_id
              and (p_g.device_id is null or p_g.device_id = p_d.id)));
$$;

create or replace function public.get_cat_status()
returns table (device_id uuid, zone_name text, nearest_zone_name text, nearest_zone_m double precision)
language sql
stable
security definer
set search_path = ''
as $$
  select d.id,
         -- the zone it is in, as decided by the alerts (with GPS hysteresis)
         (select g.name
            from public.geofence_state s
            join public.geofences g on g.id = s.geofence_id
           where s.device_id = d.id and s.inside and public.zone_applies(g, d)
           order by (g.household_id is not null) desc, extensions.st_area(g.area)
           limit 1),
         near.name,
         near.m
    from public.devices d
    left join lateral (
      select g.name, extensions.st_distance(g.area, d.last_location) as m
        from public.geofences g
       where public.zone_applies(g, d) and d.last_location is not null
       order by extensions.st_distance(g.area, d.last_location)
       limit 1
    ) near on true
   where d.id in (select public.viewable_device_ids())
     and d.owner_id is not null;
$$;
revoke execute on function public.get_cat_status() from public, anon;
grant execute on function public.get_cat_status() to authenticated;

-- -----------------------------------------------------------------------------
-- Tracker health
-- -----------------------------------------------------------------------------
-- Battery drain is fitted over the positions since the last charge (at most
-- 7 days, at least 3 hours of data), so a recent charge doesn't hide the trend.
create or replace function public.get_tracker_health(p_device_id uuid)
returns table (
  last_seen_at       timestamptz,
  last_fix_at        timestamptz,
  battery_pct        smallint,
  drain_pct_per_day  double precision,
  days_left          double precision,
  fixes_24h          integer,
  report_interval_s  integer,
  silent             boolean,
  silent_after_s     integer
)
language plpgsql
stable
security definer
set search_path = ''
as $$
#variable_conflict use_column
declare
  v_dev    public.devices;
  v_charge timestamptz;
  v_slope  double precision;
  v_span   double precision;
begin
  select * into v_dev from public.devices d
   where d.id = p_device_id and d.id in (select public.viewable_device_ids());
  if not found then
    raise exception 'cat not found' using errcode = 'P0002';
  end if;

  select max(t.recorded_at) into v_charge
    from (select recorded_at, battery_pct, lag(battery_pct) over (order by recorded_at) as prev
            from public.telemetry
           where device_id = p_device_id and recorded_at > now() - interval '7 days'
             and battery_pct is not null) t
   where t.battery_pct >= t.prev + 5;

  select regr_slope(t.battery_pct, extract(epoch from t.recorded_at)) * 86400,
         extract(epoch from max(t.recorded_at) - min(t.recorded_at))
    into v_slope, v_span
    from public.telemetry t
   where t.device_id = p_device_id
     and t.recorded_at >= greatest(coalesce(v_charge, '-infinity'), now() - interval '7 days')
     and t.battery_pct is not null;

  last_seen_at      := v_dev.last_seen_at;
  last_fix_at       := v_dev.last_fix_at;
  battery_pct       := v_dev.last_battery_pct;
  drain_pct_per_day := case when v_span >= 3 * 3600 and v_slope < 0 then -v_slope end;
  days_left         := case when drain_pct_per_day > 0.1 and v_dev.last_battery_pct is not null
                            then v_dev.last_battery_pct / drain_pct_per_day end;
  fixes_24h         := (select count(*) from public.telemetry t
                         where t.device_id = p_device_id and t.recorded_at > now() - interval '24 hours');
  report_interval_s := v_dev.report_interval_s;
  silent_after_s    := v_dev.silent_after_s;
  silent            := v_dev.kind = 'collar'
                       and v_dev.last_seen_at < now() - make_interval(secs => v_dev.silent_after_s);
  return next;
end;
$$;
revoke execute on function public.get_tracker_health(uuid) from public, anon;
grant execute on function public.get_tracker_health(uuid) to authenticated;

-- -----------------------------------------------------------------------------
-- Commands for Traccar trackers (our own firmware gets its config over MQTT)
-- -----------------------------------------------------------------------------
create table public.device_commands (
  id          bigint generated always as identity primary key,
  device_id   uuid not null references public.devices (id) on delete cascade,
  kind        text not null check (kind in ('report_interval')),
  payload     jsonb not null,
  created_at  timestamptz not null default now(),
  sent_at     timestamptz,
  attempts    smallint not null default 0,
  last_error  text
);
create index device_commands_pending_idx on public.device_commands (created_at) where sent_at is null;
alter table public.device_commands enable row level security;
revoke all on public.device_commands from anon, authenticated;

-- Lost mode reports every 30 s; otherwise the cat's normal interval. A newer
-- command replaces one that hasn't gone out yet.
create or replace function public.devices_queue_tracker_command()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.protocol = 'traccar' and new.owner_id is not null then
    update public.device_commands
       set sent_at = now(), last_error = 'superseded'
     where device_id = new.id and sent_at is null and kind = 'report_interval';
    insert into public.device_commands (device_id, kind, payload)
    values (new.id, 'report_interval',
            jsonb_build_object('seconds', case when new.lost_mode then 30 else new.report_interval_s end,
                               'lost_mode', new.lost_mode));
  end if;
  return null;
end;
$$;

create trigger devices_queue_tracker_command
  after update of lost_mode, report_interval_s on public.devices
  for each row
  when (old.lost_mode is distinct from new.lost_mode or old.report_interval_s is distinct from new.report_interval_s)
  execute function public.devices_queue_tracker_command();
