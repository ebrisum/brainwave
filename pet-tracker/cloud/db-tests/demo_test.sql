-- Runs the demo-account seed (cloud/supabase/seed/demo_account.sql) and
-- checks the app would show it as intended. Run after staff_test.sql.
\set ON_ERROR_STOP on
\set QUIET on
\pset tuples_only on
\pset format unaligned

\i ../supabase/seed/demo_account.sql

create or replace function pg_temp.check(p_ok boolean, p_label text)
returns void language plpgsql as $$
begin
  if p_ok is not true then raise exception 'FAIL: %', p_label; end if;
  raise notice 'ok   - %', p_label;
end $$;
grant execute on all functions in schema pg_temp to public;

select pg_temp.check(
  (select email_confirmed_at is not null and encrypted_password = extensions.crypt('CHANGE-ME-demo-password', encrypted_password)
     from auth.users where email = 'demo@example.com'),
  'the demo login exists, confirmed, with its password');
select set_config('test.demo', (select id::text from auth.users where email = 'demo@example.com'), false);

set role authenticated;
select set_config('request.jwt.claim.sub', current_setting('test.demo'), false);
select pg_temp.check((select count(*) = 2 from public.devices), 'the demo account has two cats');
select pg_temp.check(
  (select bool_and(zone_name = 'Home') from public.get_cat_status()),
  'both are at home now');
select pg_temp.check(
  (select count(*) filter (where transition = 'exit') = 1 and count(*) filter (where transition = 'enter') = 1
     from public.geofence_events e join public.devices d on d.id = e.device_id where d.display_name = 'Minoes'),
  'Minoes left home and came back today');
select pg_temp.check(
  (select resting from public.get_tracker_health((select id from public.devices where display_name = 'Pluis'))),
  'Pluis shows as resting');
select pg_temp.check(
  (select count(*) > 20 from public.get_pet_track((select id from public.devices where display_name = 'Minoes'), now() - interval '1 day')),
  'Minoes has a route for today');
reset role;
\echo 'ALL DEMO TESTS PASSED'
