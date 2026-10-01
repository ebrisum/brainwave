import { describe, expect, it } from "vitest";
import { VideoLike, VideoSync } from "../src/ride/videoSync";

const sync = new VideoSync({ name: "t", sStart: 0, sEnd: 1000, medianSpeedMs: 10, points: Array.from({ length: 101 }, (_, k) => [k * 10, 5 + k] as [number, number]) });
const fake = (): VideoLike & { plays: number } => ({ currentTime: 0, playbackRate: 1, paused: true, plays: 0, play() { this.paused = false; this.plays++; }, pause() { this.paused = true; } });

describe("video sync", () => {
  it("maps distance to video time", () => {
    expect(sync.timeAt(0)).toBe(5);
    expect(sync.timeAt(505)).toBeCloseTo(55.5, 6);
    expect(sync.filmedSpeedAt(500)).toBeCloseTo(10, 6);
  });
  it("plays at the virtual/filmed speed ratio and seeks on drift", () => {
    const v = fake();
    expect(sync.control(v, 300, 5, false)).toBe(true);
    expect(v.currentTime).toBeCloseTo(35, 6); // seeked
    expect(v.playbackRate).toBeCloseTo(0.5, 2);
    expect(v.paused).toBe(false);
    v.currentTime = 35.6; // slightly ahead → slow down a bit more
    sync.control(v, 300, 5, false);
    expect(v.playbackRate).toBeLessThan(0.5);
  });
  it("pauses when the rider stops or leaves the footage", () => {
    const v = fake();
    sync.control(v, 100, 8, false);
    sync.control(v, 100, 0, false);
    expect(v.paused).toBe(true);
    expect(sync.control(v, 2000, 8, false)).toBe(false);
  });
});
