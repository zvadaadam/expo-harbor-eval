"""Deterministic oracle: sign in through the system ASWebAuthenticationSession.

The system surface mixes two kinds of screen. The app screen and the iOS
"'GoldenGate' Wants to Use ... to Sign In" confirmation are native, so the
oracle drives them with agent-device. The HarborID sheet itself is an
out-of-process web view that agent-device reads as a sparse tree, so — like the
vision-grid oracle — the oracle reads and drives that part with argent, whose
accessibility service exposes the web form as normalized-coordinate elements.
Every step is polled and retried because the sheet loads asynchronously and the
provider adds a two-second login delay.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

BUNDLE_ID = "com.expo.simbench.goldengate"
UDID = os.environ["SIMBENCH_DEVICE"]
DEVICE_NAME = os.environ.get("SIMBENCH_DEVICE_NAME", "iPhone 17")
SESSION = os.environ.get("AGENT_DEVICE_SESSION", "default")
USERNAME = os.environ.get("SIMBENCH_OAUTH_USER", "riley.chen")
ACCESS_CODE = os.environ.get("SIMBENCH_OAUTH_CODE", "harbor-2026")
CONSENT = os.environ.get("SIMBENCH_OAUTH_CONSENT", "allow")


def ad(*args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["agent-device", *args, "--session", SESSION],
        capture_output=True, text=True, timeout=180,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"agent-device {' '.join(args)} failed: "
            f"{completed.stdout[-300:]} {completed.stderr[-300:]}"
        )
    return completed.stdout


def argent(tool: str, **kwargs) -> str:
    args = ["argent", "run", tool, "--udid", UDID]
    for key, value in kwargs.items():
        args += [f"--{key}", str(value)]
    completed = subprocess.run(args, capture_output=True, text=True, timeout=150)
    return completed.stdout + completed.stderr


def describe() -> str:
    raw = argent("describe")
    match = re.search(r'"description":\s*"(.*?)",\s*"source"', raw, re.S)
    return match.group(1).encode().decode("unicode_escape") if match else raw


def rects(desc: str, needle: str) -> list[tuple[float, float, float, float]]:
    found = []
    for line in desc.splitlines():
        if needle in line:
            match = re.search(r"\(([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)\)", line)
            if match:
                found.append(tuple(map(float, match.groups())))
    return found


def tap(rect: tuple[float, float, float, float]) -> None:
    x, y, w, h = rect
    argent("gesture-tap", x=round(x + w / 2, 4), y=round(y + h / 2, 4))


def tap_tallest(desc: str, needle: str) -> bool:
    found = rects(desc, needle)
    if not found:
        return False
    tap(max(found, key=lambda r: r[3]))
    return True


def wait_web(needle: str, attempts: int = 25) -> str:
    for _ in range(attempts):
        desc = describe()
        if needle in desc:
            return desc
        time.sleep(1)
    return describe()


def container_json(name: str, default):
    completed = subprocess.run(
        ["xcrun", "simctl", "get_app_container", UDID, BUNDLE_ID, "data"],
        capture_output=True, text=True, timeout=60,
    )
    if completed.returncode != 0:
        return default
    try:
        with open(completed.stdout.strip() + f"/Documents/{name}") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def signed_in() -> bool:
    session = container_json("session.json", {})
    return session.get("username") == USERNAME and session.get("mode") == "system"


def has_event(kind: str) -> bool:
    return any(e.get("kind") == kind for e in container_json("events.json", []))


def main() -> None:
    subprocess.run(["xcrun", "simctl", "terminate", UDID, BUNDLE_ID], capture_output=True)
    subprocess.run(["agent-device", "close", "--session", SESSION], capture_output=True, timeout=60)
    ad("open", "--platform", "ios", "--device", DEVICE_NAME, BUNDLE_ID)
    ad("press", 'id="sign-in-system-button"', "--settle")

    # The iOS "Wants to Use ... to Sign In" alert is native; accept it, retrying
    # until the HarborID web sheet takes over.
    for _ in range(12):
        if "Sign in to continue" in describe():
            break
        ad("press", 'label="Continue"', "--settle", check=False)
        time.sleep(1)

    desc = wait_web("Sign in to continue")
    if "Sign in to continue" not in desc:
        ad("close", check=False)
        raise SystemExit("oracle: HarborID sheet never rendered")

    # Fill the web form through argent (agent-device sees it as sparse).
    tap(max(rects(desc, '"Username"'), key=lambda r: r[3]))
    time.sleep(1)
    argent("keyboard", text=USERNAME)
    time.sleep(1)
    desc = describe()
    tap(max(rects(desc, '"Access code"'), key=lambda r: r[3]))
    time.sleep(1)
    argent("keyboard", text=ACCESS_CODE)
    time.sleep(1)
    tap_tallest(describe(), 'AXButton "Sign in"')

    target = "Allow" if CONSENT == "allow" else "Deny"
    desc = wait_web("Allow GoldenGate")
    tap_tallest(desc, f'AXButton "{target}"')

    for _ in range(25):
        time.sleep(1)
        if CONSENT != "allow":
            if has_event("provider-consent-denied"):
                break
        elif signed_in():
            break

    ad("close", check=False)
    if CONSENT != "allow":
        if has_event("provider-consent-denied") and not signed_in():
            print("oracle: consent denied, no session established")
            return
        raise SystemExit("oracle: deny path did not reach the expected state")
    if signed_in():
        print(f"oracle: signed in as {USERNAME!r} through the system auth session")
        return
    raise SystemExit("oracle: system auth-session sign-in did not complete")


if __name__ == "__main__":
    sys.exit(main())
