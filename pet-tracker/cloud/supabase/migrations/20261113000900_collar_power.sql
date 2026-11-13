-- =============================================================================
-- Collar power features (firmware with the power policy, firmware/src/policy.c).
--
--   * The collar's config downlink now carries its home zones (household
--     zones first, at most 4, as centre + radius). The collar batches
--     positions inside them and uploads leaving / coming home at once.
--   * Zone changes and moving a cat to another household re-send the config.
--   * The ingest worker may record check-ins without a position
--     (pt/v1/<id>/telemetry/heartbeat) through tracker_heartbeat().
--   * Our collars check in every 4 h while the pet rests (no GNSS needed),
--     so their "tracker silent" alert waits 5 h; Traccar trackers keep 3 h.
-- =============================================================================

-- Security invoker on purpose: callers only see zones they may see (RLS);
-- triggers that run as the table owner see all zones of that cat.
create or replace function public.device_config_json(p_dev public.devices)
returns jsonb
language sql
stable
set search_path = ''
as $$
  with tz as (
    select (extract(epoch from (now() at time zone p_dev.timezone) - (now() at time zone 'UTC')) / 60)::int as offset_min
  ),
  zones as (
    select jsonb_build_object(
             'la', round(extensions.st_y(c.pt) * 1e6)::int,
             'lo', round(extensions.st_x(c.pt) * 1e6)::int,
             'r',  least(5000, greatest(10, round(sqrt(extensions.st_area(g.area) / pi()))))::int) as zone,
           row_number() over (order by (g.household_id is not null) desc, g.created_at) as n
      from public.geofences g
      cross join lateral (select extensions.st_centroid(g.area::extensions.geometry) as pt) c
     where public.zone_applies(g, p_dev)
  )
  select jsonb_build_object(
    'interval_s',  p_dev.report_interval_s,
    'lost_mode',   p_dev.lost_mode,
    'night_mode',  p_dev.night_mode,
    -- collars run on UTC; the window is re-sent daily so DST changes apply
    'night_start_utc_min', ((p_dev.night_start_min - tz.offset_min) % 1440 + 1440) % 1440,
    'night_end_utc_min',   ((p_dev.night_end_min   - tz.offset_min) % 1440 + 1440) % 1440,
    'night_interval_s', p_dev.night_interval_s,
    'zones', coalesce((select jsonb_agg(z.zone order by z.n) from zones z where z.n <= 4), '[]'::jsonb))
  from tz;
$$;

-- Our own collars only (Traccar trackers get settings via device_commands).
create or replace function public.devices_notify_config()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.kind = 'collar' and new.protocol = 'pt-v1' and new.owner_id is not null then
    perform pg_notify('device_config', jsonb_build_object(
      'device_uid', new.device_uid,
      'config', public.device_config_json(new))::text);
  end if;
  return null;
end;
$$;

drop trigger devices_notify_config on public.devices;
create trigger devices_notify_config
  after update of lost_mode, night_mode, night_start_min, night_end_min,
                  night_interval_s, report_interval_s, timezone, household_id
  on public.devices
  for each row
  when (old is distinct from new)
  execute function public.devices_notify_config();

-- A zone added, moved or removed: re-send the config of every collar it applies to.
create or replace function public.geofences_notify_config()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  g public.geofences := coalesce(new, old);
  d public.devices;
begin
  for d in
    select * from public.devices v
     where v.kind = 'collar' and v.protocol = 'pt-v1' and v.owner_id is not null
       and (   (g.household_id is not null and v.household_id = g.household_id)
            or (g.household_id is null and v.owner_id = g.owner_id
                and (g.device_id is null or g.device_id = v.id)))
  loop
    perform pg_notify('device_config', jsonb_build_object(
      'device_uid', d.device_uid, 'config', public.device_config_json(d))::text);
  end loop;
  return null;
end;
$$;

create trigger geofences_notify_config
  after insert or update or delete on public.geofences
  for each row execute function public.geofences_notify_config();

-- The MQTT ingest worker's least-privilege role records check-ins too.
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'telemetry_ingest') then
    grant execute on function public.tracker_heartbeat(text, smallint) to telemetry_ingest;
  end if;
end;
$$;

-- "Tracker silent": 5 h for our collars (4-hourly check-ins while resting),
-- 3 h for ready-made trackers, which report on their own schedule.
alter table public.devices alter column silent_after_s set default 18000;
update public.devices set silent_after_s = 18000 where protocol = 'pt-v1' and silent_after_s = 10800;

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
     set protocol = 'traccar', model = p_model, iccid = p_iccid, silent_after_s = 10800
   where id = v_id;
  return v_code;
end;
$$;
