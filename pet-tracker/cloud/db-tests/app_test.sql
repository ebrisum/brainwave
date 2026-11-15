-- Tests for the complete app (migration 20261115001200), run after demo_test.sql.
-- Uses the demo account (Minoes + Pluis in "Demo home") and sam (3333) as an outsider.
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

select set_config('test.demo', (select id::text from auth.users where email = 'demo@example.com'), false);
select set_config('test.minoes', (select id::text from public.devices where device_uid = 'DEMO-MINOES'), false);
select set_config('test.pluis', (select id::text from public.devices where device_uid = 'DEMO-PLUIS'), false);

-- --------------------------------------------------------------------------
-- Settings
-- --------------------------------------------------------------------------
set role authenticated;
select set_config('request.jwt.claim.sub', current_setting('test.demo'), false);
select pg_temp.check((public.get_my_settings() ->> 'lang') = 'en' and (public.get_my_settings() ->> 'history_days')::int = 180,
                     'settings have sensible defaults before anything is saved');
select pg_temp.check(
  (public.set_my_settings('{"lang":"nl","notify_zone_enter":false,"history_days":90}') ->> 'lang') = 'nl',
  'settings can be changed');
select pg_temp.check((public.get_my_settings() ->> 'notify_zone_enter')::boolean = false
                     and (public.get_my_settings() ->> 'notify_zone_exit')::boolean = true,
                     'only the given keys change');
select pg_temp.expect_error($$select public.set_my_settings('{"lang":"fr"}')$$, 'unknown languages are refused');
select pg_temp.expect_error($$select public.set_my_settings('{"history_days":7}')$$, 'and odd retention periods');
select pg_temp.expect_error($$select * from public.user_settings$$, 'the settings table itself is closed');

-- --------------------------------------------------------------------------
-- Alerts inbox
-- --------------------------------------------------------------------------
reset role;
update public.devices set last_battery_pct = 15 where id = current_setting('test.pluis')::uuid;
set role authenticated;
select set_config('request.jwt.claim.sub', current_setting('test.demo'), false);
select pg_temp.check(
  (select meta ->> 'battery' = '15' and unread from public.list_alerts(10) where kind = 'low_battery' limit 1),
  'a low battery shows in the inbox, unread, with the battery level');
select pg_temp.check(
  (select count(*) >= 2 from public.list_alerts(50) where kind in ('zone_exit', 'zone_enter')),
  'zone alerts from the seed are in the inbox');
select pg_temp.check(public.unread_alert_count() > 0, 'there are unread alerts');
select public.mark_alerts_read();
select pg_temp.check(public.unread_alert_count() = 0, 'opening the inbox marks them read');

select public.set_lost_mode(current_setting('test.minoes')::uuid, true);
select public.set_lost_mode(current_setting('test.minoes')::uuid, false);
select pg_temp.check(
  (select count(*) = 1 from public.list_alerts(10) where kind = 'found' and unread),
  'switching lost mode off again tells everyone the cat is found');

select set_config('request.jwt.claim.sub', '33333333-0000-0000-0000-000000000003', false);
select pg_temp.check(
  not exists (select 1 from public.list_alerts(200) where device_id in (current_setting('test.minoes')::uuid, current_setting('test.pluis')::uuid)),
  'others never see these alerts');
reset role;

-- --------------------------------------------------------------------------
-- Push targets honour settings and quiet hours
-- --------------------------------------------------------------------------
insert into public.push_tokens (user_id, token, platform)
values (current_setting('test.demo')::uuid, 'ExponentPushToken[demo]', 'ios')
on conflict do nothing;
select pg_temp.check(
  (select count(*) = 0 from public.push_targets(current_setting('test.demo')::uuid, current_setting('test.minoes')::uuid, 'zone_enter')),
  '"back home" alerts are off for the demo account, so no push');
select pg_temp.check(
  (select lang = 'nl' from public.push_targets(current_setting('test.demo')::uuid, current_setting('test.minoes')::uuid, 'zone_exit')),
  '"left home" still goes out, in Dutch');
update public.user_settings set quiet_enabled = true, quiet_start_min = 0, quiet_end_min = 1439, timezone = 'UTC'
 where user_id = current_setting('test.demo')::uuid;
select pg_temp.check(
  (select count(*) = 0 from public.push_targets(current_setting('test.demo')::uuid, current_setting('test.minoes')::uuid, 'zone_exit')),
  'quiet hours mute alerts');
