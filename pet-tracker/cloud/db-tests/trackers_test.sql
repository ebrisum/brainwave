-- Tests for ready-made trackers, cat status and tracker health
-- (migration 20261113000700), run after zones_test.sql. Run with ./run.sh
\set ON_ERROR_STOP on
\set QUIET on
\pset tuples_only on
\pset format unaligned

create or replace function pg_temp.expect_error(p_sql text, p_label text)
returns void language plpgsql as $$
begin
  execute p_sql;
  raise exception 'FAIL: % (expected an error)', p_label;
exception
  when raise_exception then
    if sqlerrm like 'FAIL:%' then raise; end if;
    raise notice 'ok   - % (%)', p_label, sqlerrm;
  when others then
    raise notice 'ok   - % (%)', p_label, sqlerrm;
end $$;

create or replace function pg_temp.check(p_ok boolean, p_label text)
returns void language plpgsql as $$
begin
  if p_ok is not true then raise exception 'FAIL: %', p_label; end if;
  raise notice 'ok   - %', p_label;
end $$;

create or replace function pg_temp.dev(p_uid text) returns uuid
language sql security definer as $$ select id from public.devices where device_uid = p_uid $$;

grant execute on all functions in schema pg_temp to public;

-- --- registering -------------------------------------------------------------------
set role service_role;
do $$ begin
  perform set_config('test.code', public.provision_tracker('861234567890123', 'MT710', '8988228066602340000'), false);
  perform set_config('test.code2', public.provision_tracker('7364512'), false);
end $$;
select pg_temp.check(current_setting('test.code') ~ '^[A-HJ-NP-Z2-9]{12}$', 'a tracker gets a 12-character claim code');
select pg_temp.check(
  (select protocol = 'traccar' and imei = '861234567890123' and model = 'MT710' from public.devices where device_uid = '861234567890123'),
  'it is registered as a Traccar tracker with its IMEI');
select pg_temp.check((select imei is null from public.devices where device_uid = '7364512'),
                     'a non-IMEI id (Traccar Client app) also works');
select pg_temp.expect_error($$select public.provision_tracker('861234567890123')$$, 'the same tracker cannot be registered twice');
select pg_temp.check(
  (public.ingest_tracker_position('861234567890123', 52.3790, 4.8995, 10::real) ->> 'status') = 'inactive_device',
  'positions are dropped until someone claims the tracker');
select pg_temp.check((public.ingest_tracker_position('999', 52.0, 4.0, 10::real) ->> 'status') = 'unknown_device',
                     'unknown trackers are ignored');
reset role;
set role authenticated;
select pg_temp.expect_error($$select public.provision_tracker('861234567890124')$$, 'apps cannot register trackers');

set request.jwt.claim.sub = '11111111-0000-0000-0000-000000000001';
select pg_temp.expect_error($$select public.claim_device('861234567890123', 'WRONGCODE123')$$, 'a wrong claim code fails');
select public.claim_device('861234567890123', current_setting('test.code')) is not null;
select public.claim_device('7364512', current_setting('test.code2')) is not null;
reset role;

-- --- positions and "where is the cat" ---------------------------------------------------
set role service_role;
select pg_temp.check(
  (public.ingest_tracker_position('861234567890123', 52.3790, 4.8995, 10::real) ->> 'status') = 'ok',
  'a claimed tracker''s position is stored');
reset role;
select pg_temp.check((select last_battery_pct = 100 from public.devices where device_uid = '861234567890123'),
                     'a tracker without a battery level does not read as empty');
set role authenticated;
set request.jwt.claim.sub = '11111111-0000-0000-0000-000000000001';
select public.create_circle_geofence(pg_temp.dev('861234567890123'), 'Home', 52.3790, 4.8995, 40) is not null;
select pg_temp.check(
  (select zone_name = 'Home' from public.get_cat_status() where device_id = pg_temp.dev('861234567890123')),
  'at home: the status names the zone');
reset role;
set role service_role;
select public.ingest_tracker_position('861234567890123', 52.3850, 4.9100, 10::real, 80::smallint);
reset role;
set role authenticated;
set request.jwt.claim.sub = '11111111-0000-0000-0000-000000000001';
select pg_temp.check(
  (select zone_name is null and nearest_zone_name = 'Home' and nearest_zone_m between 500 and 1500
     from public.get_cat_status() where device_id = pg_temp.dev('861234567890123')),
  'out: the status says how far it is from home');
