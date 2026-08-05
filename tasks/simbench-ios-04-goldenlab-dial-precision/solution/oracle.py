"""Deterministic oracle: set the dial to the exact target via agent-device.

No single action solves this: the oracle reads the current value, drags the
slider thumb proportionally toward the target, and repeats until exact —
the read-act-verify loop the tier exists to test.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time

BUNDLE_ID = "com.expo.simbench.goldenlab"
TARGET = 72
DEVICE = "iPhone 17"
THUMB_INSET = 13.0  # slider thumb radius: usable track is inset on both ends
MAX_ROUNDS = 25


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


def snapshot_nodes() -> list[dict]:
    # Full snapshot, not -i: the value display is a non-interactive Text.
    raw = run_text("snapshot", "--json")
    payload = json.loads(raw[raw.find("{") :])
    return (payload.get("data") or {}).get("nodes") or []


def node_by_id(nodes: list[dict], identifier: str) -> dict | None:
    for node in nodes:
        if node.get("identifier") == identifier:
            return node
    return None


def read_state() -> tuple[int, dict]:
    nodes = snapshot_nodes()
    value_node = node_by_id(nodes, "dial-value")
    slider_node = node_by_id(nodes, "dial-slider")
    if value_node is None or slider_node is None:
        raise RuntimeError("dial-value or dial-slider not in tree")
    value = int(str(value_node.get("label") or "0"))
    return value, slider_node["rect"]


def thumb_x(rect: dict, value: int) -> float:
    usable = rect["width"] - 2 * THUMB_INSET
    return rect["x"] + THUMB_INSET + (value / 100.0) * usable


def saved_ok() -> bool:
    container = subprocess.run(
        ["xcrun", "simctl", "get_app_container", "booted", BUNDLE_ID, "data"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if container.returncode != 0:
        return False
    try:
        with open(container.stdout.strip() + "/Documents/settings.json") as f:
            return json.load(f).get("temperature") == TARGET
    except (OSError, ValueError):
        return False


def main() -> None:
    subprocess.run(
        ["xcrun", "simctl", "terminate", "booted", BUNDLE_ID], capture_output=True
    )
    close_stale_sessions()
    run_text("open", "--platform", "ios", "--device", DEVICE, BUNDLE_ID)

    for _ in range(MAX_ROUNDS):
        value, rect = read_state()
        if value == TARGET:
            run_text("press", 'id="save-temperature-button"', "--settle")
            time.sleep(1)
            if saved_ok():
                run_text("close", check=False)
                print(f"oracle: dial saved at {TARGET} via UI")
                return
            continue
        delta = TARGET - value
        if abs(delta) > 6:
            # Coarse: proportional drag. Drags below iOS's pan-start
            # threshold (~10pt ≈ 3 steps) do not register at all, so fine
            # adjustment must use the steppers instead.
            start_x = thumb_x(rect, value)
            end_x = thumb_x(rect, TARGET)
            y = rect["y"] + rect["height"] / 2
            run_text(
                "swipe",
                f"{start_x:.0f}",
                f"{y:.0f}",
                f"{end_x:.0f}",
                f"{y:.0f}",
                "600",
            )
            time.sleep(0.4)
            continue
        stepper = 'id="dial-plus"' if delta > 0 else 'id="dial-minus"'
        for _ in range(abs(delta)):
            run_text("press", stepper, check=False)
        time.sleep(0.4)

    run_text("close", check=False)
    raise SystemExit(f"oracle: dial not saved at {TARGET} after {MAX_ROUNDS} rounds")


if __name__ == "__main__":
    sys.exit(main())
