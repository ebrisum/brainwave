/** Minimal surface of HTMLVideoElement used by the controller (lets tests use a fake). */
export interface VideoLike { currentTime: number; playbackRate: number; paused: boolean; play(): Promise<void> | void; pause(): void }

export interface VideoSyncJson { name: string; sStart: number; sEnd: number; points: [number, number][]; medianSpeedMs: number }

/**
 * Plays real ride footage at the rider's *virtual* speed: the video time follows the course distance s via the
 * synced (s, videoTime) points; playback rate = virtual speed / speed when filmed, with a seek when drift > 1.5 s.
 */
export class VideoSync {
  private s: Float64Array;
  private t: Float64Array;
  constructor(public json: VideoSyncJson) {
    this.s = Float64Array.from(json.points.map((p) => p[0]));
    this.t = Float64Array.from(json.points.map((p) => p[1]));
  }

  covers(s: number) {
    return s >= this.json.sStart && s <= this.json.sEnd;
  }

  private bracket(s: number): number {
    let lo = 0, hi = this.s.length - 1;
    if (s <= this.s[0]) return 0;
    if (s >= this.s[hi]) return hi - 1;
    while (hi - lo > 1) {
      const m = (lo + hi) >> 1;
      if (this.s[m] <= s) lo = m; else hi = m;
    }
    return lo;
  }

  /** Video time for course distance s. */
  timeAt(s: number): number {
    const i = this.bracket(s);
    const f = (s - this.s[i]) / Math.max(this.s[i + 1] - this.s[i], 1e-6);
    return this.t[i] + (this.t[i + 1] - this.t[i]) * Math.min(Math.max(f, 0), 1);
  }

  /** Speed (m/s) when filmed around s (averaged over ±40 m to smooth GPS noise). */
  filmedSpeedAt(s: number): number {
    const a = this.timeAt(s - 40), b = this.timeAt(s + 40);
    const ds = Math.min(s + 40, this.json.sEnd) - Math.max(s - 40, this.json.sStart);
    return b > a ? ds / (b - a) : this.json.medianSpeedMs;
  }

  /** Call ~10×/s. Returns true while the footage covers the rider's position. */
  control(v: VideoLike, s: number, speed: number, paused: boolean): boolean {
    if (!this.covers(s)) {
      if (!v.paused) v.pause();
      return false;
    }
    const target = this.timeAt(s);
    if (paused || speed < 0.3) {
      if (!v.paused) v.pause();
      if (Math.abs(v.currentTime - target) > 0.5) v.currentTime = target;
      return true;
    }
    if (Math.abs(v.currentTime - target) > 1.5) v.currentTime = target;
    const drift = v.currentTime - target;
    // Rate follows the speed ratio, nudged to close small drifts within ~2 s
    const rate = speed / Math.max(this.filmedSpeedAt(s), 0.5) - Math.max(-0.25, Math.min(0.25, drift / 2));
    v.playbackRate = Math.min(Math.max(rate, 0.1), 4);
    if (v.paused) void v.play();
    return true;
  }
}
