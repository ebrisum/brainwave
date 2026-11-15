-- =============================================================================
-- Everything the complete app needs from the database.
--
--   * Alerts inbox: every alert (zones, battery, silent collar, lost, found)
--     for the cats you can see, with "unread" since you last opened the inbox.
--     Alerts carry `meta` (zone name, battery %) so the app and the push
--     function can word them in the reader's language.
--   * Your settings: language, which alerts you get, quiet hours, and how long
--     location history is kept (30-365 days).
--   * Live share links for a lost cat: a link anyone can open, until it
--     expires or you stop it (get_shared_cat is the only anon function).
--   * Power mode per collar (battery saver / normal / live).
--   * Cat profile: date of birth, breed, weight, microchip, vet, indoor/outdoor.
--   * History for any day (get_pet_track_range), data export (GDPR art. 20)
--     and swapping a cat onto a new collar without losing its history.
-- =============================================================================

alter type public.notification_kind add value if not exists 'found';

-- -----------------------------------------------------------------------------
-- Alerts carry their facts, not only English text
-- -----------------------------------------------------------------------------
alter table public.notification_outbox add column if not exists meta jsonb not null default '{}'::jsonb;
create index if not exists notification_outbox_device_time_idx on public.notification_outbox (device_id, created_at desc);

create or replace function public.geofence_events_enqueue_push()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_zone text;
begin
  if not new.notify then
    return null;
  end if;
  select name into v_zone from public.geofences where id = new.geofence_id;
  insert into public.notification_outbox (owner_id, device_id, kind, title, body, meta)
  values (
    new.owner_id, new.device_id,
    case when new.transition = 'exit' then 'zone_exit' else 'zone_enter' end::public.notification_kind,
    case when new.transition = 'exit'
         then public.cat_name(new.device_id) || ' left ' || coalesce(v_zone, 'a zone')
         else public.cat_name(new.device_id) || ' is back in ' || coalesce(v_zone, 'a zone') end,
    case when new.transition = 'exit'
         then 'Tap to see where ' || public.cat_name(new.device_id) || ' is now.'
         else 'All good - ' || public.cat_name(new.device_id) || ' came home.' end,
    jsonb_build_object('zone', v_zone));
  return null;
end;
$$;

