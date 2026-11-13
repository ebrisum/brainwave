-- =============================================================================
-- Staff: make tracker labels from the app, recorded at once.
--
--   * public.staff lists the accounts that may make labels and see who has
--     which tracker. Add yourself:
--       insert into public.staff (user_id) select id from auth.users where email = '<you>';
--   * staff_create_tracker() registers a new tracker and returns its claim
--     code for the QR label; the database records who made it and when.
--   * staff_list_trackers() / staff_reset_tracker(): the overview and
--     returns, for staff in the app (list_trackers / reset_tracker stay
--     service_role-only for scripts).
-- =============================================================================

create table public.staff (
  user_id   uuid primary key references auth.users (id) on delete cascade,
  added_at  timestamptz not null default now()
);
alter table public.staff enable row level security;
revoke all on public.staff from anon, authenticated;

alter table public.devices
  add column provisioned_by uuid references auth.users (id) on delete set null;

create or replace function public.is_staff()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (select 1 from public.staff where user_id = (select auth.uid()));
$$;
revoke execute on function public.is_staff() from public, anon;
grant execute on function public.is_staff() to authenticated;

create or replace function public.staff_create_tracker(
  p_model      text default 'Test collar',
  p_iccid      text default null,
  p_device_uid text default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid  text := nullif(trim(coalesce(p_device_uid, '')), '');
  v_code text;
begin
  if not public.is_staff() then
    raise exception 'only staff can make tracker labels' using errcode = '42501';
  end if;
  -- Without an IMEI (a test label), make up a short readable id.
  v_uid := coalesce(v_uid, 'CT-' || substr(public.new_claim_code(), 1, 6));
  if v_uid !~ '^[A-Za-z0-9_-]{3,64}$' then
    raise exception 'tracker id may only contain letters, digits, - and _' using errcode = '22023';
  end if;

  v_code := public.provision_tracker(v_uid, nullif(trim(coalesce(p_model, '')), ''), nullif(trim(coalesce(p_iccid, '')), ''));
  update public.devices set provisioned_by = auth.uid() where device_uid = v_uid;

  return jsonb_build_object('device_uid', v_uid, 'claim_code', v_code,
                            'model', nullif(trim(coalesce(p_model, '')), ''));
end;
$$;
revoke execute on function public.staff_create_tracker(text, text, text) from public, anon;
grant execute on function public.staff_create_tracker(text, text, text) to authenticated;

create or replace function public.staff_list_trackers(p_search text default null)
returns table (
  device_uid      text,
  model           text,
  iccid           text,
  status          text,
  owner_email     text,
  cat_name        text,
  household_name  text,
  claimed_at      timestamptz,
  last_seen_at    timestamptz,
  battery_pct     smallint,
  registered_at   timestamptz,
  registered_by   text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  if not public.is_staff() then
    raise exception 'only staff can see the tracker overview' using errcode = '42501';
  end if;
  return query
    select l.device_uid, l.model, l.iccid, l.status, l.owner_email, l.cat_name, l.household_name,
           l.claimed_at, l.last_seen_at, l.battery_pct, l.registered_at, u.email::text
      from public.list_trackers(p_search) l
      join public.devices d on d.device_uid = l.device_uid
      left join auth.users u on u.id = d.provisioned_by
     order by l.registered_at desc;
end;
$$;
revoke execute on function public.staff_list_trackers(text) from public, anon;
grant execute on function public.staff_list_trackers(text) to authenticated;

create or replace function public.staff_reset_tracker(p_device_uid text)
returns text
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not public.is_staff() then
    raise exception 'only staff can reset trackers' using errcode = '42501';
  end if;
  return public.reset_tracker(p_device_uid);
end;
$$;
revoke execute on function public.staff_reset_tracker(text) from public, anon;
grant execute on function public.staff_reset_tracker(text) to authenticated;
