-- Tests for staff label making (migration 20261113001100), run after resting_test.sql.
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

-- sam (3333) is not staff; mark (2222) becomes staff.
set role authenticated;
set request.jwt.claim.sub = '33333333-0000-0000-0000-000000000003';
select pg_temp.check(not public.is_staff(), 'customers are not staff');
select pg_temp.expect_error($$select public.staff_create_tracker()$$, 'customers cannot make labels');
select pg_temp.expect_error($$select * from public.staff_list_trackers()$$, 'or see the tracker overview');
select pg_temp.expect_error($$insert into public.staff (user_id) values (auth.uid())$$, 'or make themselves staff');
reset role;

insert into public.staff (user_id) values ('22222222-0000-0000-0000-000000000002');

set role authenticated;
set request.jwt.claim.sub = '22222222-0000-0000-0000-000000000002';
select pg_temp.check(public.is_staff(), 'staff are recognised');
do $$ begin
  perform set_config('test.label', public.staff_create_tracker('Test collar')::text, false);
  perform set_config('test.imei', public.staff_create_tracker('MT710', '8988228066602341111', '861234567890555')::text, false);
end $$;
select pg_temp.check((current_setting('test.label')::jsonb ->> 'device_uid') ~ '^CT-[A-HJ-NP-Z2-9]{6}$',
                     'a test label gets a short readable id');
select pg_temp.check((current_setting('test.label')::jsonb ->> 'claim_code') ~ '^[A-HJ-NP-Z2-9]{12}$',
                     'and a 12-character claim code');
select pg_temp.check(
  (select registered_by = 'mark@example.nl' and model = 'MT710' and iccid = '8988228066602341111' and owner_email is null
     from public.staff_list_trackers('861234567890555')),
  'the overview records who made the label, the model and the SIM');
select pg_temp.expect_error($$select public.staff_create_tracker('x', null, 'bad id!')$$, 'tracker ids are checked');

-- a customer scans the label: the overview shows them as the owner
set request.jwt.claim.sub = '33333333-0000-0000-0000-000000000003';
select pg_temp.check(
  (public.check_claim_code(current_setting('test.label')::jsonb ->> 'device_uid',
                           current_setting('test.label')::jsonb ->> 'claim_code') ->> 'status') = 'ready',
  'the label is recognised in the app');
select public.claim_device(current_setting('test.label')::jsonb ->> 'device_uid',
                           current_setting('test.label')::jsonb ->> 'claim_code') is not null;
set request.jwt.claim.sub = '22222222-0000-0000-0000-000000000002';
select pg_temp.check(
  (select owner_email = 'sam@example.nl' and claimed_at is not null
     from public.staff_list_trackers(current_setting('test.label')::jsonb ->> 'device_uid')),
  'after scanning, the overview shows who has it and since when');

-- returns
do $$ begin
  perform set_config('test.newcode', public.staff_reset_tracker(current_setting('test.label')::jsonb ->> 'device_uid'), false);
end $$;
select pg_temp.check(
  (select owner_email is null from public.staff_list_trackers(current_setting('test.label')::jsonb ->> 'device_uid')),
  'staff can take back a returned tracker');
reset role;
\echo 'ALL STAFF TESTS PASSED'
