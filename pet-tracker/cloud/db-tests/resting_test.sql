-- Tests for the "resting" status (migration 20261113001000), run after power_test.sql.
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
grant execute on all functions in schema pg_temp to public;

-- olga's own-firmware collar pt-111111111111111 from power_test.sql
set role telemetry_ingest;
select public.ingest_telemetry('pt-111111111111111', 52.3790, 4.8995, 8::real, 80::smallint, null, now() - interval '2 hours');
select (public.tracker_heartbeat('pt-111111111111111', 79::smallint, 'still') ->> 'status') = 'ok';
reset role;

set role authenticated;
set request.jwt.claim.sub = '11111111-0000-0000-0000-000000000001';
select pg_temp.check(
  (select resting and not silent and battery_pct = 79
     from public.get_tracker_health((select id from public.devices where device_uid = 'pt-111111111111111'))),
  'a "still" check-in shows the collar as resting (not silent)');
reset role;

set role telemetry_ingest;
select public.ingest_telemetry('pt-111111111111111', 52.3850, 4.9100, 8::real, 78::smallint, null, now());
reset role;
set role authenticated;
set request.jwt.claim.sub = '11111111-0000-0000-0000-000000000001';
select pg_temp.check(
  (select not resting from public.get_tracker_health((select id from public.devices where device_uid = 'pt-111111111111111'))),
  'a new position ends "resting"');
reset role;

set role telemetry_ingest;
select public.tracker_heartbeat('pt-111111111111111', 78::smallint, 'no_sky');
reset role;
set role authenticated;
set request.jwt.claim.sub = '11111111-0000-0000-0000-000000000001';
select pg_temp.check(
  (select not resting from public.get_tracker_health((select id from public.devices where device_uid = 'pt-111111111111111'))),
  'a check-in without a fix for another reason (no sky) is not "resting"');
reset role;

update public.devices set resting = true, last_seen_at = now() - interval '6 hours' where device_uid = 'pt-111111111111111';
set role authenticated;
set request.jwt.claim.sub = '11111111-0000-0000-0000-000000000001';
select pg_temp.check(
  (select silent and not resting from public.get_tracker_health((select id from public.devices where device_uid = 'pt-111111111111111'))),
  'a resting collar that misses its check-ins becomes silent, not resting');
reset role;
\echo 'ALL RESTING TESTS PASSED'