select pg_temp.check(
  (select count(*) = 1 from public.push_targets(current_setting('test.demo')::uuid, current_setting('test.minoes')::uuid, 'lost_mode')),
  'but never lost mode');
select pg_temp.check(public.in_quiet_hours(1380::smallint, 420::smallint, 'UTC', timestamptz '2026-11-15 23:30+00')
                     and not public.in_quiet_hours(1380::smallint, 420::smallint, 'UTC', timestamptz '2026-11-15 12:00+00'),
                     'quiet hours work across midnight');
update public.user_settings set quiet_enabled = false where user_id = current_setting('test.demo')::uuid;

-- --------------------------------------------------------------------------
-- Live share links
-- --------------------------------------------------------------------------
set role authenticated;
select set_config('request.jwt.claim.sub', current_setting('test.demo'), false);
select set_config('test.share', public.create_share_link(current_setting('test.minoes')::uuid, 24) ->> 'token', false);
select pg_temp.check(length(current_setting('test.share')) >= 20, 'a share link has a long random token');
select pg_temp.check((public.get_share_link(current_setting('test.minoes')::uuid) ->> 'token') = current_setting('test.share'),
                     'the app finds the active link again');
select set_config('request.jwt.claim.sub', '33333333-0000-0000-0000-000000000003', false);
select pg_temp.expect_error(format($$select public.create_share_link(%L::uuid)$$, current_setting('test.minoes')), 'outsiders cannot share someone''s cat');
reset role;

set role anon;
select pg_temp.check(
  (public.get_shared_cat(current_setting('test.share')) ->> 'name') = 'Minoes'
  and (public.get_shared_cat(current_setting('test.share')) ->> 'lat') is not null,
  'anyone with the link sees the cat''s name and position');
select pg_temp.check(
  not (public.get_shared_cat(current_setting('test.share')) ? 'owner_id')
  and not (public.get_shared_cat(current_setting('test.share')) ? 'device_uid'),
  'and nothing about the owner or the tracker');
select pg_temp.check(public.get_shared_cat('not-a-real-token-123456') is null, 'a wrong token shows nothing');
select pg_temp.expect_error($$select * from public.share_links$$, 'the links table is closed');
select pg_temp.expect_error($$select public.list_alerts()$$, 'anonymous visitors get nothing else');
reset role;

set role authenticated;
select set_config('request.jwt.claim.sub', current_setting('test.demo'), false);
select pg_temp.check(public.revoke_share_links(current_setting('test.minoes')::uuid) = 1, 'the owner can stop the link');
reset role;
set role anon;
select pg_temp.check(public.get_shared_cat(current_setting('test.share')) is null, 'a stopped link shows nothing');
reset role;
update public.share_links set revoked_at = null, expires_at = now() - interval '1 minute' where token = current_setting('test.share');
set role anon;
select pg_temp.check(public.get_shared_cat(current_setting('test.share')) is null, 'neither does an expired one');
reset role;

-- --------------------------------------------------------------------------
-- Power mode
-- --------------------------------------------------------------------------
set role authenticated;
select set_config('request.jwt.claim.sub', current_setting('test.demo'), false);
update public.devices set power_mode = 'saver' where id = current_setting('test.pluis')::uuid;
reset role;
select pg_temp.check((select report_interval_s = 1800 from public.devices where id = current_setting('test.pluis')::uuid),
                     'battery saver reports every 30 minutes');
select pg_temp.check(
  (select (payload ->> 'seconds')::int = 1800 from public.device_commands
    where device_id = current_setting('test.pluis')::uuid and sent_at is null order by id desc limit 1),
  'and a Traccar tracker gets the new interval as a command');
select pg_temp.check(
  (select public.device_config_json(d) ->> 'power_mode' = 'saver' from public.devices d where id = current_setting('test.pluis')::uuid),
  'our own collars get the power mode in their config');
select pg_temp.expect_error(format($$update public.devices set power_mode = 'turbo' where id = %L$$, current_setting('test.pluis')), 'unknown power modes are refused');

-- --------------------------------------------------------------------------
-- Cat profile
-- --------------------------------------------------------------------------
set role authenticated;
select set_config('request.jwt.claim.sub', current_setting('test.demo'), false);
update public.devices
   set birth_date = '2021-04-02', breed = 'European shorthair', weight_kg = 4.2, microchip = '528140000123456',
       vet_name = 'Dierenkliniek Centrum', vet_phone = '+31 20 123 4567', lifestyle = 'outdoor'
 where id = current_setting('test.minoes')::uuid;
