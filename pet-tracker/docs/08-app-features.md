# The complete app: what is in it, and switching it on

## What the app has now

| Tab / screen | What it does |
|---|---|
| **Map** | All cats on the map with the list below; buttons for *show all*, *me* and *satellite*; tap a cat for its card and walking directions. |
| **Cats** | A card per cat, grouped by household, with place, battery and quick actions: *Lost?*, *Find*, *History*, *Collar*. |
| **Alerts** | One inbox for every cat: left / back home, battery low, collar silent, lost mode, found. Unread badge on the tab. |
| **Places** | Every zone (per household and per cat) on a map, who is inside now, add and delete. |
| **Me** | Account, households & sharing, alerts, appearance, **language (English / Nederlands)**, help, privacy & data, staff tools. |
| Cat page | Live / route / heatmap, today, collar health, quick buttons to Find, History, Insights, Profile, Collar. |
| **Lost cat** | Lost mode on, compass + directions, a **live link** for neighbours (works without an account), a printable **"missing" poster** with QR code, a search checklist, and *Found!*. |
| **Find** | Arrow and distance from this phone to the cat (GPS + compass). |
| **History** | Pick a day; the route on the map and the day as a timeline: at home, out (how far), stops. |
| **Insights** | The week in numbers, a bar per day, comparison with last week. |
| **Profile** | Date of birth, breed, weight (warns if the collar is too heavy), microchip, vet, indoor/outdoor, notes for sitters. |
| **Collar** | Health, model and firmware, **power mode** (battery saver / normal / live), fitting and charging, **move the cat to a new collar** (history moves along), remove the collar. |
| Alerts settings | Push on/off, which alerts you get, **quiet hours** (lost mode always comes through). |
| Households & sharing | Households, members and roles, invites as **QR code, link or code**. |
| Help & support | Getting started, battery tips, questions, warranty, contact. |
| Privacy & data | Privacy policy and terms, **how long history is kept** (30-365 days), **export all data**, delete account. |
| Welcome | Three screens on first launch, then login or demo. Permissions are asked when needed, each with an explanation. |

## Switching it on (Supabase)

1. **SQL** — Supabase → SQL Editor → run `cloud/supabase/migrations/20261115001200_app_complete.sql`
   (wrap it in `begin; … commit;` like the earlier ones).
   ✔ Check: `select public.get_my_settings();` returns your settings.
   Until you run it, the app still works; the new parts (inbox, settings, live links, power mode, profile) stay empty.
2. **Push function** — `npx supabase functions deploy send-push`. Pushes now follow each person's alert settings, quiet hours and language.
3. **App settings** in `app/.env` (all optional):
   - `EXPO_PUBLIC_WEB_URL` — where the web build of the app is hosted. Live links and invite links then open in any browser. Without it, links use `cattracker://` and only work where the app is installed.
   - `EXPO_PUBLIC_SUPPORT_EMAIL`, `EXPO_PUBLIC_PRIVACY_URL`, `EXPO_PUBLIC_TERMS_URL`.
4. **Publish** — `npx eas update --branch preview` (Expo Go) as before.

## Hosting the web build (for live links and invites)

`npx expo export -p web` produces a folder you can host on any static host
(EAS Hosting, Netlify, Cloudflare Pages) on your own domain, with "single
page app" fallback to `index.html`. `/share/<token>` then shows the live
location to anyone with the link; `/join?code=…` lets people accept an
invite. This is part of the "outside the app" work (website and domain).

## Collars

Our own collar firmware reads `power_mode` from its config: *live* sends each
fix at once, *battery saver* batches more at home; the interval itself comes
from the server (30 / 15 / 5 min). Traccar trackers get the interval as a
command. Rebuild and flash the firmware to use it; older firmware ignores the
field and simply follows the interval.
