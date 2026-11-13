-- =============================================================================
-- Demo account with ready-made data, for showing the app.
-- Paste all of this in Supabase -> SQL Editor -> Run (once).
--
--   Log in:  demo@example.com  /  the password in v_password below
--
-- Creates the login (confirmed, no e-mail needed), a household "Demo home"
-- with a home zone, and two cats on demo trackers:
--   Minoes - went out for a walk today and came back (route, heatmap,
--            "left / back home", activity)
--   Pluis  - at home all day, "Resting"
-- Change v_password before running if you share this file.
-- =============================================================================
begin;

do $$
declare
  v_email    text := 'demo@example.com';
  v_password text := 'CHANGE-ME-demo-password';
  v_user     uuid := gen_random_uuid();
  v_home     uuid;
  v_code     text;
  v_lat0     double precision := 52.3740;  -- home (Amsterdam, Jordaan)
  v_lng0     double precision := 4.8830;
  v_k        double precision := 111320 * cos(radians(52.3740));
  v_t0       timestamptz := date_trunc('minute', now()) - interval '6 hours';
  v_d        double precision;
  v_b        double precision;
begin
  if exists (select 1 from auth.users where email = v_email) then
    raise exception 'The demo account % already exists', v_email;
  end if;

  -- 1. The login (same shape as a confirmed e-mail sign-up).
  insert into auth.users (instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,
                          raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
                          confirmation_token, email_change, email_change_token_new, recovery_token)
  values ('00000000-0000-0000-0000-000000000000', v_user, 'authenticated', 'authenticated', v_email,
          extensions.crypt(v_password, extensions.gen_salt('bf')), now(),
          '{"provider":"email","providers":["email"]}', '{}', now(), now(), '', '', '', '');
  insert into auth.identities (id, user_id, provider_id, identity_data, provider, last_sign_in_at, created_at, updated_at)
  values (gen_random_uuid(), v_user, v_user::text,
          jsonb_build_object('sub', v_user::text, 'email', v_email, 'email_verified', true),
          'email', now(), now(), now());

  -- 2. Act as the demo user for the app's own functions.
  perform set_config('request.jwt.claim.sub', v_user::text, true);
  v_home := public.create_household('Demo home');

  v_code := public.provision_tracker('DEMO-MINOES', 'Demo collar');
  perform public.claim_device('DEMO-MINOES', v_code);
  v_code := public.provision_tracker('DEMO-PLUIS', 'Demo collar');
  perform public.claim_device('DEMO-PLUIS', v_code);
  update public.devices set display_name = 'Minoes', color = '#F59E0B' where device_uid = 'DEMO-MINOES';
  update public.devices set display_name = 'Pluis',  color = '#EC4899' where device_uid = 'DEMO-PLUIS';

  -- 3. Both at home this morning, then the household's home zone.
  perform public.ingest_tracker_position('DEMO-MINOES', v_lat0 + 0.00003, v_lng0 - 0.00002, 9::real, 94::smallint, v_t0);
  perform public.ingest_tracker_position('DEMO-PLUIS',  v_lat0 - 0.00004, v_lng0 + 0.00003, 11::real, 88::smallint, v_t0);
  perform public.create_circle_geofence(null, 'Home', v_lat0, v_lng0, 40, true, v_home);

  -- 4. Minoes: a 2.5 h loop through the neighbourhood (up to ~350 m away),
  --    every 5 minutes, back home 2 hours ago; the battery slowly drops.
  for i in 1..30 loop
    v_d := 350 * sin(pi() * i / 30.0);
    v_b := radians(30 + 120.0 * i / 30.0);
    perform public.ingest_tracker_position(
      'DEMO-MINOES',
      v_lat0 + v_d * cos(v_b) / 111320 + (random() - 0.5) * 0.00004,
      v_lng0 + v_d * sin(v_b) / v_k + (random() - 0.5) * 0.00006,
      (6 + random() * 8)::real,
      (93 - i / 6)::smallint,
      v_t0 + interval '30 minutes' + i * interval '5 minutes');
  end loop;
  perform public.ingest_tracker_position('DEMO-MINOES', v_lat0 + 0.00002, v_lng0 + 0.00001, 8::real, 87::smallint,
                                          now() - interval '20 minutes');

  -- 5. Pluis: dozing at home, a position every hour; now "Resting".
  for i in 1..5 loop
    perform public.ingest_tracker_position('DEMO-PLUIS', v_lat0 - 0.00004 + (random() - 0.5) * 0.00004,
                                            v_lng0 + 0.00003 + (random() - 0.5) * 0.00005, (8 + random() * 10)::real,
                                            (88 - i)::smallint, v_t0 + i * interval '1 hour');
  end loop;
  perform public.tracker_heartbeat('DEMO-PLUIS', 83::smallint, 'still');

  raise notice 'Demo account ready: % (household %)', v_email, v_home;
end;
$$;

commit;
