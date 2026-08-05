"""Deterministic oracle: tap the red square in the vision grid.

Grid cells are hidden from the accessibility tree, so the oracle computes the
red cell's center from the grid container's frame and the app's fixed layout
(row 3, column 1, zero-based; 58pt cells with 8pt spacing), then taps by
coordinate via argent. Screen frames are in points on a 402x874pt device.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time

BUNDLE_ID = "com.expo.simbench.goldenlab"
DEVICE = "iPhone 17"
RED_ROW, RED_COLUMN = 3, 1
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
    listing = run_text("session", "list", check=False)
    for name in re.findall(r'"name":\s*"([^"]+)"', listing):
        subprocess.run(
            ["agent-device", "close", "--session", name],
            capture_output=True,
            timeout=60,
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
        ["xcrun", "simctl", "get_app_container", "booted", BUNDLE_ID, "data"],
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
        ["xcrun", "simctl", "terminate", "booted", BUNDLE_ID], capture_output=True
    )
    close_stale_sessions()
    run_text("open", "--platform", "ios", "--device", DEVICE, BUNDLE_ID)
    run_text("press", 'label="Grid"', "--settle")

    rect = grid_rect()
    x = rect["x"] + RED_COLUMN * (CELL + SPACING) + CELL / 2
    y = rect["y"] + RED_ROW * (CELL + SPACING) + CELL / 2

    udid_out = subprocess.run(
        ["xcrun", "simctl", "list", "devices", "booted"],
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout
    match = re.search(r"[A-F0-9-]{36}", udid_out)
    if not match:
        raise SystemExit("oracle: no booted simulator")
    subprocess.run(
        [
            "argent", "run", "gesture-tap",
            "--udid", match.group(0),
            "--x", f"{x / SCREEN_W:.4f}",
            "--y", f"{y / SCREEN_H:.4f}",
        ],
        capture_output=True,
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
