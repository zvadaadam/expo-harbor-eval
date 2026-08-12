"""Deterministic oracle: create the target note through the UI via agent-device.

No LLM involved. Re-snapshots after every mutating action and resolves fresh
element refs each time — refs go stale whenever the tree re-renders (the
keyboard appearing after `fill` is enough), and pressing a stale ref taps
whatever now occupies those coordinates.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

BUNDLE_ID = "com.expo.simbench.goldennotes"
TARGET_TITLE = "Harbor Sim Bench 001"
DEVICE = os.environ.get("SIMBENCH_DEVICE", "iPhone 17")


def run(*args: str) -> dict:
    completed = subprocess.run(
        ["agent-device", *args, "--json"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    raw = completed.stdout
    start = raw.find("{")
    if start == -1:
        raise RuntimeError(
            f"agent-device {args[0]}: no JSON in output: {raw[:200]} {completed.stderr[:200]}"
        )
    payload = json.loads(raw[start:])
    if not payload.get("success", False):
        raise RuntimeError(f"agent-device {args[0]} failed: {json.dumps(payload)[:400]}")
    return payload.get("data") or {}


def snapshot_nodes() -> list[dict]:
    data = run("snapshot", "-i")
    return data.get("nodes") or data.get("elements") or []


def find_ref(nodes: list[dict], role: str, label: str) -> str:
    want_role = role.replace("-", "").lower()
    for node in nodes:
        node_role = str(node.get("role") or node.get("type") or "")
        node_label = " ".join(
            str(node.get(key) or "")
            for key in ("identifier", "label", "name", "text")
        )
        ref = node.get("ref") or node.get("id")
        if (
            ref
            and want_role in node_role.replace("-", "").lower()
            and label in node_label
        ):
            return ref if str(ref).startswith("@") else f"@{ref}"
    raise RuntimeError(
        f"No node with role~{role!r} label~{label!r} in: "
        + json.dumps(nodes)[:400]
    )


def close_stale_sessions() -> None:
    listing = subprocess.run(
        ["agent-device", "session", "list"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    try:
        sessions = json.loads(listing.stdout).get("sessions", [])
    except ValueError:
        sessions = []
    for session in sessions:
        name = session.get("name")
        if name:
            subprocess.run(
                ["agent-device", "close", "--session", name],
                capture_output=True,
                timeout=60,
            )


def main() -> None:
    subprocess.run(
        ["xcrun", "simctl", "terminate", "booted", BUNDLE_ID],
        capture_output=True,
    )
    close_stale_sessions()
    run("open", "--platform", "ios", "--device", DEVICE, BUNDLE_ID)

    field = find_ref(snapshot_nodes(), "text-field", "note-title-field")
    run("fill", field, TARGET_TITLE, "--settle")

    # Fresh snapshot: the keyboard is now up and refs have changed.
    add_button = find_ref(snapshot_nodes(), "button", "Add")
    run("press", add_button, "--settle")

    run("close")
    print(f"oracle: created note {TARGET_TITLE!r} via UI")


if __name__ == "__main__":
    sys.exit(main())
