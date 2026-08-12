"""Deterministic oracle: submit the Register form via agent-device.

The Register button is pinned under the keyboard while either field is
focused (the screen opts out of keyboard avoidance), so the oracle must
dismiss the keyboard before pressing it — the step this tier exists to test.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time

BUNDLE_ID = "com.expo.simbench.goldennotes"
TARGET_NAME = "Ada Lovelace"
TARGET_CODE = "EXPO-7431"
DEVICE = "iPhone 17"


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


def registered() -> bool:
    container = subprocess.run(
        ["xcrun", "simctl", "get_app_container", "booted", BUNDLE_ID, "data"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if container.returncode != 0:
        return False
    try:
        with open(container.stdout.strip() + "/Documents/registration.json") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return False
    return data.get("name") == TARGET_NAME and data.get("code") == TARGET_CODE


def main() -> None:
    subprocess.run(
        ["xcrun", "simctl", "terminate", "booted", BUNDLE_ID], capture_output=True
    )
    close_stale_sessions()
    run_text("open", "--platform", "ios", "--device", DEVICE, BUNDLE_ID)
    run_text("press", 'label="Register"', "--settle")

    run_text("fill", 'id="name-field"', TARGET_NAME, "--settle")

    for _ in range(3):
        # Re-fill each round: a press that lands on the keyboard (occluded
        # button) types stray characters into the focused code field, and
        # fill replaces the content, repairing it.
        run_text("fill", 'id="code-field"', TARGET_CODE, "--settle")
        # `keyboard dismiss` is Android-only here; typing a newline submits
        # the single-line TextField, which resigns focus and drops the
        # keyboard on iOS.
        run_text("type", "\n", check=False)
        time.sleep(1)
        run_text("press", 'id="register-button"', "--settle", check=False)
        time.sleep(1)
        if registered():
            run_text("close", check=False)
            print(f"oracle: registered {TARGET_NAME!r}/{TARGET_CODE!r} via UI")
            return

    run_text("close", check=False)
    raise SystemExit("oracle: registration did not land")


if __name__ == "__main__":
    sys.exit(main())
