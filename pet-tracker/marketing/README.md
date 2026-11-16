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

## The collar (product renders)

`product/scene.html` is a Three.js scene of the collar: a 19-gram pod on a
breakaway collar, charging base, colours, size next to a 2-euro coin.
**Illustrative:** Eview does not publish the EV-206M's exact shape or size,
so swap these for real photos (or Eview's white-label renders with our logo)
once the samples arrive.

| File | Use |
|---|---|
| `hero-collar-nl.jpg`, `hero-collar-en.jpg` | 2400×1260 banner: collar + app |
| `product-cards/<lang>/NN-*.jpg` | 1200×1500 cards: weight, no subscription, connected, charging, colours, size |
| renders (zip, not in git) | transparent PNGs, 2000×1500 (colours 2400×1200) |

```bash
cd marketing && npm install                                   # three.js
node product/render.cjs /tmp/renders                          # transparent PNGs
node product/compose.cjs /tmp/renders /tmp/raw marketing      # cards + banner (needs the app screens)
```