-- Low battery, lost mode on, and found (lost mode off again).
create or replace function public.devices_battery_and_lost_alerts()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.owner_id is null then
    return new;
  end if;

  if new.last_battery_pct is not null and new.last_battery_pct between 1 and 19
     and not old.low_battery_alerted then
    new.low_battery_alerted := true;
    insert into public.notification_outbox (owner_id, device_id, kind, title, body, meta)
    values (new.owner_id, new.id, 'low_battery',
            coalesce(new.display_name, 'Your cat') || '''s tracker battery is low',
            'Battery at ' || new.last_battery_pct || ' %. Charge it soon so you don''t lose track.',
            jsonb_build_object('battery', new.last_battery_pct));
  elsif new.last_battery_pct is not null and new.last_battery_pct >= 30 then
    new.low_battery_alerted := false;
  end if;

  if new.lost_mode and not old.lost_mode then
    insert into public.notification_outbox (owner_id, device_id, kind, title, body)
    values (new.owner_id, new.id, 'lost_mode',
            'Lost mode on for ' || coalesce(new.display_name, 'your cat'),
            'Positions now update as often as possible. Open the app to follow live.');
  elsif old.lost_mode and not new.lost_mode then
    insert into public.notification_outbox (owner_id, device_id, kind, title, body, meta)
    values (new.owner_id, new.id, 'found',
            coalesce(new.display_name, 'Your cat') || ' is found',
            'Lost mode is off again.',
            jsonb_build_object('lost_since', old.lost_mode_since));
  end if;

  return new;
end;
$$;

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
  insert into public.notification_outbox (owner_id, device_id, kind, title, body, meta)
  select s.owner_id, s.id, 'tracker_silent',
         coalesce(s.display_name, 'Your cat') || '''s tracker is silent',
         'No check-in since ' || to_char(s.last_seen_at at time zone s.timezone, 'HH24:MI') ||
         case when s.last_battery_pct is not null and s.last_battery_pct < 25
              then '. The battery was low: charge it and put it back on.'
              else '. It may be out of range, or switched off.' end,
         jsonb_build_object('last_seen_at', s.last_seen_at, 'battery', s.last_battery_pct)
    from silent s;
  get diagnostics n = row_count;
  return n;
end;
$$;
revoke execute on function public.check_silent_trackers() from public, anon, authenticated;
grant execute on function public.check_silent_trackers() to service_role;

-- -----------------------------------------------------------------------------
-- Alerts inbox
-- -----------------------------------------------------------------------------
create table if not exists public.alert_reads (
  user_id     uuid primary key references auth.users (id) on delete cascade,
  read_until  timestamptz not null default now()
);
alter table public.alert_reads enable row level security;
revoke all on public.alert_reads from anon, authenticated;

create or replace function public.list_alerts(p_limit integer default 50, p_before timestamptz default null)
returns table (id bigint, device_id uuid, kind text, title text, body text, meta jsonb,
               created_at timestamptz, unread boolean)
language sql
stable
security definer
set search_path = ''
as $$
  select o.id, o.device_id, o.kind::text, o.title, o.body, o.meta, o.created_at,
         o.created_at > coalesce((select r.read_until from public.alert_reads r where r.user_id = auth.uid()),
                                 '-infinity'::timestamptz)
    from public.notification_outbox o
   where o.device_id in (select public.viewable_device_ids())
     and (p_before is null or o.created_at < p_before)
   order by o.created_at desc
   limit least(greatest(coalesce(p_limit, 50), 1), 200);
$$;

create or replace function public.unread_alert_count()
returns integer
language sql
stable
security definer
set search_path = ''
as $$
  select count(*)::int
    from public.notification_outbox o
   where o.device_id in (select public.viewable_device_ids())
     and o.created_at > coalesce((select r.read_until from public.alert_reads r where r.user_id = auth.uid()),
                                 now() - interval '30 days');
$$;

create or replace function public.mark_alerts_read()
returns void
language sql
security definer
set search_path = ''
as $$
  insert into public.alert_reads (user_id, read_until) values (auth.uid(), now())
  on conflict (user_id) do update set read_until = excluded.read_until;
$$;

-- -----------------------------------------------------------------------------
-- Your settings
-- -----------------------------------------------------------------------------
create table if not exists public.user_settings (
  user_id                uuid primary key references auth.users (id) on delete cascade,
  lang                   text not null default 'en' check (lang in ('en', 'nl')),
  notify_zone_exit       boolean not null default true,
  notify_zone_enter      boolean not null default true,
  notify_low_battery     boolean not null default true,
  notify_tracker_silent  boolean not null default true,
  notify_found           boolean not null default true,
  quiet_enabled          boolean not null default false,
  quiet_start_min        smallint not null default 1380 check (quiet_start_min between 0 and 1439),
  quiet_end_min          smallint not null default 420  check (quiet_end_min between 0 and 1439),
  timezone               text not null default 'Europe/Amsterdam' check (char_length(timezone) <= 64),
  history_days           smallint not null default 180 check (history_days in (30, 90, 180, 365)),
  updated_at             timestamptz not null default now()
);
alter table public.user_settings enable row level security;
revoke all on public.user_settings from anon, authenticated;

create or replace function public.get_my_settings()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
           'lang',                  coalesce(s.lang, 'en'),
           'notify_zone_exit',      coalesce(s.notify_zone_exit, true),
           'notify_zone_enter',     coalesce(s.notify_zone_enter, true),
           'notify_low_battery',    coalesce(s.notify_low_battery, true),
           'notify_tracker_silent', coalesce(s.notify_tracker_silent, true),
           'notify_found',          coalesce(s.notify_found, true),
           'quiet_enabled',         coalesce(s.quiet_enabled, false),
           'quiet_start_min',       coalesce(s.quiet_start_min, 1380),
           'quiet_end_min',         coalesce(s.quiet_end_min, 420),
           'timezone',              coalesce(s.timezone, 'Europe/Amsterdam'),
           'history_days',          coalesce(s.history_days, 180))
    from (select 1) one
    left join public.user_settings s on s.user_id = auth.uid();
$$;

