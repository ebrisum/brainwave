-- =============================================================================
-- Selling trackers: recognising a label, and knowing whose tracker is whose.
--
--   * check_claim_code(): the app scans a label and asks whether the code is
--     right and the tracker still free, before anything is linked. A wrong
--     code and an unknown tracker get the same answer, so labels can't be
--     guessed.
--   * list_trackers() (service_role): every tracker with its SIM, who
--     claimed it and when, which cat and household it is, and when it last
--     checked in. For sales and support.
--   * reset_tracker() (service_role): a returned tracker loses its owner and
--     history and gets a new claim code, so the old label stops working.
-- =============================================================================

create or replace function public.check_claim_code(p_device_uid text, p_claim_code text)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_dev public.devices;
begin
  if auth.uid() is null then
    raise exception 'not authenticated' using errcode = '42501';
  end if;

  select d.* into v_dev
    from public.devices d
    join private.device_secrets s on s.device_id = d.id
   where d.device_uid = p_device_uid
     and s.claim_code_hash = extensions.crypt(p_claim_code, s.claim_code_hash);
  if not found then
    return jsonb_build_object('status', 'invalid');
  end if;

  return jsonb_build_object(
    'status', case when v_dev.owner_id = auth.uid() then 'yours'
                   when v_dev.owner_id is not null or v_dev.status <> 'provisioned' then 'taken'
                   else 'ready' end,
    'model', coalesce(v_dev.model, case when v_dev.protocol = 'pt-v1' then 'Cat Tracker collar' end),
    'kind', v_dev.kind);
end;
$$;
revoke execute on function public.check_claim_code(text, text) from public, anon;
grant execute on function public.check_claim_code(text, text) to authenticated;

-- Search matches the tracker id, the SIM's ICCID or the owner's email.
create or replace function public.list_trackers(p_search text default null)
returns table (
  device_uid      text,
  model           text,
  iccid           text,
  protocol        text,
  status          text,
  owner_email     text,
  cat_name        text,
  household_name  text,
  claimed_at      timestamptz,
  last_seen_at    timestamptz,
  battery_pct     smallint,
  registered_at   timestamptz
)
language sql
stable
security definer
set search_path = ''
as $$
  select d.device_uid, d.model, d.iccid, d.protocol, d.status::text, u.email::text,
         d.display_name, h.name, d.claimed_at, d.last_seen_at, d.last_battery_pct, d.created_at
    from public.devices d
    left join auth.users u on u.id = d.owner_id
    left join public.households h on h.id = d.household_id
   where d.kind = 'collar'
     and (p_search is null or p_search = ''
          or d.device_uid ilike '%' || p_search || '%'
          or d.iccid ilike '%' || p_search || '%'
          or u.email::text ilike '%' || p_search || '%')
   order by d.created_at desc;
$$;
revoke execute on function public.list_trackers(text) from public, anon, authenticated;
grant execute on function public.list_trackers(text) to service_role;

create or replace function public.reset_tracker(p_device_uid text)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_id   uuid;
  v_code text := public.new_claim_code();
begin
  select id into v_id from public.devices where device_uid = p_device_uid for update;
  if not found then
    raise exception 'tracker not found' using errcode = 'P0002';
  end if;

  delete from public.geofence_events where device_id = v_id;
  delete from public.geofence_state  where device_id = v_id;
  delete from public.geofences       where device_id = v_id;
  delete from public.telemetry       where device_id = v_id;
  delete from public.device_commands where device_id = v_id;
  delete from public.cat_sitters     where device_id = v_id;

  -- devices_reset_on_owner_clear wipes status / last_* fields.
  update public.devices
     set owner_id = null, household_id = null, photo_path = null, lost_mode = false, lost_mode_since = null
   where id = v_id;
  update public.devices set status = 'provisioned' where id = v_id;
  update private.device_secrets
     set claim_code_hash = extensions.crypt(v_code, extensions.gen_salt('bf', 10))
   where device_id = v_id;
  return v_code;
end;
$$;
revoke execute on function public.reset_tracker(text) from public, anon, authenticated;
grant execute on function public.reset_tracker(text) to service_role;
