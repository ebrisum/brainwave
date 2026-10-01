"""JSON-lines progress events (consumed by the API worker and the UI) and human-readable output."""
from __future__ import annotations

import json
import sys
import time
from typing import Any, TextIO


class Progress:
    def __init__(self, mode: str = "text", stream: TextIO | None = None):
        self.mode = mode
        self.stream = stream or (sys.stdout if mode == "json" else sys.stderr)
        self.t0 = time.time()
        self.listeners: list = []

    def emit(self, event: str, **data: Any) -> None:
        rec = {"event": event, "t": round(time.time() - self.t0, 3), **data}
        for cb in self.listeners:
            cb(rec)
        if self.mode == "json":
            self.stream.write(json.dumps(rec, default=str) + "\n")
            self.stream.flush()
        elif self.mode == "text":
            if event == "stage_start":
                self.stream.write(f"▶ {data['stage']}\n")
            elif event == "stage_end":
                status = data.get("status", "done")
                self.stream.write(f"  ✓ {data['stage']} ({status}, {data.get('duration_s', 0):.2f} s)\n")
            elif event == "warning":
                self.stream.write(f"  ⚠ {data.get('message')}\n")
            elif event == "done":
                self.stream.write(f"✔ {data.get('courseId')} → {data.get('path')}\n")
            elif event == "error":
                self.stream.write(f"✖ {data.get('message')}\n")
            self.stream.flush()

    def stage_progress(self, stage: str, fraction: float, note: str = "") -> None:
        self.emit("stage_progress", stage=stage, fraction=round(min(max(fraction, 0.0), 1.0), 4), note=note)


class NullProgress(Progress):
    def __init__(self):
        super().__init__(mode="none")
