"""Deterministic oracle: tap the red square in the vision grid.

The trusted oracle reads this installation's randomized layout, locates the
container in the accessibility tree, and taps the target through the UI.
Candidates do not receive the layout file as task input.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time

BUNDLE_ID = "com.expo.simbench.goldenlab"
DEVICE = os.environ.get("SIMBENCH_DEVICE", "iPhone 17")
CELL, SPACING = 58.0, 8.0
SCREEN_W, SCREEN_H = 402.0, 874.0


def run_text(*args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["agent-device", *args], capture_output=True, text=True, timeout=180
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"agent-device {' '.join(args)} failed: "
            f"{completed.stdout[-300:]} {completed.stderr[-300:]}"
        )
    return completed.stdout


def close_stale_sessions() -> None:
    # Only the trial-owned session: other agents may be using this Mac.
    subprocess.run(
        ["agent-device", "close", "--session", os.environ.get("AGENT_DEVICE_SESSION", "default")],
        capture_output=True, timeout=60,
    )


def grid_rect() -> dict:
    raw = run_text("snapshot", "--json")
    payload = json.loads(raw[raw.find("{") :])
    for node in (payload.get("data") or {}).get("nodes") or []:
        if node.get("identifier") == "grid-canvas":
            return node["rect"]
    raise RuntimeError("grid-canvas not in tree")


def red_tapped() -> bool:
    container = subprocess.run(
        ["xcrun", "simctl", "get_app_container", DEVICE, BUNDLE_ID, "data"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if container.returncode != 0:
        return False
    try:
        with open(container.stdout.strip() + "/Documents/grid-taps.json") as f:
            taps = json.load(f)
    except (OSError, ValueError):
        return False
    return bool(taps) and taps[-1] == "red"


def main() -> None:
    subprocess.run(
        ["xcrun", "simctl", "terminate", DEVICE, BUNDLE_ID], capture_output=True
    )
    close_stale_sessions()
    run_text("open", "--platform", "ios", "--device", os.environ.get("SIMBENCH_DEVICE_NAME", DEVICE), BUNDLE_ID)
    run_text("press", 'label="Grid"', "--settle")

    container = subprocess.run(
        ["xcrun", "simctl", "get_app_container", DEVICE, BUNDLE_ID, "data"],
        check=True, capture_output=True, text=True, timeout=60,
    ).stdout.strip()
    with open(container + "/Documents/grid-layout.json") as stream:
        layout = json.load(stream)
    red_row, red_column = next((r, c) for r, row in enumerate(layout)
                              for c, color in enumerate(row) if color == "red")
    rect = grid_rect()
    x = rect["x"] + red_column * (CELL + SPACING) + CELL / 2
    y = rect["y"] + red_row * (CELL + SPACING) + CELL / 2

    # Argent can start a persistent server that inherits its output handles.
    # A file lets us wait for the CLI exit without waiting for daemon pipe EOF.
    with tempfile.TemporaryFile() as output:
        subprocess.run(
            [
                "argent", "run", "gesture-tap",
                "--udid", DEVICE,
                "--x", f"{x / SCREEN_W:.4f}",
                "--y", f"{y / SCREEN_H:.4f}",
            ],
            stdout=output,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=120,
        )
    time.sleep(1)

    run_text("close", check=False)
    if red_tapped():
        print("oracle: tapped the red square via UI")
        return
    raise SystemExit("oracle: red square was not tapped")


if __name__ == "__main__":
    sys.exit(main())
