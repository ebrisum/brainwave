-- =============================================================================
-- "Resting" as reported by the collar.
--
-- A collar whose accelerometer says the pet hasn't moved sends a check-in
-- without a GNSS fix (note "still"). The app shows that as "Resting since
-- <last position>" instead of leaving owners to wonder whether the collar
-- went quiet. Any new position clears it.
-- =============================================================================

alter table public.devices add column resting boolean not null default false;

comment on column public.devices.resting is
  'The latest check-in said the pet has not moved since its last position (accelerometer).';

drop function public.tracker_heartbeat(text, smallint);
create function public.tracker_heartbeat(
  p_device_uid  text,
  p_battery_pct smallint default null,
  p_note        text default null  -- still | no_sky | timeout | skipped
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.devices
     set last_seen_at     = now(),
         last_battery_pct = coalesce(p_battery_pct, last_battery_pct),
         resting          = coalesce(p_note = 'still', false)
   where device_uid = p_device_uid
     and status = 'active'
     and owner_id is not null;
  return jsonb_build_object('status', case when found then 'ok' else 'unknown_or_inactive_device' end);
end;
$$;
revoke execute on function public.tracker_heartbeat(text, smallint, text) from public, anon, authenticated;
grant execute on function public.tracker_heartbeat(text, smallint, text) to service_role;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'telemetry_ingest') then
    grant execute on function public.tracker_heartbeat(text, smallint, text) to telemetry_ingest;
  end if;
end;
$$;

-- A new position means fresh news: no longer "resting" until the collar says so again.
create or replace function public.devices_clear_resting()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.last_fix_at is distinct from old.last_fix_at then
    new.resting := false;
  end if;
  return new;
end;
$$;

create trigger devices_clear_resting
  before update of last_fix_at on public.devices
  for each row execute function public.devices_clear_resting();

drop function public.get_tracker_health(uuid);
create function public.get_tracker_health(p_device_id uuid)
returns table (
  last_seen_at       timestamptz,
  last_fix_at        timestamptz,
  battery_pct        smallint,
  drain_pct_per_day  double precision,
  days_left          double precision,
  fixes_24h          integer,
  report_interval_s  integer,
  silent             boolean,
  silent_after_s     integer,
  resting            boolean
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
  resting           := v_dev.resting and not coalesce(silent, false);
  return next;
end;
$$;
revoke execute on function public.get_tracker_health(uuid) from public, anon;
grant execute on function public.get_tracker_health(uuid) to authenticated;