set request.jwt.claim.sub = '22222222-0000-0000-0000-000000000002';
select pg_temp.check(
  (select count(*) from public.get_cat_status() where device_id = pg_temp.dev('861234567890123')) = 0,
  'other people don''t get the status of someone else''s cat');
reset role;

-- --- tracker silent ----------------------------------------------------------------------------
set role service_role;
select pg_temp.check((public.tracker_heartbeat('861234567890123', 75::smallint) ->> 'status') = 'ok',
                     'a check-in without a position keeps the tracker alive');
reset role;
select pg_temp.check((select last_battery_pct = 75 from public.devices where device_uid = '861234567890123'),
                     'and updates the battery');
update public.devices set last_seen_at = now() - interval '4 hours' where device_uid = '861234567890123';
select public.check_silent_trackers();
select pg_temp.check(
  (select count(*) from public.notification_outbox
    where kind = 'tracker_silent' and device_id = pg_temp.dev('861234567890123')) = 1,
  'a tracker that stops checking in raises a "tracker silent" alert');
select public.check_silent_trackers();
select pg_temp.check(
  (select count(*) from public.notification_outbox
    where kind = 'tracker_silent' and device_id = pg_temp.dev('861234567890123')) = 1,
  'only once');
select pg_temp.check(
  (select count(*) from public.notification_outbox o join public.devices d on d.id = o.device_id
    where o.kind = 'tracker_silent' and d.kind = 'phone') = 0,
  'phone trackers never raise it');
set role service_role;
select public.tracker_heartbeat('861234567890123');
reset role;
update public.devices set last_seen_at = now() - interval '4 hours' where device_uid = '861234567890123';
select public.check_silent_trackers();
select pg_temp.check(
  (select count(*) from public.notification_outbox
    where kind = 'tracker_silent' and device_id = pg_temp.dev('861234567890123')) = 2,
  'after it checked in again, a new silence alerts again');

-- --- tracker health -------------------------------------------------------------------------------
set role service_role;
select public.ingest_tracker_position('7364512', 52.3790, 4.8995, 10::real, 90::smallint, now() - interval '10 hours');
select public.ingest_tracker_position('7364512', 52.3791, 4.8996, 10::real, 85::smallint, now() - interval '5 hours');
select public.ingest_tracker_position('7364512', 52.3792, 4.8997, 10::real, 81::smallint, now() - interval '1 hour');
reset role;
set role authenticated;
set request.jwt.claim.sub = '11111111-0000-0000-0000-000000000001';
select pg_temp.check(
  (select drain_pct_per_day between 20 and 28 and days_left between 2.8 and 4.2 and fixes_24h = 3 and battery_pct = 81
     from public.get_tracker_health(pg_temp.dev('7364512'))),
  'battery drain and days left come from the recent positions');
reset role;
set role service_role;
select public.ingest_tracker_position('7364512', 52.3792, 4.8997, 10::real, 100::smallint);
reset role;
set role authenticated;
set request.jwt.claim.sub = '11111111-0000-0000-0000-000000000001';
select pg_temp.check(
  (select drain_pct_per_day is null and days_left is null from public.get_tracker_health(pg_temp.dev('7364512'))),
  'right after a charge there is no estimate yet');
set request.jwt.claim.sub = '22222222-0000-0000-0000-000000000002';
select pg_temp.expect_error($$select * from public.get_tracker_health(pg_temp.dev('7364512'))$$,
                            'other people cannot see the tracker''s health');

-- --- commands to the tracker -----------------------------------------------------------------------
set request.jwt.claim.sub = '11111111-0000-0000-0000-000000000001';
select public.set_lost_mode(pg_temp.dev('861234567890123'), true);
reset role;
select pg_temp.check(
  (select (payload ->> 'seconds')::int = 30 from public.device_commands
    where device_id = pg_temp.dev('861234567890123') and sent_at is null),
  'lost mode asks the tracker to report every 30 s');
set role authenticated;
set request.jwt.claim.sub = '11111111-0000-0000-0000-000000000001';
select public.set_lost_mode(pg_temp.dev('861234567890123'), false);
reset role;
select pg_temp.check(
  (select count(*) = 1 and min((payload ->> 'seconds')::int) = 900 from public.device_commands
    where device_id = pg_temp.dev('861234567890123') and sent_at is null),
  'turning it off replaces the pending command with the normal interval');
select pg_temp.check(
  (select count(*) from public.device_commands d join public.devices v on v.id = d.device_id where v.protocol <> 'traccar') = 0,
  'our own collars get their settings over MQTT, not this queue');
\echo 'ALL TRACKER TESTS PASSED'
