import { useEffect, useState } from "react";
import { LoadedCourse, localToLatLon, poseAt } from "@rideprep/course-format";
import { fmtDist, Units } from "../units";

interface Photo { id: string; thumb: string; capturedAt?: number; label: string; s: number }

/**
 * Real street-level photos at the points that matter (climb starts, technical corners, aid stations), from Mapillary
 * (CC BY-SA). Needs a free client token (mapillary.com/dashboard/developers). Images are shown live, not stored.
 */
export function StreetPhotos({ course, token, units }: { course: LoadedCourse; token: string; units: Units }) {
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [err, setErr] = useState<string>();
  useEffect(() => {
    if (!token) return;
    const seg = course.manifest.segments;
    const spots: { s: number; label: string }[] = [
      ...seg.climbs.map((c) => ({ s: c.sStart, label: `Climb ${(c.lengthM / 1000).toFixed(1)} km @ ${c.avgGradePct.toFixed(1)} %` })),
      ...seg.corners.filter((c) => c.vMaxDryKmh < 35).slice(0, 6).map((c) => ({ s: c.s, label: `${c.hairpin ? "Hairpin" : "Corner"} ${c.direction}, ${Math.round(c.vMaxDryKmh)} km/h max` })),
      ...seg.pois.filter((p) => ["aid_station", "bridge", "town_entry"].includes(p.type)).slice(0, 4).map((p) => ({ s: p.s, label: p.name || p.type })),
    ].slice(0, 12);
    const o = course.manifest.origin;
    let cancelled = false;
    Promise.all(spots.map(async (sp) => {
      const p = poseAt(course.route, sp.s);
      const [lat, lon] = localToLatLon(o.lat, o.lon, p.x, p.y);
      const d = 0.0004;
      const url = `https://graph.mapillary.com/images?access_token=${encodeURIComponent(token)}&fields=id,thumb_1024_url,captured_at,compass_angle`
        + `&bbox=${lon - d},${lat - d},${lon + d},${lat + d}&limit=5`;
      const r = await fetch(url);
      if (!r.ok) throw new Error(`Mapillary ${r.status}`);
      const j = (await r.json()) as { data: { id: string; thumb_1024_url: string; captured_at?: number; compass_angle?: number }[] };
      // Prefer images looking along the direction of travel
      const heading = (p.headingRad * 180) / Math.PI;
      const best = j.data.sort((a, b) => angDiff(a.compass_angle, heading) - angDiff(b.compass_angle, heading))[0];
      return best ? ({ id: best.id, thumb: best.thumb_1024_url, capturedAt: best.captured_at, label: sp.label, s: sp.s } as Photo) : null;
    }))
      .then((list) => { if (!cancelled) setPhotos(list.filter((x): x is Photo => !!x)); })
      .catch((e) => !cancelled && setErr(String(e)));
    return () => { cancelled = true; };
  }, [course, token]);
  if (!token) return <p className="muted">Add a Mapillary token in Settings to see real street-level photos of the key points.</p>;
  if (err) return <p className="warn">{err}</p>;
  if (!photos.length) return <p className="muted">Looking for street-level photos…</p>;
  return (
    <div className="photos">
      {photos.map((p) => (
        <a key={p.id} href={`https://www.mapillary.com/app/?pKey=${p.id}`} target="_blank" rel="noreferrer" className="photo">
          <img src={p.thumb} alt={p.label} loading="lazy" />
          <span>{fmtDist(p.s, units, 1)} · {p.label}{p.capturedAt ? ` · ${new Date(p.capturedAt).getFullYear()}` : ""}</span>
        </a>
      ))}
      <small className="muted">Photos © Mapillary contributors, CC BY-SA 4.0</small>
    </div>
  );
}

const angDiff = (a: number | undefined, b: number) => (a === undefined ? 180 : Math.abs(((a - b + 540) % 360) - 180));
