"""Deterministic oracle: reveal the code, wait it out, submit it.

The code only appears after a five-second spinner, pressing Reveal again
during the wait restarts it, and the value is random per reveal — so the
oracle must wait patiently and read the code off the screen.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time

BUNDLE_ID = "com.expo.simbench.goldenlab"
DEVICE = "iPhone 17"


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


def node_label(identifier: str) -> str | None:
    raw = run_text("snapshot", "--json")
    payload = json.loads(raw[raw.find("{") :])
    for node in (payload.get("data") or {}).get("nodes") or []:
        if node.get("identifier") == identifier:
            return str(node.get("label") or "")
    return None


def submitted_matches_revealed() -> bool:
    container = subprocess.run(
        ["xcrun", "simctl", "get_app_container", "booted", BUNDLE_ID, "data"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if container.returncode != 0:
        return False
    base = container.stdout.strip() + "/Documents/"
    try:
        with open(base + "submission.json") as f:
            submitted = json.load(f).get("submitted")
        with open(base + "events.json") as f:
            events = json.load(f)
    except (OSError, ValueError):
        return False
    revealed = [e["title"] for e in events if e.get("kind") == "code-revealed"]
    return bool(submitted) and bool(revealed) and submitted == revealed[-1]


def main() -> None:
    subprocess.run(
        ["xcrun", "simctl", "terminate", "booted", BUNDLE_ID], capture_output=True
    )
    close_stale_sessions()
    run_text("open", "--platform", "ios", "--device", DEVICE, BUNDLE_ID)
    run_text("press", 'label="Reveal"', "--settle")
    run_text("press", 'id="reveal-button"', "--settle")

    code = None
    for _ in range(12):
        time.sleep(1)
        code = node_label("revealed-code")
        if code:
            break
    if not code:
        run_text("close", check=False)
        raise SystemExit("oracle: code never revealed")

    run_text("fill", 'id="code-entry-field"', code, "--settle")
    run_text("type", "\n", check=False)
    time.sleep(1)
    run_text("press", 'id="submit-code-button"', "--settle")
    time.sleep(1)

    run_text("close", check=False)
    if submitted_matches_revealed():
        print(f"oracle: submitted revealed code {code!r} via UI")
        return
    raise SystemExit("oracle: submission did not match revealed code")


if __name__ == "__main__":
    sys.exit(main())
