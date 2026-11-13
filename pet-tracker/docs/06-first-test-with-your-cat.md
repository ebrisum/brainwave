# First test with your own cat

Everything you need to go from "the app works on my phone" to "a tracker on
the cat reports to the app". Do the steps in order; each one ends with a
check, so you know it works before you go on.

What you need: your Supabase project, your Expo account, a Google/Firebase
account (for Android push), a small server with a domain name (for Traccar),
1NCE SIMs and a Mictrack MT710. Steps 1–6 work before the MT710 arrives.

---

## 1. Database

1. Supabase → **Database → Extensions** → enable **pg_cron** (needed for the
   "tracker silent" check every 15 minutes).
2. Supabase → **SQL Editor** → paste all of `supabase-update-700.sql` → **Run**.

✔ Check: `select public.check_silent_trackers();` runs and returns `0`.
If you enabled pg_cron only after step 2, also run once:
`select cron.schedule('pet-tracker-silent-trackers', '*/15 * * * *', 'select public.check_silent_trackers();');`

## 2. Edge Functions

On your computer, in the `pet-tracker` folder:

```bash
npx supabase login
npx supabase link --project-ref <your project ref>   # the part before .supabase.co
npx supabase functions deploy send-push
npx supabase functions deploy traccar-ingest --no-verify-jwt
npx supabase functions deploy tracker-commands
```

Secrets (make the forward secret with `openssl rand -hex 24`, or any 48
random letters and digits; keep it, Traccar needs the same value):

```bash
npx supabase secrets set TRACCAR_FORWARD_SECRET=<48 random characters>
npx supabase secrets set TRACCAR_URL=https://traccar.<your domain> TRACCAR_USER=<traccar admin email> TRACCAR_PASSWORD=<traccar admin password>
```

✔ Check: Supabase → Edge Functions lists all three.

## 3. Database webhooks (push alerts and tracker commands)

Supabase → **Database → Webhooks → Create a new hook**, twice:

| Name | Table | Events | Type | Function |
|---|---|---|---|---|
| send-push | `notification_outbox` | Insert | Supabase Edge Functions | `send-push` |
| tracker-commands | `device_commands` | Insert | Supabase Edge Functions | `tracker-commands` |

## 4. Installable Android app with push alerts

Expo Go cannot receive push alerts, so you install your own build once.

1. In `app/.env` set your own package name, e.g. `ANDROID_PACKAGE=eu.<yourname>.cattracker`.
2. [Firebase console](https://console.firebase.google.com) → new project →
   **Add app → Android** with that package name → download
   `google-services.json` into the `app` folder (it is not secret, but keep it
   out of public repos).
3. Firebase → Project settings → **Service accounts → Generate new private key**
   (a JSON file; this one *is* secret). Then:
   ```bash
   cd app
   npx eas credentials      # Android → preview → Push Notifications: FCM V1 → upload that JSON
   npx eas build -p android --profile preview
   ```
4. Open the link EAS prints on your phone and install the APK.
5. In the app: Settings → **Turn on alerts**.

✔ Check: add a home zone, walk out with the phone-as-tracker cat: a
"left Home" push arrives with the app closed.

## 5. Traccar server

A small VPS is enough (e.g. 2 GB RAM, Ubuntu). Point a DNS name at it, e.g.
`traccar.<your domain>`.

```bash
# on the server
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp \
  && sudo ufw allow 5030 && sudo ufw allow 5055/tcp && sudo ufw enable
# copy the cloud/traccar folder to the server, then in it:
cp .env.example .env     # fill in TRACCAR_DOMAIN, SUPABASE_URL, TRACCAR_FORWARD_SECRET
./configure.sh
sudo docker compose up -d
```

Open `https://traccar.<your domain>`, create the admin account (use the same
email/password as `TRACCAR_USER` / `TRACCAR_PASSWORD` in step 2).

✔ Check: the Traccar web page loads over https.

## 6. Dry run with the Traccar Client app (no tracker needed)

The free **Traccar Client** app (Android/iOS) turns a second phone into a
stand-in tracker.

1. In Traccar Client: server URL `http://<server ip>:5055`, note the
   **device identifier** it shows, interval 60 s, start the service.
2. Register it (on your computer, never commit the service role key):
   ```bash
   cd cloud/provisioning && npm install
   echo "<device identifier>,TraccarClient" > trackers.csv
   SUPABASE_URL=https://<ref>.supabase.co SUPABASE_SERVICE_ROLE_KEY=<service role key> \
     node provision.mjs trackers.csv out
   ```
   `out/labels.html` shows the claim code (and a QR code).
3. In the app: **Add cat → GPS collar** → collar ID + code (or scan the QR
   code with the installed app).

If Traccar shows the device but the app doesn't, look at Supabase → Edge
Functions → traccar-ingest → Logs. Lots of `401` means the secret header
doesn't arrive: in `traccar.local.xml` change the `forward.url` to end in
`traccar-ingest?key=<the same secret>` and restart (`sudo docker compose restart traccar`).

✔ Check: the cat appears and moves; Traccar's web page shows the device;
"At Home / Out" and the Today card work; the Collar card shows check-ins.
To test the "tracker silent" alert quickly: stop Traccar Client and run
`update devices set silent_after_s = 1800 where device_uid = '<id>';`, then wait
30–45 minutes.

## 7. The Mictrack MT710

1. Put the 1NCE SIM in (activate it in the 1NCE portal).
2. Send the setup by SMS from the 1NCE portal, using the commands from
   Mictrack's MT710 manual (fill in the exact syntax here once you have it):

   | Setting | Value | MT710 command |
   |---|---|---|
   | APN | `iot.1nce.net` | *from the manual* |
   | Server | `<server ip or domain>`, port `5030`, TCP | *from the manual* |
   | Interval | 300 s | *from the manual* |

3. Register it with its IMEI (on the box/label) and the SIM's ICCID:
   `861234567890123,MT710,8988…` in `trackers.csv`, run `provision.mjs`, claim it in the app.
4. Lost mode: put the MT710's interval command in a secret, with `{seconds}`
   (or `{minutes}`) where the number goes:
   `npx supabase secrets set TRACKER_INTERVAL_COMMAND='<command with {seconds}>'`

✔ Check: the MT710 shows up in Traccar, then in the app. Switch lost mode on:
Traccar's device page shows the command was sent, and positions speed up.

## 8. On the cat

Breakaway collar, two fingers of room, first wear indoors and supervised.
Keep a short daily log for 1–2 weeks: battery %, MB used (1NCE portal),
gaps in the route, false "left home" alerts, how the cat copes. The Collar
card's "days left" estimate and the 1NCE data use tell you whether the
battery and the 500 MB last.

## Security notes

* The Mictrack protocol has no encryption or login: anyone who knows an IMEI
  could send fake positions to port 5030. Fine for a test; before selling,
  only accept 1NCE's addresses on the firewall or use 1NCE's VPN.
* The service role key and the Traccar password stay on your computer, the
  server and in Supabase secrets, never in the app or the repository.
