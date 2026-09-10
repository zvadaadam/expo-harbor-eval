"""Portable, standard-library-only simbench evidence collection and verification.

Vendored into each task's tests/ so tasks remain independently runnable.
The manifest binds a snapshot to a trial; hashes detect corruption, not an
adversarial collector. Only the harness should supply evidence bundles.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

FILES = {
    "com.expo.simbench.goldennotes": {
        "notes.json": list, "claims.json": list,
        "registration.json": dict, "events.json": list,
    },
    "com.expo.simbench.goldenlab": {
        "settings.json": dict, "submission.json": dict,
        "grid-taps.json": list, "grid-layout.json": list, "events.json": list,
    },
}
MAX_FILE_BYTES = 8 * 1024 * 1024


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    tmp.replace(path)


def simctl(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["xcrun", "simctl", *args], capture_output=True, text=True, timeout=90,
    )
    if check and result.returncode:
        raise RuntimeError(f"simctl {args[0]} failed: {result.stderr.strip()[-500:]}")
    return result.stdout.strip()


def resolve_device(selector: str) -> str:
    devices = json.loads(simctl("list", "devices", "available", "-j"))["devices"]
    matches = [d for group in devices.values() for d in group
               if selector in (d["udid"], d["name"]) and d.get("isAvailable", True)]
    if len(matches) != 1:
        raise ValueError(f"Device {selector!r} matched {len(matches)} simulators; provide a UDID")
    return matches[0]["udid"]


def read_state(path: Path, expected: type):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"Invalid evidence file: {path.name}")
    value = json.loads(path.read_text())
    if not isinstance(value, expected):
        raise ValueError(f"Wrong state type: {path.name}")
    if path.name in ("events.json", "notes.json") and not all(isinstance(x, dict) for x in value):
        raise ValueError(f"Invalid records: {path.name}")
    return value


def snapshot(container: Path, output: Path, *, bundle_id: str, task_id: str,
             trial_id: str, device: str, backend: str) -> dict:
    """Copy a quiescent app container; absent initial-state files are explicit."""
    if not (container / "Documents").is_dir() or (container / "Documents").is_symlink():
        raise ValueError("App Documents directory is unavailable")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite evidence: {output}")
    output.mkdir(parents=True)
    files = {}
    for name, expected in FILES[bundle_id].items():
        source = container / "Documents" / name
        if not source.exists() and not source.is_symlink():
            files[name] = None  # fresh apps legitimately have no persisted state
            continue
        read_state(source, expected)
        data = source.read_bytes()
        target = output / "Documents" / name
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(data)
        files[name] = digest(data)
    manifest = {
        "schema_version": 1, "kind": "simbench-evidence", "bundle_id": bundle_id,
        "task_id": task_id, "trial_id": trial_id, "device": device,
        "backend": backend, "files": files,
    }
    # Written last: a partial copy is never a valid bundle.
    write_json(output / "manifest.json", manifest)
    return manifest


def validate_snapshot(root: Path, *, bundle_id: str, task_id: str, trial_id: str) -> dict:
    if (root / "Documents").is_symlink() or (root / "manifest.json").is_symlink():
        raise ValueError("Evidence must not contain directory or manifest symlinks")
    manifest = json.loads((root / "manifest.json").read_text())
    expected = {"schema_version": 1, "kind": "simbench-evidence",
                "bundle_id": bundle_id, "task_id": task_id, "trial_id": trial_id}
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"Evidence {key} mismatch")
    if set(manifest["files"]) != set(FILES[bundle_id]):
        raise ValueError("Evidence file inventory mismatch")
    for name, expected_type in FILES[bundle_id].items():
        path = root / "Documents" / name
        checksum = manifest["files"][name]
        if checksum is None:
            if path.exists() or path.is_symlink():
                raise ValueError(f"Unexpected evidence file: {name}")
        else:
            read_state(path, expected_type)
            if digest(path.read_bytes()) != checksum:
                raise ValueError(f"Evidence checksum mismatch: {name}")
    return manifest


def load_json(path: Path, default):
    # Absence is recorded in a validated snapshot. Parse errors must propagate.
    return json.loads(path.read_text()) if path.exists() else default


def verifier_main(bundle_id: str, build_checks, task_id: str) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reward", type=Path)
    parser.add_argument("--details", type=Path)
    parser.add_argument("--evidence", type=Path, default=os.environ.get("SIMBENCH_EVIDENCE_DIR"))
    parser.add_argument("--trial-id", default=os.environ.get("SIMBENCH_TRIAL_ID"))
    parser.add_argument("--device", default=os.environ.get("SIMBENCH_DEVICE", "iPhone 17"))
    args = parser.parse_args()
    details = {"ok": False, "checks": [], "evidence": {}, "errors": []}
    result = {"reward": 0.0, "sim_runner_ok": 0.0}
    try:
        trial_id = args.trial_id
        if args.evidence and not trial_id:
            raise ValueError("Replaying evidence requires --trial-id")
        trial_id = trial_id or args.reward.parent.resolve().name
        root = args.evidence
        if root is None:
            device = resolve_device(args.device)
            container = Path(simctl("get_app_container", device, bundle_id, "data"))
            # Stop app writes before copying. Failure to terminate an already
            # stopped app is harmless; failure with a live process is not.
            response = subprocess.run(
                ["xcrun", "simctl", "terminate", device, bundle_id],
                capture_output=True, text=True, timeout=30,
            )
            if response.returncode and not any(x in response.stderr for x in (
                "found nothing to terminate", "not running", "No such process",
            )):
                raise RuntimeError(f"Could not quiesce app: {response.stderr[-500:]}")
            root = args.reward.parent / "evidence"
            snapshot(container, root, bundle_id=bundle_id, task_id=task_id,
                     trial_id=trial_id, device=device,
                     backend=os.environ.get("SIMBENCH_BACKEND", "local-macos"))
        manifest = validate_snapshot(root, bundle_id=bundle_id, task_id=task_id, trial_id=trial_id)
        checks, extra, evidence = build_checks(root, load_json)
        checks.insert(0, {"name": "app installed in simulator", "passed": True})
        result = {"reward": float(all(c["passed"] for c in checks)),
                  **extra, "sim_runner_ok": 1.0}
        details.update(ok=True, checks=checks, evidence=evidence, manifest=manifest)
    except Exception as exc:
        details["errors"].append(str(exc))
    write_json(args.reward, result)
    if args.details:
        write_json(args.details, details)
    print(json.dumps(result))
    if not details["ok"]:
        raise SystemExit(2)
