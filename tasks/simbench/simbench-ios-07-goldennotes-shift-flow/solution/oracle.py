"""Deterministic oracle: complete the four-step shift flow via agent-device.

Chains the three atomic tiers in the required order — note (typing), two
inventory claims (scroll-and-find), registration (keyboard occlusion) — so
the journal records the sequence the verifier demands. Techniques mirror the
sibling oracles: selector targets instead of stale refs, raw swipes for the
SwiftUI List (semantic scroll silently no-ops), a newline to drop the iOS
keyboard, and app-container state polling after every mutating step.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

BUNDLE_ID = "com.expo.simbench.goldennotes"
NOTE_TITLE = "Shift Opened 007"
CLAIM_ITEMS = ("Item 019", "Item 052")
REGISTER_NAME = "Riley Chen"
REGISTER_CODE = "DOCK-7"
DEVICE = os.environ.get("SIMBENCH_DEVICE", "iPhone 17")
MAX_SCROLLS = 30


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


def container_json(name: str, default):
    completed = subprocess.run(
        ["xcrun", "simctl", "get_app_container", "booted", BUNDLE_ID, "data"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        return default
    try:
        with open(completed.stdout.strip() + f"/Documents/{name}") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def note_created() -> bool:
    return any(n.get("title") == NOTE_TITLE for n in container_json("notes.json", []))


def item_claimed(item: str) -> bool:
    return item in container_json("claims.json", [])


def registered() -> bool:
    data = container_json("registration.json", {})
    return data.get("name") == REGISTER_NAME and data.get("code") == REGISTER_CODE


def visible_item_numbers(snapshot: str) -> list[int]:
    return [
        int(m.group(1)) for m in re.finditer(r"\[cell\]\s+\"Item (\d{3})\"", snapshot)
    ]


def create_note() -> None:
    run_text("press", 'label="Notes"', "--settle", check=False)
    run_text("fill", 'id="note-title-field"', NOTE_TITLE, "--settle")
    run_text("press", 'id="add-note-button"', "--settle")
    time.sleep(1)
    if not note_created():
        raise SystemExit("oracle: note did not land")
    # The field keeps focus after Add and the keyboard covers the tab bar;
    # a newline resigns focus so tab presses can land.
    run_text("type", "\n", check=False)
    time.sleep(1)


def goto_inventory() -> None:
    for _ in range(3):
        run_text("press", 'label="Inventory"', "--settle", check=False)
        if visible_item_numbers(run_text("snapshot", "-i")):
            return
        # Keyboard may still be up and swallowing the tap; drop it and retry.
        run_text("type", "\n", check=False)
        time.sleep(1)
    raise SystemExit("oracle: could not open the Inventory tab")


def claim(item: str) -> None:
    number = int(item.split()[-1])
    for _ in range(MAX_SCROLLS):
        if item_claimed(item):
            return
        snapshot = run_text("snapshot", "-i")
        visible = visible_item_numbers(snapshot)
        if number in visible:
            if visible and number in visible[-2:]:
                # Target sits in the last rows, where the tab bar overlays the
                # list and taps are refused or miss. Pull it toward mid-screen.
                run_text("swipe", "200", "500", "200", "400", "400")
                continue
            run_text("press", f'id="claim-{item}"', "--settle", check=False)
            time.sleep(1)
            if item_claimed(item):
                return
            run_text("swipe", "200", "500", "200", "400", "400")
            continue
        # Direction-aware small step: a bare fling can jump past the target.
        if visible and min(visible) > number:
            run_text("swipe", "200", "450", "200", "600", "500")
        else:
            run_text("swipe", "200", "600", "200", "450", "500")
    raise SystemExit(f"oracle: could not claim {item!r}")


def register() -> None:
    run_text("press", 'label="Register"', "--settle")
    run_text("fill", 'id="name-field"', REGISTER_NAME, "--settle")
    for _ in range(3):
        # Re-fill each round: a press that lands on the keyboard (occluded
        # button) types stray characters into the focused code field, and
        # fill replaces the content, repairing it.
        run_text("fill", 'id="code-field"', REGISTER_CODE, "--settle")
        # `keyboard dismiss` is Android-only here; a newline submits the
        # single-line TextField, which resigns focus and drops the keyboard.
        run_text("type", "\n", check=False)
        time.sleep(1)
        run_text("press", 'id="register-button"', "--settle", check=False)
        time.sleep(1)
        if registered():
            return
    raise SystemExit("oracle: registration did not land")


def main() -> None:
    subprocess.run(
        ["xcrun", "simctl", "terminate", "booted", BUNDLE_ID], capture_output=True
    )
    close_stale_sessions()
    run_text("open", "--platform", "ios", "--device", DEVICE, BUNDLE_ID)

    create_note()
    goto_inventory()
    for item in CLAIM_ITEMS:
        claim(item)
    register()

    run_text("close", check=False)
    print(
        f"oracle: flow complete — note {NOTE_TITLE!r}, claims {CLAIM_ITEMS}, "
        f"registered {REGISTER_NAME!r}"
    )


if __name__ == "__main__":
    sys.exit(main())
