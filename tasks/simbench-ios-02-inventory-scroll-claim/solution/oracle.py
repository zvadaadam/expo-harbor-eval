"""Deterministic oracle: claim an off-screen inventory row via agent-device.

Scroll-until-found: the target row starts far below the fold, and List cells
render lazily, so the oracle scrolls and re-snapshots until the row appears.
Rows are pressed via their claim-<item> accessibility id. Scrolling uses raw
coordinate swipes with a long duration: agent-device's semantic `scroll`
subcommand no-ops against this SwiftUI List (while still reporting success),
and short swipes fling with momentum.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time

BUNDLE_ID = "com.expo.simbench.goldennotes"
TARGET_ITEM = "Item 047"
DEVICE = "iPhone 17"
MAX_SCROLLS = 30

NODE_RE = re.compile(r"(@e\d+)\s+\[([\w-]+)\]\s+\"([^\"]*)\"")


def run_text(*args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["agent-device", *args],
        capture_output=True,
        text=True,
        timeout=180,
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


def claim_ref_for(snapshot: str, item: str) -> str | None:
    """Ref of the Claim button belonging to *item*'s row, or None."""
    nodes = NODE_RE.findall(snapshot)
    seen_item = False
    for ref, role, label in nodes:
        if label == item:
            seen_item = True
            continue
        if seen_item:
            if role == "button" and label == "Claim":
                return ref
            if role == "cell":  # next row started: row had no Claim button
                return None
    return None


def visible_item_numbers(snapshot: str) -> list[int]:
    return [
        int(m.group(1)) for m in re.finditer(r"\[cell\]\s+\"Item (\d{3})\"", snapshot)
    ]


def claim_registered() -> bool:
    container = subprocess.run(
        ["xcrun", "simctl", "get_app_container", "booted", BUNDLE_ID, "data"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if container.returncode != 0:
        return False
    path = container.stdout.strip() + "/Documents/claims.json"
    try:
        with open(path) as f:
            return TARGET_ITEM in json.load(f)
    except (OSError, ValueError):
        return False


def main() -> None:
    target_number = int(TARGET_ITEM.split()[-1])
    subprocess.run(
        ["xcrun", "simctl", "terminate", "booted", BUNDLE_ID], capture_output=True
    )
    close_stale_sessions()
    run_text("open", "--platform", "ios", "--device", DEVICE, BUNDLE_ID)
    run_text("press", 'label="Inventory"', "--settle")

    for _ in range(MAX_SCROLLS):
        snapshot = run_text("snapshot", "-i")
        ref = claim_ref_for(snapshot, TARGET_ITEM)
        if ref:
            visible = visible_item_numbers(snapshot)
            if visible and target_number in visible[-2:]:
                # Target sits in the last rows, where the tab bar overlays the
                # list and taps are refused or miss. Pull it toward mid-screen.
                run_text("swipe", "200", "500", "200", "400", "400")
                continue
            run_text("press", f'id="claim-{TARGET_ITEM}"', "--settle", check=False)
            time.sleep(1)
            if claim_registered():
                run_text("close", check=False)
                print(f"oracle: claimed {TARGET_ITEM!r} via UI")
                return
            # Tap refused or missed: nudge the row clear and retry.
            run_text("swipe", "200", "500", "200", "400", "400")
            continue
        # Direction-aware with a small step: a bare scroll is a near-full-page
        # fling that can jump straight past the target row.
        visible = visible_item_numbers(snapshot)
        if visible and min(visible) > target_number:
            run_text("swipe", "200", "350", "200", "600", "500")
        else:
            run_text("swipe", "200", "600", "200", "350", "500")

    run_text("close", check=False)
    raise SystemExit(
        f"oracle: could not claim {TARGET_ITEM!r} after {MAX_SCROLLS} rounds"
    )


if __name__ == "__main__":
    sys.exit(main())