select pg_temp.check((select weight_kg = 4.2 and lifestyle = 'outdoor' from public.devices where id = current_setting('test.minoes')::uuid),
                     'the owner fills in the cat''s profile');
select pg_temp.expect_error(format($$update public.devices set weight_kg = 40 where id = %L$$, current_setting('test.minoes')), 'impossible weights are refused');
select pg_temp.expect_error(format($$update public.devices set microchip = 'abc' where id = %L$$, current_setting('test.minoes')), 'and malformed chip numbers');
select set_config('request.jwt.claim.sub', '33333333-0000-0000-0000-000000000003', false);
update public.devices set breed = 'hacked' where id = current_setting('test.minoes')::uuid;
reset role;
select pg_temp.check((select breed = 'European shorthair' from public.devices where id = current_setting('test.minoes')::uuid),
                     'others cannot change it');

-- --------------------------------------------------------------------------
-- History of a day
-- --------------------------------------------------------------------------
set role authenticated;
select set_config('request.jwt.claim.sub', current_setting('test.demo'), false);
select pg_temp.check(
  (select count(*) > 0 from public.get_pet_track_range(current_setting('test.minoes')::uuid, now() - interval '1 day', now() + interval '1 minute')),
  'a day''s route can be fetched');
select pg_temp.check(
  (select count(*) = 0 from public.get_pet_track_range(current_setting('test.minoes')::uuid, now() - interval '30 days', now() - interval '29 days')),
  'an empty day is empty');
reset role;

-- --------------------------------------------------------------------------
-- Data export
-- --------------------------------------------------------------------------
set role authenticated;
select set_config('request.jwt.claim.sub', current_setting('test.demo'), false);
select pg_temp.check(
  (select jsonb_array_length(x -> 'cats') = 2
      and (x -> 'account' ->> 'email') = 'demo@example.com'
      and jsonb_array_length((x -> 'cats') -> 0 -> 'positions') > 0
     from (select public.export_my_data() as x) e),
  'the export has the account, both cats and their positions');
reset role;

-- --------------------------------------------------------------------------
-- New collar for the same cat
-- --------------------------------------------------------------------------
select set_config('test.swapcode', public.provision_tracker('TEST-SWAP-01', 'Demo collar'), false);
select set_config('test.points', (select count(*)::text from public.telemetry where device_id = current_setting('test.minoes')::uuid), false);
set role authenticated;
select set_config('request.jwt.claim.sub', current_setting('test.demo'), false);
select pg_temp.expect_error(format($$select public.replace_collar(%L::uuid, 'TEST-SWAP-01', 'WRONGCODE234')$$, current_setting('test.minoes')),
                            'a wrong code on the new collar is refused');
select set_config('test.newid', public.replace_collar(current_setting('test.minoes')::uuid, 'TEST-SWAP-01', current_setting('test.swapcode'))::text, false);
select pg_temp.check(
  (select display_name = 'Minoes' and breed = 'European shorthair' and household_id is not null
     from public.devices where id = current_setting('test.newid')::uuid),
  'the new collar is Minoes, with her profile and household');
reset role;
select pg_temp.check(
  (select count(*)::text = current_setting('test.points') from public.telemetry where device_id = current_setting('test.newid')::uuid),
  'and her whole history');
select pg_temp.check((select owner_id is null from public.devices where device_uid = 'DEMO-MINOES'), 'the old collar is released');

-- --------------------------------------------------------------------------
-- Retention follows each owner's setting
-- --------------------------------------------------------------------------
insert into public.telemetry (device_id, owner_id, recorded_at, location, accuracy_m, battery_pct)
values (current_setting('test.pluis')::uuid, current_setting('test.demo')::uuid, now() - interval '100 days',
        extensions.st_setsrid(extensions.st_makepoint(4.883, 52.374), 4326)::extensions.geography, 10, 80),
       (current_setting('test.pluis')::uuid, current_setting('test.demo')::uuid, now() - interval '60 days',
        extensions.st_setsrid(extensions.st_makepoint(4.883, 52.374), 4326)::extensions.geography, 10, 80);
select public.purge_history();
select pg_temp.check(
  (select count(*) = 1 from public.telemetry
    where device_id = current_setting('test.pluis')::uuid and recorded_at < now() - interval '30 days'),
  'with 90 days chosen, older positions are deleted and newer ones kept');

\echo 'ALL APP TESTS PASSED'
