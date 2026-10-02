"""One-click course import for the render project (the hand-off bundle from tools/unreal_bundle.py).

In the Unreal Editor: Tools → Execute Python Script… → this file. Or in the Output Log (Cmd: Python):
    py "Scripts/build_level.py"                      everything (all chunks, rails at the start, climbs and hero road)
    py "Scripts/build_level.py" --chunks 86,87,88    a few chunks for a quick look
    py "Scripts/build_level.py" --rails km:44-46.5   rails only where you want to film

Reads <project>/Course (the course package), <project>/Rider (rider GLBs) and, if present,
<project>/Config/RidePrepAssetOverrides.json (swap kit trees/props for Fab/Megascans assets), then runs
import_game_level.py: World Partition level, kit materials, terrain/roads/buildings, hero road, trees and props, RVT,
camera rails along the riding line, the rider. Extra arguments are passed through.
"""
import importlib
import os
import sys

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
HERE = os.path.join(PROJECT, "Scripts")
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def run(extra=()):
    course = os.path.join(PROJECT, "Course")
    if not os.path.exists(os.path.join(course, "game", "index.json")):
        unreal.log_error(f"[RidePrep] no course at {course} (expected Course/manifest.json and Course/game/index.json)")
        return
    args = ["--package", course, "--rider-dir", os.path.join(PROJECT, "Rider")]
    overrides = os.path.join(PROJECT, "Config", "RidePrepAssetOverrides.json")
    if os.path.exists(overrides):
        args += ["--overrides", overrides]
    saved = sys.argv
    sys.argv = [os.path.join(HERE, "import_game_level.py"), *args, *extra]
    try:
        import import_game_level

        importlib.reload(import_game_level)  # pick up edits between runs in the same editor session
        with unreal.ScopedSlowTask(1, "RidePrep: building the course level (this takes a while)") as task:
            task.make_dialog(True)
            import_game_level.main()
            task.enter_progress_frame(1)
    finally:
        sys.argv = saved


# Only arguments typed after the script path (the editor may leave other things in sys.argv)
run([x for x in sys.argv[1:] if x.startswith("--") or not x.endswith(".py")] if len(sys.argv) > 1 else [])