-- Only the keys present in p_changes are changed; the checks above validate.
create or replace function public.set_my_settings(p_changes jsonb)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid uuid := auth.uid();
begin
  if v_uid is null then
    raise exception 'not authenticated' using errcode = '42501';
  end if;
  insert into public.user_settings (user_id) values (v_uid) on conflict (user_id) do nothing;
  update public.user_settings u set
    lang                  = coalesce(p_changes ->> 'lang', u.lang),
    notify_zone_exit      = coalesce((p_changes ->> 'notify_zone_exit')::boolean, u.notify_zone_exit),
    notify_zone_enter     = coalesce((p_changes ->> 'notify_zone_enter')::boolean, u.notify_zone_enter),
    notify_low_battery    = coalesce((p_changes ->> 'notify_low_battery')::boolean, u.notify_low_battery),
    notify_tracker_silent = coalesce((p_changes ->> 'notify_tracker_silent')::boolean, u.notify_tracker_silent),
    notify_found          = coalesce((p_changes ->> 'notify_found')::boolean, u.notify_found),
    quiet_enabled         = coalesce((p_changes ->> 'quiet_enabled')::boolean, u.quiet_enabled),
    quiet_start_min       = coalesce((p_changes ->> 'quiet_start_min')::smallint, u.quiet_start_min),
    quiet_end_min         = coalesce((p_changes ->> 'quiet_end_min')::smallint, u.quiet_end_min),
    timezone              = coalesce(p_changes ->> 'timezone', u.timezone),
    history_days          = coalesce((p_changes ->> 'history_days')::smallint, u.history_days),
    updated_at            = now()
  where u.user_id = v_uid;
  return public.get_my_settings();
end;
$$;

-- Push targets for one alert, honouring each person's settings. Lost mode
-- always goes through; quiet hours mute everything else.
create or replace function public.in_quiet_hours(p_start smallint, p_end smallint, p_tz text, p_at timestamptz default now())
returns boolean
language sql
stable
set search_path = ''
as $$
  with m as (
    select (extract(hour from p_at at time zone p_tz) * 60 + extract(minute from p_at at time zone p_tz))::int as now_min
  )
  select case when p_start = p_end then false
              when p_start < p_end then m.now_min >= p_start and m.now_min < p_end
              else m.now_min >= p_start or m.now_min < p_end end
    from m;
$$;

create or replace function public.push_targets(p_owner_id uuid, p_device_id uuid, p_kind text)
returns table (token text, user_id uuid, lang text)
language sql
stable
security definer
set search_path = ''
as $$
  select r.token, r.user_id, coalesce(s.lang, 'en')
    from public.push_recipients(p_owner_id, p_device_id) r
    left join public.user_settings s on s.user_id = r.user_id
   where s.user_id is null
      or (
        case p_kind
          when 'zone_exit'      then s.notify_zone_exit
          when 'zone_enter'     then s.notify_zone_enter
          when 'low_battery'    then s.notify_low_battery
          when 'tracker_silent' then s.notify_tracker_silent
          when 'found'          then s.notify_found
          else true end
        and (p_kind = 'lost_mode' or not s.quiet_enabled
             or not public.in_quiet_hours(s.quiet_start_min, s.quiet_end_min, s.timezone)));
$$;
revoke execute on function public.push_targets(uuid, uuid, text) from public, anon, authenticated;
grant execute on function public.push_targets(uuid, uuid, text) to service_role;

-- -----------------------------------------------------------------------------
-- History retention per owner (replaces the fixed 180-day purge)
-- -----------------------------------------------------------------------------
create or replace function public.purge_history()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  n integer;
begin
  delete from public.telemetry t
   using (select d.id, coalesce(s.history_days, 180) as days
            from public.devices d
            left join public.user_settings s on s.user_id = d.owner_id) k
   where t.device_id = k.id and t.recorded_at < now() - make_interval(days => k.days);
  get diagnostics n = row_count;
  delete from public.telemetry where recorded_at < now() - interval '365 days';
  delete from public.geofence_events where occurred_at < now() - interval '365 days';
  delete from public.notification_outbox where created_at < now() - interval '180 days';
  delete from public.share_links where expires_at < now() - interval '7 days';
  return n;
end;
$$;
revoke execute on function public.purge_history() from public, anon, authenticated;
grant execute on function public.purge_history() to service_role;

-- -----------------------------------------------------------------------------
-- Live share links (lost cat: "help us look")
-- -----------------------------------------------------------------------------
create table if not exists public.share_links (
  token       text primary key check (token ~ '^[A-Za-z0-9_-]{20,64}$'),
  device_id   uuid not null references public.devices (id) on delete cascade,
  created_by  uuid not null references auth.users (id) on delete cascade,
  created_at  timestamptz not null default now(),
  expires_at  timestamptz not null,
  revoked_at  timestamptz
);
create index if not exists share_links_device_idx on public.share_links (device_id);
alter table public.share_links enable row level security;
revoke all on public.share_links from anon, authenticated;

