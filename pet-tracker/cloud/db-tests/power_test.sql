-- Tests for the collar power features (migration 20261113000900), run after
-- sales_test.sql. Run with ./run.sh
\set ON_ERROR_STOP on
\set QUIET on
\pset tuples_only on
\pset format unaligned

create or replace function pg_temp.check(p_ok boolean, p_label text)
returns void language plpgsql as $$
begin
  if p_ok is not true then raise exception 'FAIL: %', p_label; end if;
  raise notice 'ok   - %', p_label;
end $$;

create or replace function pg_temp.config(p_uid text) returns jsonb
language sql security definer as $$ select public.device_config_json(d) from public.devices d where d.device_uid = p_uid $$;

grant execute on all functions in schema pg_temp to public;

-- A collar with our own firmware, claimed by olga (it joins her admin household).
set role service_role;
select public.provision_device('pt-111111111111111', '111111111111111', 'CLAIMCODE1234') is not null;
reset role;
set role authenticated;
set request.jwt.claim.sub = '11111111-0000-0000-0000-000000000001';
select public.claim_device('pt-111111111111111', 'CLAIMCODE1234') is not null;
reset role;

select pg_temp.check(pg_temp.config('pt-111111111111111') -> 'zones' = '[]'::jsonb,
                     'without zones the collar gets an empty list (uploads every fix, as before)');

set role authenticated;
set request.jwt.claim.sub = '11111111-0000-0000-0000-000000000001';
do $$ begin
  perform set_config('test.house',
    (select household_id::text from public.devices where device_uid = 'pt-111111111111111'), false);
  perform set_config('test.home',
    public.create_circle_geofence(null, 'Home', 52.3790, 4.8995, 40, true, current_setting('test.house')::uuid)::text, false);
end $$;
reset role;

select pg_temp.check(
  (select jsonb_array_length(z) = 1 and (z -> 0 ->> 'la')::int = 52379000 and (z -> 0 ->> 'lo')::int = 4899500
          and (z -> 0 ->> 'r')::int between 39 and 41
     from (select pg_temp.config('pt-111111111111111') -> 'zones' as z) x),
  'the household''s home goes to the collar as centre (micro-degrees) and radius');

-- Moving the cat out of the household: the household's zone no longer applies.
set role authenticated;
set request.jwt.claim.sub = '11111111-0000-0000-0000-000000000001';
select public.set_cat_household((select id from public.devices where device_uid = 'pt-111111111111111'), null);
reset role;
select pg_temp.check(pg_temp.config('pt-111111111111111') -> 'zones' = '[]'::jsonb,
                     'a private cat no longer gets the household''s zones');

-- Its own zones still go along, at most four, household zones first.
set role authenticated;
set request.jwt.claim.sub = '11111111-0000-0000-0000-000000000001';
select public.set_cat_household((select id from public.devices where device_uid = 'pt-111111111111111'),
                                current_setting('test.house')::uuid);
select count(*) = 5 from (
  select public.create_circle_geofence((select id from public.devices where device_uid = 'pt-111111111111111'),
                                       'Spot ' || i, 52.38 + i * 0.001, 4.90, 30)
    from generate_series(1, 5) i) x;
reset role;
select pg_temp.check(
  (select jsonb_array_length(z) = 4 and (z -> 0 ->> 'la')::int = 52379000
     from (select pg_temp.config('pt-111111111111111') -> 'zones' as z) x),
  'at most four zones, the household''s home first');

set role authenticated;
set request.jwt.claim.sub = '11111111-0000-0000-0000-000000000001';
select public.delete_zone(current_setting('test.home')::uuid);
reset role;
select pg_temp.check(
  (select (pg_temp.config('pt-111111111111111') -> 'zones' -> 0 ->> 'la')::int <> 52379000),
  'deleting a zone takes it off the collar''s list');

select pg_temp.check(
  has_function_privilege('telemetry_ingest', 'public.tracker_heartbeat(text, smallint)', 'execute'),
  'the MQTT ingest role can record check-ins');
select pg_temp.check(
  not has_function_privilege('telemetry_ingest', 'public.provision_tracker(text, text, text)', 'execute'),
  'and nothing more');
select pg_temp.check(
  (select silent_after_s = 18000 from public.devices where device_uid = 'pt-111111111111111'),
  'our collars: "tracker silent" after 5 h (they check in every 4 h while resting)');
set role service_role;
select public.provision_tracker('861234567890999', 'MT710') is not null;
reset role;
select pg_temp.check(
  (select silent_after_s = 10800 from public.devices where device_uid = '861234567890999'),
  'ready-made trackers: still after 3 h');
\echo 'ALL POWER TESTS PASSED'
