import { useEffect } from "react";
import { detectQuality } from "./engine/quality";
import { Briefing } from "./screens/Briefing";
import { Library } from "./screens/Library";
import { Pairing } from "./screens/Pairing";
import { PostRide } from "./screens/PostRide";
import { Ride } from "./screens/Ride";
import { Settings } from "./screens/Settings";
import { Upload } from "./screens/Upload";
import { useApp } from "./store";

export function App() {
  const screen = useApp((s) => s.screen);
  useEffect(() => {
    // First run: auto-detect the graphics preset; deep links: ?course=<id>&screen=briefing|ride
    try {
      if (!localStorage.getItem("rideprep.quality.detected")) {
        useApp.getState().updateSettings({ quality: detectQuality() });
        localStorage.setItem("rideprep.quality.detected", "1");
      }
    } catch { /* storage unavailable */ }
    const q = new URLSearchParams(location.search);
    const course = q.get("course");
    if (course) useApp.getState().go((q.get("screen") as never) ?? "briefing", { courseId: course, camera: (q.get("camera") as never) ?? "chase" });
  }, []);
  switch (screen) {
    case "upload": return <Upload />;
    case "briefing": return <Briefing />;
    case "pairing": return <Pairing />;
    case "ride": return <Ride />;
    case "postride": return <PostRide />;
    case "settings": return <Settings />;
    default: return <Library />;
  }
}