create or replace function public.create_share_link(p_device_id uuid, p_hours integer default 72)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_token text;
  v_exp   timestamptz := now() + make_interval(hours => least(greatest(coalesce(p_hours, 72), 1), 24 * 14));
begin
  if p_device_id not in (select public.viewable_device_ids()) then
    raise exception 'cat not found' using errcode = 'P0002';
  end if;
  v_token := translate(encode(extensions.gen_random_bytes(18), 'base64'), '+/=', '-_');
  insert into public.share_links (token, device_id, created_by, expires_at)
  values (v_token, p_device_id, auth.uid(), v_exp);
  return jsonb_build_object('token', v_token, 'expires_at', v_exp);
end;
$$;

-- The newest link that still works, if any.
create or replace function public.get_share_link(p_device_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object('token', l.token, 'expires_at', l.expires_at)
    from public.share_links l
   where l.device_id = p_device_id
     and l.device_id in (select public.viewable_device_ids())
     and l.revoked_at is null and l.expires_at > now()
   order by l.created_at desc
   limit 1;
$$;

create or replace function public.revoke_share_links(p_device_id uuid)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  n integer;
begin
  if p_device_id not in (select public.viewable_device_ids()) then
    raise exception 'cat not found' using errcode = 'P0002';
  end if;
  update public.share_links set revoked_at = now()
   where device_id = p_device_id and revoked_at is null;
  get diagnostics n = row_count;
  return n;
end;
$$;

-- Public: what someone with the link may see. Nothing else about the owner.
create or replace function public.get_shared_cat(p_token text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
           'name', coalesce(d.display_name, 'Cat'),
           'color', d.color,
           'lat', extensions.st_y(d.last_location::extensions.geometry),
           'lng', extensions.st_x(d.last_location::extensions.geometry),
           'accuracy_m', d.last_accuracy_m,
           'fix_at', d.last_fix_at,
           'lost_mode', d.lost_mode,
           'lost_since', d.lost_mode_since,
           'expires_at', l.expires_at)
    from public.share_links l
    join public.devices d on d.id = l.device_id
   where l.token = p_token
     and l.revoked_at is null
     and l.expires_at > now()
     and d.owner_id is not null;
$$;

-- -----------------------------------------------------------------------------
-- Power mode (collars): battery saver / normal / live
-- -----------------------------------------------------------------------------
alter table public.devices add column if not exists power_mode text not null default 'normal'
  check (power_mode in ('saver', 'normal', 'live'));

create or replace function public.devices_apply_power_mode()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.kind = 'collar' and new.power_mode is distinct from old.power_mode then
    new.report_interval_s := case new.power_mode when 'saver' then 1800 when 'live' then 300 else 900 end;
  end if;
  return new;
end;
$$;

drop trigger if exists devices_apply_power_mode on public.devices;
create trigger devices_apply_power_mode
  before update of power_mode on public.devices
  for each row execute function public.devices_apply_power_mode();

-- Traccar trackers: a power-mode change queues the interval command too.
drop trigger if exists devices_queue_tracker_command on public.devices;
create trigger devices_queue_tracker_command
  after update of lost_mode, report_interval_s, power_mode on public.devices
  for each row
  when (old.lost_mode is distinct from new.lost_mode
        or old.report_interval_s is distinct from new.report_interval_s
        or old.power_mode is distinct from new.power_mode)
  execute function public.devices_queue_tracker_command();

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
    'power_mode',  p_dev.power_mode,
    'lost_mode',   p_dev.lost_mode,
    'night_mode',  p_dev.night_mode,
    'night_start_utc_min', ((p_dev.night_start_min - tz.offset_min) % 1440 + 1440) % 1440,
    'night_end_utc_min',   ((p_dev.night_end_min   - tz.offset_min) % 1440 + 1440) % 1440,
    'night_interval_s', p_dev.night_interval_s,
    'zones', coalesce((select jsonb_agg(z.zone order by z.n) from zones z where z.n <= 4), '[]'::jsonb))
  from tz;
$$;

