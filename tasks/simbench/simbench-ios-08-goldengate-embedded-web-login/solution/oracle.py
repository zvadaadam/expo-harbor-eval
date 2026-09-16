"""Deterministic oracle: sign in through the in-app HarborID web sheet.

The embedded surface is an in-app WKWebView presented as a sheet; agent-device
reads its DOM as a semantic tree, so the oracle drives it with role+label
selectors (no coordinates). Technique mirrors the sibling oracles: selector
targets instead of stale refs, a newline to submit where focus lingers, and
app-container state polling after every mutating step. Retries absorb the web
sheet's load latency and the two-second identity-provider login delay.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

BUNDLE_ID = "com.expo.simbench.goldengate"
USERNAME = os.environ.get("SIMBENCH_OAUTH_USER", "ada.lovelace")
ACCESS_CODE = os.environ.get("SIMBENCH_OAUTH_CODE", "engine-1843")
CONSENT = os.environ.get("SIMBENCH_OAUTH_CONSENT", "allow")
DEVICE = os.environ.get("SIMBENCH_DEVICE", "iPhone 17")


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
    subprocess.run(
        ["agent-device", "close", "--session", os.environ.get("AGENT_DEVICE_SESSION", "default")],
        capture_output=True, timeout=60,
    )


def container_json(name: str, default):
    completed = subprocess.run(
        ["xcrun", "simctl", "get_app_container", DEVICE, BUNDLE_ID, "data"],
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
    return session.get("username") == USERNAME and session.get("mode") == "embedded"


def consent_recorded(kind: str) -> bool:
    return any(e.get("kind") == kind for e in container_json("events.json", []))


def main() -> None:
    subprocess.run(["xcrun", "simctl", "terminate", DEVICE, BUNDLE_ID], capture_output=True)
    close_stale_sessions()
    run_text("open", "--platform", "ios", "--device",
             os.environ.get("SIMBENCH_DEVICE_NAME", DEVICE), BUNDLE_ID)

    run_text("press", 'id="sign-in-embedded-button"', "--settle")

    # The WKWebView sheet loads its form asynchronously; wait for the fields.
    for _ in range(15):
        if 'label="Username"' in run_text("snapshot", "-i", check=False):
            break
        time.sleep(1)

    run_text("fill", 'role=textfield label="Username"', USERNAME, "--settle", check=False)
    run_text("fill", 'role=textfield label="Access code"', ACCESS_CODE, "--settle", check=False)
    run_text("press", 'role=button label="Sign in"', "--settle", check=False)

    # Provider login has a two-second delay before the consent page renders.
    target = "Allow" if CONSENT == "allow" else "Deny"
    for _ in range(15):
        if f'label="{target}"' in run_text("snapshot", "-i", check=False):
            break
        time.sleep(1)
    run_text("press", f'role=button label="{target}"', "--settle", check=False)

    for _ in range(15):
        time.sleep(1)
        if CONSENT != "allow":
            if consent_recorded("provider-consent-denied"):
                break
        elif signed_in():
            break

    run_text("close", check=False)
    if CONSENT != "allow":
        if consent_recorded("provider-consent-denied") and not signed_in():
            print("oracle: consent denied, no session established")
            return
        raise SystemExit("oracle: deny path did not reach the expected state")
    if signed_in():
        print(f"oracle: signed in as {USERNAME!r} through the embedded web sheet")
        return
    raise SystemExit("oracle: embedded sign-in did not complete")


if __name__ == "__main__":
    sys.exit(main())
