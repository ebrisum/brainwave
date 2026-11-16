# App impressions for the website

Screens from the real app (web build, demo mode, real OpenStreetMap map via
OpenFreeMap), in Dutch and English.

| File | Use |
|---|---|
| `hero-nl.jpg`, `hero-en.jpg` | 2400×1260 banner: headline + three phones |
| `cards/<lang>/NN-*.jpg` | 1200×1500 (4:5) feature cards: headline, subline, phone |
| framed phones (zip, not in git) | each screen in a phone, transparent PNG, 1254×2616 |

Make them again after app changes:

```bash
cd app && npx expo export -p web --output-dir /tmp/web && npx serve -s /tmp/web -l 8090 &
node marketing/capture.cjs http://localhost:8090 /tmp/raw     # raw screens, nl + en
node marketing/compose.cjs /tmp/raw marketing                # frames, cards, hero
```

Headlines and sublines live in `compose.cjs` (COPY, HERO). The brand name
"CAT TRACKER" is a placeholder until the real name and logo exist.

Map data © OpenStreetMap contributors, tiles OpenFreeMap / OpenMapTiles: keep a
small credit near the images on the website (e.g. in the footer).