drop trigger if exists devices_notify_config on public.devices;
create trigger devices_notify_config
  after update of lost_mode, night_mode, night_start_min, night_end_min,
                  night_interval_s, report_interval_s, timezone, household_id, power_mode
  on public.devices
  for each row
  when (old is distinct from new)
  execute function public.devices_notify_config();

-- -----------------------------------------------------------------------------
-- Cat profile
-- -----------------------------------------------------------------------------
alter table public.devices
  add column if not exists birth_date date check (birth_date between date '1990-01-01' and current_date),
  add column if not exists breed      text check (char_length(breed) <= 60),
  add column if not exists weight_kg  numeric(4, 1) check (weight_kg between 0.5 and 15),
  add column if not exists microchip  text check (microchip ~ '^[0-9A-Za-z]{6,20}$'),
  add column if not exists vet_name   text check (char_length(vet_name) <= 80),
  add column if not exists vet_phone  text check (vet_phone ~ '^[0-9 +()-]{6,24}$'),
  add column if not exists lifestyle  text check (lifestyle in ('indoor', 'outdoor', 'both')),
  add column if not exists notes      text check (char_length(notes) <= 500);

grant update (power_mode, birth_date, breed, weight_kg, microchip, vet_name, vet_phone, lifestyle, notes)
  on public.devices to authenticated;

-- -----------------------------------------------------------------------------
-- History of any day
-- -----------------------------------------------------------------------------
create or replace function public.get_pet_track_range(p_device_id uuid, p_from timestamptz, p_to timestamptz)
returns table (recorded_at timestamptz, lat double precision, lng double precision,
               accuracy_m real, battery_pct smallint)
language sql
stable
security invoker
set search_path = ''
as $$
  select t.recorded_at,
         extensions.st_y(t.location::extensions.geometry),
         extensions.st_x(t.location::extensions.geometry),
         t.accuracy_m, t.battery_pct
    from public.telemetry t
   where t.device_id = p_device_id
     and t.recorded_at >= p_from
     and t.recorded_at < p_to
   order by t.recorded_at
   limit 5000;
$$;

-- -----------------------------------------------------------------------------
-- A new collar for the same cat: profile, zones, sitters and history move
-- over; the old collar is released (its label works again only after staff
-- reset it).
-- -----------------------------------------------------------------------------
create or replace function public.replace_collar(p_old_device_id uuid, p_device_uid text, p_claim_code text)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid uuid := auth.uid();
  v_old public.devices;
  v_new uuid;
begin
  select * into v_old from public.devices where id = p_old_device_id and owner_id = v_uid for update;
  if not found then
    raise exception 'cat not found' using errcode = 'P0002';
  end if;

  v_new := public.claim_device(p_device_uid, p_claim_code);

  update public.devices set
    display_name = v_old.display_name, color = v_old.color, photo_path = v_old.photo_path,
    household_id = v_old.household_id, night_mode = v_old.night_mode,
    night_start_min = v_old.night_start_min, night_end_min = v_old.night_end_min,
    night_interval_s = v_old.night_interval_s, timezone = v_old.timezone,
    power_mode = v_old.power_mode, birth_date = v_old.birth_date, breed = v_old.breed,
    weight_kg = v_old.weight_kg, microchip = v_old.microchip, vet_name = v_old.vet_name,
    vet_phone = v_old.vet_phone, lifestyle = v_old.lifestyle, notes = v_old.notes
  where id = v_new;

  update public.telemetry       set device_id = v_new where device_id = p_old_device_id;
  update public.geofence_events set device_id = v_new where device_id = p_old_device_id;
  update public.geofences       set device_id = v_new where device_id = p_old_device_id;
  update public.cat_sitters     set device_id = v_new where device_id = p_old_device_id;
  update public.share_links     set device_id = v_new where device_id = p_old_device_id;
  update public.notification_outbox set device_id = v_new where device_id = p_old_device_id;
  delete from public.geofence_state  where device_id = p_old_device_id;
  delete from public.device_commands where device_id = p_old_device_id;

  -- the photo now belongs to the new collar: keep release_device from touching it
  update public.devices set photo_path = null where id = p_old_device_id;
  perform public.release_device(p_old_device_id);
  return v_new;
end;
$$;

