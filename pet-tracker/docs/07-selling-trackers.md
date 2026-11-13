# Selling trackers: labels, scanning and who has which tracker

## How it fits together

1. **Register** each tracker before it ships: its id (IMEI), model and SIM
   (ICCID). The database stores a hashed claim code and the script prints a
   label with a QR code.
2. **Label** inside the box (not on the outside: whoever has the code can link
   the tracker). The QR code holds
   `cattracker://add-cat?device=<id>&code=<code>`; the id and code are also
   printed for typing.
3. **The customer** opens the app → Add cat → GPS collar → **Scan the QR
   code**. The app checks the label first ("MT710 recognised. Ready to add",
   "already linked to another account", or "doesn't match") and only links it
   when they tap **Claim collar**. With the installed app, the phone's own
   camera opens the same screen.
4. From then on the tracker, its SIM and the customer's account are linked:
   `trackers.mjs list` shows who has which tracker.

## Commands (in `cloud/provisioning`, after `npm install`)

Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` first (Supabase →
Settings → API). The service role key stays on your own computer.

```bash
# Register a batch: one line per tracker, "imei[,model[,iccid]]"
node provision.mjs trackers.csv out
#   out/labels.html   sheet of 70 × 34 mm labels to print on A4
#   out/qr/<id>.png   one QR code per tracker, for a label printer
#   out/labels.csv    id, code and link (keep it safe: codes are shown once)

node trackers.mjs list                 # every tracker, owner, cat, last check-in
node trackers.mjs list olga@           # search by email, tracker id or ICCID
node trackers.mjs csv > trackers.csv   # everything, for a spreadsheet
node trackers.mjs reset 861234567890123  # a returned tracker: removes owner and
                                         # history, prints a new label (old one stops working)

node demo-label.mjs                    # label for the app's demo collar
```

## Testing without a real tracker

* **Demo mode:** `node demo-label.mjs`, open `out/demo-label.png` on your
  computer screen, then in the app (demo) → Add cat → GPS collar → Scan.
* **Your own Supabase:** register a pretend tracker, e.g. a `trackers.csv`
  with the line `TEST-0001,MT710`, run `provision.mjs`, scan the label with
  the app while signed in. `trackers.mjs list` then shows your email next to
  `TEST-0001`. `trackers.mjs reset TEST-0001` makes it available again.
