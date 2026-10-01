import { Encoder, Profile } from "@garmin/fitsdk";
import { RideRecord, RideSummary } from "./record";

const iso = (t: number) => new Date(t).toISOString().replace(/\.\d{3}Z$/, "Z");
const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/** GPX 1.1 with Garmin TrackPointExtension (hr, cad) and a <power> extension (understood by Strava and others). */
export function toGpx(recs: RideRecord[], name: string): string {
  const pts = recs.map((r) => {
    const ext = [`<power>${Math.round(r.powerW)}</power>`, "<gpxtpx:TrackPointExtension>",
      r.hrBpm ? `<gpxtpx:hr>${Math.round(r.hrBpm)}</gpxtpx:hr>` : "", r.cadenceRpm !== undefined ? `<gpxtpx:cad>${Math.round(r.cadenceRpm)}</gpxtpx:cad>` : "",
      "</gpxtpx:TrackPointExtension>"].join("");
    return `<trkpt lat="${r.lat.toFixed(7)}" lon="${r.lon.toFixed(7)}"><ele>${r.ele.toFixed(1)}</ele><time>${iso(r.t)}</time><extensions>${ext}</extensions></trkpt>`;
  });
  return `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="RidePrep" xmlns="http://www.topografix.com/GPX/1/1" xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">
<metadata><name>${esc(name)}</name><time>${iso(recs[0]?.t ?? Date.now())}</time></metadata>
<trk><name>${esc(name)}</name><type>VirtualRide</type><trkseg>
${pts.join("\n")}
</trkseg></trk></gpx>
`;
}

/** TCX activity (Biking) with power via ActivityExtension v2 (Watts). */
export function toTcx(recs: RideRecord[], summary: RideSummary): string {
  const tps = recs.map((r) => `<Trackpoint><Time>${iso(r.t)}</Time><Position><LatitudeDegrees>${r.lat.toFixed(7)}</LatitudeDegrees><LongitudeDegrees>${r.lon.toFixed(7)}</LongitudeDegrees></Position><AltitudeMeters>${r.ele.toFixed(1)}</AltitudeMeters><DistanceMeters>${r.s.toFixed(1)}</DistanceMeters>${r.hrBpm ? `<HeartRateBpm><Value>${Math.round(r.hrBpm)}</Value></HeartRateBpm>` : ""}${r.cadenceRpm !== undefined ? `<Cadence>${Math.round(r.cadenceRpm)}</Cadence>` : ""}<Extensions><ns3:TPX><ns3:Speed>${r.speedMs.toFixed(3)}</ns3:Speed><ns3:Watts>${Math.round(r.powerW)}</ns3:Watts></ns3:TPX></Extensions></Trackpoint>`);
  return `<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2" xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2">
<Activities><Activity Sport="Biking"><Id>${iso(summary.startTime)}</Id>
<Lap StartTime="${iso(summary.startTime)}"><TotalTimeSeconds>${summary.durationS.toFixed(0)}</TotalTimeSeconds><DistanceMeters>${summary.distanceM.toFixed(1)}</DistanceMeters><Calories>${Math.round(summary.kJ)}</Calories>${summary.avgHr ? `<AverageHeartRateBpm><Value>${Math.round(summary.avgHr)}</Value></AverageHeartRateBpm>` : ""}<Intensity>Active</Intensity><TriggerMethod>Manual</TriggerMethod>
<Track>
${tps.join("\n")}
</Track></Lap></Activity></Activities></TrainingCenterDatabase>
`;
}

const SEMI = 2 ** 31 / 180;

/** Developer fields written to every record (spec §12). */
export const DEV_FIELDS = [
  { key: 0, fieldName: "u_rider", units: "m/s", get: (r: RideRecord) => r.uRider },
  { key: 1, fieldName: "w_head", units: "m/s", get: (r: RideRecord) => r.wHead },
  { key: 2, fieldName: "shelter", units: "", get: (r: RideRecord) => r.shelter },
  { key: 3, fieldName: "air_density", units: "kg/m3", get: (r: RideRecord) => r.rho },
] as const;