-- -----------------------------------------------------------------------------
-- Data export (GDPR art. 15/20): everything stored about you and your cats.
-- -----------------------------------------------------------------------------
create or replace function public.export_my_data()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'exported_at', now(),
    'account', (select jsonb_build_object('id', u.id, 'email', u.email, 'created_at', u.created_at)
                  from auth.users u where u.id = auth.uid()),
    'settings', public.get_my_settings(),
    'households', coalesce((
      select jsonb_agg(jsonb_build_object('name', h.name, 'role', m.role, 'joined_at', m.created_at))
        from public.household_memberships m join public.households h on h.id = m.household_id
       where m.user_id = auth.uid()), '[]'::jsonb),
    'cats', coalesce((
      select jsonb_agg(jsonb_build_object(
               'name', d.display_name, 'tracker', d.device_uid, 'kind', d.kind, 'color', d.color,
               'birth_date', d.birth_date, 'breed', d.breed, 'weight_kg', d.weight_kg,
               'microchip', d.microchip, 'vet_name', d.vet_name, 'vet_phone', d.vet_phone,
               'lifestyle', d.lifestyle, 'notes', d.notes, 'claimed_at', d.claimed_at,
               'zones', coalesce((select jsonb_agg(jsonb_build_object('name', g.name, 'created_at', g.created_at))
                                    from public.geofences g where g.device_id = d.id), '[]'::jsonb),
               'zone_events', coalesce((select jsonb_agg(jsonb_build_object('transition', e.transition, 'at', e.occurred_at) order by e.occurred_at)
                                          from public.geofence_events e where e.device_id = d.id), '[]'::jsonb),
               'positions', coalesce((select jsonb_agg(jsonb_build_object(
                                         'at', t.recorded_at,
                                         'lat', extensions.st_y(t.location::extensions.geometry),
                                         'lng', extensions.st_x(t.location::extensions.geometry),
                                         'accuracy_m', t.accuracy_m, 'battery_pct', t.battery_pct) order by t.recorded_at)
                                        from public.telemetry t where t.device_id = d.id), '[]'::jsonb)))
        from public.devices d where d.owner_id = auth.uid()), '[]'::jsonb),
    'alerts', coalesce((
      select jsonb_agg(jsonb_build_object('kind', o.kind, 'title', o.title, 'at', o.created_at) order by o.created_at)
        from public.notification_outbox o where o.owner_id = auth.uid()), '[]'::jsonb));
$$;

-- -----------------------------------------------------------------------------
-- Grants
-- -----------------------------------------------------------------------------
revoke execute on function public.list_alerts(integer, timestamptz)                  from public, anon;
revoke execute on function public.unread_alert_count()                               from public, anon;
revoke execute on function public.mark_alerts_read()                                 from public, anon;
revoke execute on function public.get_my_settings()                                  from public, anon;
revoke execute on function public.set_my_settings(jsonb)                             from public, anon;
revoke execute on function public.create_share_link(uuid, integer)                   from public, anon;
revoke execute on function public.get_share_link(uuid)                               from public, anon;
revoke execute on function public.revoke_share_links(uuid)                           from public, anon;
revoke execute on function public.get_pet_track_range(uuid, timestamptz, timestamptz) from public, anon;
revoke execute on function public.replace_collar(uuid, text, text)                   from public, anon;
revoke execute on function public.export_my_data()                                   from public, anon;
grant execute on function public.list_alerts(integer, timestamptz)                  to authenticated;
grant execute on function public.unread_alert_count()                               to authenticated;
grant execute on function public.mark_alerts_read()                                 to authenticated;
grant execute on function public.get_my_settings()                                  to authenticated;
grant execute on function public.set_my_settings(jsonb)                             to authenticated;
grant execute on function public.create_share_link(uuid, integer)                   to authenticated;
grant execute on function public.get_share_link(uuid)                               to authenticated;
grant execute on function public.revoke_share_links(uuid)                           to authenticated;
grant execute on function public.get_pet_track_range(uuid, timestamptz, timestamptz) to authenticated;
grant execute on function public.replace_collar(uuid, text, text)                   to authenticated;
grant execute on function public.export_my_data()                                   to authenticated;
revoke execute on function public.get_shared_cat(text) from public;
grant execute on function public.get_shared_cat(text) to anon, authenticated;

-- Daily purge with each owner's own retention (if pg_cron is installed).
do $$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    if exists (select 1 from cron.job where jobname = 'pet-tracker-telemetry-retention') then
      perform cron.unschedule('pet-tracker-telemetry-retention');
    end if;
    perform cron.schedule('pet-tracker-history-retention', '17 3 * * *', 'select public.purge_history();');
  end if;
end $$;
