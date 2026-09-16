"""Deterministic oracle: sign in through the Safari hand-off.

The app opens the HarborID login in Safari and the callback returns over the
goldengate:// custom scheme. The app screen and Safari's "Open in GoldenGate?"
prompt are native (agent-device); Safari's web content is out-of-process, so
the oracle reads and drives it with argent's accessibility service. Safari also
raises a native "Save Password?" sheet on submit — the oracle dismisses it.

Note (see docs/oauth-simbench.md): agent-device cannot yet focus/type into
Safari's out-of-process web content with the pinned tool version, so this task
is held out of the model job cohorts until a driver can drive Safari web input;
the oracle uses argent, whose accessibility service reads Safari.
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
USERNAME = os.environ.get("SIMBENCH_OAUTH_USER", "grace.hopper")
ACCESS_CODE = os.environ.get("SIMBENCH_OAUTH_CODE", "cobol-1959")
CONSENT = os.environ.get("SIMBENCH_OAUTH_CONSENT", "allow")


def ad(*args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["agent-device", *args, "--session", SESSION],
        capture_output=True, text=True, timeout=180,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(f"agent-device {' '.join(args)} failed: {completed.stderr[-300:]}")
    return completed.stdout


def argent(tool: str, **kwargs) -> str:
    args = ["argent", "run", tool, "--udid", UDID]
    for key, value in kwargs.items():
        args += [f"--{key}", str(value)]
    return subprocess.run(args, capture_output=True, text=True, timeout=150).stdout


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


def tap(rect) -> None:
    x, y, w, h = rect
    argent("gesture-tap", x=round(x + w / 2, 4), y=round(y + h / 2, 4))


def tap_tallest(desc: str, needle: str) -> bool:
    found = rects(desc, needle)
    if found:
        tap(max(found, key=lambda r: r[3]))
    return bool(found)


def wait_web(needle: str, attempts: int = 25) -> str:
    for _ in range(attempts):
        desc = describe()
        if needle in desc:
            return desc
        time.sleep(1)
    return describe()


def dismiss_save_password() -> None:
    desc = describe()
    for label in ('"Not Now"', '"Never for This Website"'):
        if tap_tallest(desc, label):
            time.sleep(1)
            return


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
    return session.get("username") == USERNAME and session.get("mode") == "browser"


def has_event(kind: str) -> bool:
    return any(e.get("kind") == kind for e in container_json("events.json", []))


def main() -> None:
    subprocess.run(["xcrun", "simctl", "terminate", UDID, BUNDLE_ID], capture_output=True)
    subprocess.run(["xcrun", "simctl", "terminate", UDID, "com.apple.mobilesafari"], capture_output=True)
    subprocess.run(["agent-device", "close", "--session", SESSION], capture_output=True, timeout=60)
    ad("open", "--platform", "ios", "--device", DEVICE_NAME, BUNDLE_ID)
    ad("press", 'id="sign-in-browser-button"', "--settle")

    desc = wait_web("Sign in to continue")
    if "Sign in to continue" not in desc:
        raise SystemExit("oracle: Safari never showed the HarborID login")

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
    time.sleep(2)
    dismiss_save_password()

    target = "Allow" if CONSENT == "allow" else "Deny"
    desc = wait_web("Allow GoldenGate")
    tap_tallest(desc, f'AXButton "{target}"')
    time.sleep(1)
    dismiss_save_password()

    # Safari's "Open in GoldenGate?" hand-off prompt is native.
    for _ in range(12):
        if signed_in() or has_event("callback-received"):
            break
        d = describe()
        if "Open" in d and "GoldenGate" in d:
            tap_tallest(d, '"Open"')
        time.sleep(1)

    for _ in range(20):
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
        print(f"oracle: signed in as {USERNAME!r} through the Safari hand-off")
        return
    raise SystemExit("oracle: browser hand-off sign-in did not complete")


if __name__ == "__main__":
    sys.exit(main())