/** FIT activity file (file_id, developer data, records, lap, session, activity) via the Garmin FIT JavaScript SDK. */
export function toFit(recs: RideRecord[], summary: RideSummary, laps: { startIndex: number; endIndex: number }[] = []): Uint8Array {
  const devId = { mesgNum: Profile.MesgNum.DEVELOPER_DATA_ID, developerDataIndex: 0, applicationVersion: 1,
    applicationId: [0x52, 0x69, 0x64, 0x65, 0x50, 0x72, 0x65, 0x70, 0, 0, 0, 0, 0, 0, 0, 1] };
  const descs = DEV_FIELDS.map((f) => ({
    mesgNum: Profile.MesgNum.FIELD_DESCRIPTION, developerDataIndex: 0, fieldDefinitionNumber: f.key, fitBaseTypeId: 136 /* float32 */,
    fieldName: f.fieldName, units: f.units,
  }));
  const enc = new Encoder();
  // The SDK's message typings are keyed by mesgNum; messages here follow the FIT Profile field names.
  const write = (m: Record<string, unknown>) => enc.writeMesg(m as never);
  const start = new Date(summary.startTime);
  write({ mesgNum: Profile.MesgNum.FILE_ID, type: "activity", manufacturer: "development", product: 1, timeCreated: start, serialNumber: 1 });
  write(devId);
  descs.forEach((d, k) => {
    write(d);
    enc.addDeveloperField(k, devId as never, d as never);
  });
  write({ mesgNum: Profile.MesgNum.EVENT, timestamp: start, event: "timer", eventType: "start" });
  for (const r of recs) {
    const m: Record<string, unknown> = {
      mesgNum: Profile.MesgNum.RECORD, timestamp: new Date(r.t), positionLat: Math.round(r.lat * SEMI), positionLong: Math.round(r.lon * SEMI),
      altitude: r.ele, distance: r.s, speed: r.speedMs, power: Math.round(Math.max(0, r.powerW)), grade: r.gradePct, temperature: Math.round(r.tempC),
      developerFields: Object.fromEntries(DEV_FIELDS.map((f) => [f.key, f.get(r)])),
    };
    if (r.hrBpm) m.heartRate = Math.round(r.hrBpm);
    if (r.cadenceRpm !== undefined) m.cadence = Math.round(r.cadenceRpm);
    write(m);
  }
  const end = new Date(recs.length ? recs[recs.length - 1].t : summary.startTime);
  write({ mesgNum: Profile.MesgNum.EVENT, timestamp: end, event: "timer", eventType: "stopAll" });
  const lapList = laps.length ? laps : [{ startIndex: 0, endIndex: recs.length - 1 }];
  for (const l of lapList) {
    const a = recs[l.startIndex];
    const b = recs[l.endIndex];
    if (!a || !b) continue;
    write({ mesgNum: Profile.MesgNum.LAP, timestamp: new Date(b.t), startTime: new Date(a.t), totalElapsedTime: (b.t - a.t) / 1000,
      totalTimerTime: (b.t - a.t) / 1000, totalDistance: b.s - a.s, event: "lap", eventType: "stop", sport: "cycling", subSport: "virtualActivity" });
  }
  write({ mesgNum: Profile.MesgNum.SESSION, timestamp: end, startTime: start, totalElapsedTime: summary.durationS, totalTimerTime: summary.durationS,
    totalDistance: summary.distanceM, sport: "cycling", subSport: "virtualActivity", avgPower: Math.round(summary.avgPowerW),
    normalizedPower: Math.round(summary.npW), trainingStressScore: summary.tss, intensityFactor: summary.ifactor, totalWork: Math.round(summary.kJ * 1000),
    avgHeartRate: summary.avgHr ? Math.round(summary.avgHr) : undefined, maxHeartRate: summary.maxHr, firstLapIndex: 0, numLaps: lapList.length,
    event: "session", eventType: "stop", totalAscent: Math.round(summary.ascentM) });
  write({ mesgNum: Profile.MesgNum.ACTIVITY, timestamp: end, totalTimerTime: summary.durationS, numSessions: 1, type: "manual",
    event: "activity", eventType: "stop" });
  return enc.close();
}
