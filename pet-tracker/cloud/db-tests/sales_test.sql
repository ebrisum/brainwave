-- Tests for recognising labels and the tracker overview (migration
-- 20261113000800), run after trackers_test.sql. Run with ./run.sh
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

grant execute on all functions in schema pg_temp to public;

-- olga claimed MT710 861234567890123 (code in trackers_test, unknown here) and 7364512.
set role service_role;
do $$ begin perform set_config('test.code', public.provision_tracker('TEST-0001', 'MT710', '8988228066602349999'), false); end $$;
reset role;

-- --- recognising a scanned label -------------------------------------------------------
set role authenticated;
set request.jwt.claim.sub = '33333333-0000-0000-0000-000000000003';
select pg_temp.check(
  (select r ->> 'status' = 'ready' and r ->> 'model' = 'MT710'
     from (select public.check_claim_code('TEST-0001', current_setting('test.code')) as r) x),
  'a new tracker with the right code is recognised: ready, with its model');
select pg_temp.check((public.check_claim_code('TEST-0001', 'WRONGCODE234') ->> 'status') = 'invalid',
                     'a wrong code is invalid');
select pg_temp.check(public.check_claim_code('NOPE-0000', current_setting('test.code')) = '{"status": "invalid"}'::jsonb,
                     'an unknown tracker gets exactly the same answer (labels cannot be guessed)');
select pg_temp.check((select count(*) from public.devices where device_uid = 'TEST-0001') = 0,
                     'checking links nothing: the tracker is not in sam''s list yet');
select public.claim_device('TEST-0001', current_setting('test.code')) is not null;
select pg_temp.check((public.check_claim_code('TEST-0001', current_setting('test.code')) ->> 'status') = 'yours',
                     'after claiming, the same label says it is yours');
set request.jwt.claim.sub = '22222222-0000-0000-0000-000000000002';
select pg_temp.check((public.check_claim_code('TEST-0001', current_setting('test.code')) ->> 'status') = 'taken',
                     'for anyone else it is taken');
reset role;
set role anon;
select pg_temp.expect_error($$select public.check_claim_code('TEST-0001', 'X')$$, 'not without an account');
reset role;

-- --- who has which tracker --------------------------------------------------------------
set role service_role;
select pg_temp.check(
  (select owner_email = 'sam@example.nl' and iccid = '8988228066602349999' and claimed_at is not null
     from public.list_trackers('TEST-0001')),
  'the overview shows the tracker, its SIM, who claimed it and when');
select pg_temp.check((select count(*) from public.list_trackers('8988228066602349999')) = 1, 'search by SIM (ICCID)');
select pg_temp.check((select count(*) >= 2 from public.list_trackers('olga@')), 'search by owner email');
select pg_temp.check((select count(*) from public.list_trackers() where device_uid like 'ph-%') = 0, 'phone trackers are not listed');
reset role;
set role authenticated;
set request.jwt.claim.sub = '33333333-0000-0000-0000-000000000003';
select pg_temp.expect_error($$select * from public.list_trackers()$$, 'customers cannot list trackers');
reset role;

-- --- returns ----------------------------------------------------------------------------
set role service_role;
select public.ingest_tracker_position('TEST-0001', 52.3790, 4.8995, 10::real, 70::smallint);
do $$ begin perform set_config('test.newcode', public.reset_tracker('TEST-0001'), false); end $$;
select pg_temp.check(
  (select owner_email is null and status = 'provisioned' and cat_name is null from public.list_trackers('TEST-0001')),
  'a returned tracker has no owner any more');
reset role;
select pg_temp.check((select count(*) from public.telemetry t join public.devices d on d.id = t.device_id where d.device_uid = 'TEST-0001') = 0,
                     'and none of the previous owner''s history');
set role authenticated;
set request.jwt.claim.sub = '33333333-0000-0000-0000-000000000003';
select pg_temp.check((public.check_claim_code('TEST-0001', current_setting('test.code')) ->> 'status') = 'invalid',
                     'the old label stops working');
set request.jwt.claim.sub = '22222222-0000-0000-0000-000000000002';
select pg_temp.check((public.check_claim_code('TEST-0001', current_setting('test.newcode')) ->> 'status') = 'ready',
                     'the new label works for the next customer');
select public.claim_device('TEST-0001', current_setting('test.newcode')) is not null;
reset role;
\echo 'ALL SALES TESTS PASSED'
