"""Build a submitted Expo app and check its native UI on an owned iOS simulator.

Opt-in runtime lane. The harness provides dependencies/configuration and checks;
the submitted source supplies the actual app. This is development/CI execution,
not a security boundary for hostile submissions.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import plistlib
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

from expo_harbor_evals.simbench_evidence import digest, write_json

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = "dev.expo.harbor.candidate"
PROFILES = {
    "feedback-04-modal-editor-touch-freeze": "modal",
    "feedback-05-slider-relative-recenter": "slider",
    "sdk-04-image-picker-canceled-assets-guard": "picker",
}
EXCLUDED = {"node_modules", ".git", "ios", "android", "build", "dist", "__pycache__"}
CODE_SUFFIXES = {".tsx", ".ts", ".jsx", ".js", ".json", ".png", ".jpg", ".jpeg", ".svg"}


class CandidateFailure(Exception):
    """Candidate failed an application contract or did not build."""


def hashes(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(p in EXCLUDED or p.startswith(".") for p in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError("Source symlinks are unsupported")
        if path.is_file():
            result[relative.as_posix()] = digest(path.read_bytes())
    return result


def prepare(task: str, candidate: Path, output: Path, *, repo: Path = ROOT) -> dict:
    if task not in PROFILES:
        raise ValueError("No native scenario for this task")
    if output.resolve().is_relative_to(candidate.resolve()):
        raise ValueError("Output must be outside the submitted workspace")
    if not (candidate / "App.tsx").is_file():
        raise CandidateFailure("Submission must contain its complete App.tsx workspace")
    profile = PROFILES[task]
    template = repo / "mobile/templates" / ("sdk54" if profile == "slider" else "sdk56")
    package = json.loads((template / "package.json").read_text())
    if (candidate / "package.json").exists():
        try:
            submitted = json.loads((candidate / "package.json").read_text())
            if not isinstance(submitted, dict) or any(
                    not isinstance(submitted.get(section, {}), dict)
                    for section in ("dependencies", "devDependencies")):
                raise ValueError("Package must declare dependency objects")
        except ValueError as exc:
            raise CandidateFailure("Submission has an invalid package.json") from exc
        # These repair tasks permit code edits, not a replacement native stack.
        for section in ("dependencies", "devDependencies"):
            for name, version in submitted.get(section, {}).items():
                if package.get(section, {}).get(name) != version:
                    raise CandidateFailure(f"Dependency outside the pinned runtime contract: {name}")
    source = hashes(candidate)
    output.mkdir(parents=True, exist_ok=False)
    app = output / "app"
    shutil.copytree(template, app)
    submitted_dir = app / "submitted"
    submitted_dir.mkdir()
    copied = {}
    for name, checksum in source.items():
        if Path(name).suffix not in CODE_SUFFIXES or Path(name).name == "package.json":
            continue
        target = submitted_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate / name, target)
        copied[name] = checksum
    spec = {"schema_version": 1, "kind": "expo-candidate-runtime", "task": task,
            "profile": profile, "submission": copied, "template": hashes(template),
            "scenario_sha256": digest(Path(__file__).with_name("mobile_scenarios.py").read_bytes()),
            "trial_id": output.name, "bundle_id": BUNDLE,
            "validation_status": "requires-native-calibration"}
    write_json(output / "input.json", spec)
    return spec


class Commands:
    def __init__(self, output: Path, timeout: int):
        self.output = output
        self.deadline = time.monotonic() + timeout
        self.index = 0
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ("EXPO_TOKEN", "__API_SERVER_URL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")}
        self.env.update(CI="1", EXPO_NO_TELEMETRY="1", EXPO_NO_GIT_STATUS="1")

    def run(self, args: list[str], *, cwd: Path | None = None, timeout=180, check=True) -> str:
        remaining = min(timeout, self.deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("Native evaluation deadline exceeded")
        self.index += 1
        log = self.output / "logs" / f"{self.index:03d}-{Path(args[0]).name}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        # Files avoid waiting for pipe EOF from a daemon started by a tool.
        with log.open("w+") as stream:
            process = subprocess.Popen(args, cwd=cwd, env=self.env, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                process.wait(timeout=remaining)
            except BaseException:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise
            stream.seek(0)
            result = stream.read()
        if check and process.returncode:
            raise subprocess.CalledProcessError(process.returncode, args, output=str(log))
        return result


def execute(output: Path, *, timeout=3000) -> dict:
    from expo_harbor_evals.mobile_scenarios import Driver, run_scenario, validate_result

    spec = json.loads((output / "input.json").read_text())
    app = output / "app"
    if hashes(app / "submitted") != spec["submission"]:
        raise ValueError("Prepared candidate source changed")
    for name, expected in spec["template"].items():
        if digest((app / name).read_bytes()) != expected:
            raise ValueError("Prepared native toolchain changed")
    if digest(Path(__file__).with_name("mobile_scenarios.py").read_bytes()) != spec["scenario_sha256"]:
        raise ValueError("Native scenario changed after preparation")
    cmd = Commands(output, timeout)
    session = "harbor-" + uuid.uuid4().hex[:12]
    device = None
    driver = None
    checks = []
    errors = []
    stage = "toolchain"
    status = "infra-error"
    try:
        if sys.platform != "darwin":
            raise RuntimeError("Native execution needs an EAS macOS worker or local Mac")
        for binary in ("node", "npm", "npx", "pod", "xcodebuild", "xcrun", "agent-device"):
            if not shutil.which(binary):
                raise RuntimeError(f"Missing native evaluation tool: {binary}")
        versions = {binary: cmd.run([binary, "--version"]) for binary in ("node", "npm", "pod", "agent-device")}
        versions["xcode"] = cmd.run(["xcodebuild", "-version"])
        if versions["agent-device"].strip().lstrip("v") != "0.19.3":
            raise RuntimeError("Native scenarios require agent-device 0.19.3")
        write_json(output / "toolchain.json", versions)
        cmd.run(["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=app, timeout=600)
        cmd.run(["npx", "--no-install", "expo", "prebuild", "--platform", "ios", "--no-install",
                 "--skip-dependency-update", "react,react-native"], cwd=app, timeout=300)
        cmd.run(["pod", "install"], cwd=app / "ios", timeout=600)
        shutil.copy2(app / "ios/Podfile.lock", output / "Podfile.lock")
        runtimes = json.loads(cmd.run(["xcrun", "simctl", "list", "runtimes", "-j"]))["runtimes"]
        available = [r for r in runtimes if r.get("isAvailable") and ".iOS-" in r["identifier"]
                     and (not os.environ.get("SIMBENCH_RUNTIME") or os.environ["SIMBENCH_RUNTIME"] in (r["identifier"], r["version"]))]
        if not available:
            raise RuntimeError("No requested iOS runtime installed")
        runtime = max(available, key=lambda r: tuple(map(int, r["version"].split("."))))
        device = cmd.run(["xcrun", "simctl", "create", session,
                          "com.apple.CoreSimulator.SimDeviceType.iPhone-17", runtime["identifier"]]).strip()
        write_json(output / "device.json", {"device": device, "session": session,
                                           "runtime": runtime["identifier"]})
        cmd.run(["xcrun", "simctl", "boot", device])
        cmd.run(["xcrun", "simctl", "bootstatus", device, "-b"])
        workspace = list((app / "ios").glob("*.xcworkspace"))
        if len(workspace) != 1:
            raise RuntimeError("Prebuild did not produce one Xcode workspace")
        stage = "candidate-build"
        try:
            cmd.run(["xcodebuild", "-workspace", str(workspace[0]), "-scheme", "HarborCandidate",
                     "-configuration", "Release", "-sdk", "iphonesimulator",
                     "-destination", f"id={device}", "-derivedDataPath", str(output / "derived"),
                     "CODE_SIGNING_ALLOWED=NO", "build"], cwd=app, timeout=1200)
        except subprocess.CalledProcessError as exc:
            raise CandidateFailure(f"Candidate build failed; inspect {exc.output}") from exc
        binary = output / "derived/Build/Products/Release-iphonesimulator/HarborCandidate.app"
        with (binary / "Info.plist").open("rb") as stream:
            info = plistlib.load(stream)
        if info.get("CFBundleIdentifier") != BUNDLE:
            raise RuntimeError("Built app has an unexpected bundle identifier")
        write_json(output / "build.json", {"executable_sha256": digest((binary / info["CFBundleExecutable"]).read_bytes()),
            "js_bundle_sha256": digest((binary / "main.jsbundle").read_bytes()), "bundle_id": BUNDLE})
        checks.append({"name": "candidate-build", "passed": True})
        stage = "native-ui"
        cmd.run(["xcrun", "simctl", "install", device, str(binary)])
        # The picker fixture is a bundled PNG added to this trial's fresh library.
        if spec["profile"] == "picker":
            cmd.run(["xcrun", "simctl", "addmedia", device, str(app / "fixture.png")])
        driver = Driver(cmd, session, output)
        driver.command("open", BUNDLE, "--platform", "ios", "--device", session)
        run_scenario(spec["profile"], driver, checks)
        validate_result({"status": "passed", "input": spec, "checks": checks, "errors": []})
        status = "passed"
    except (CandidateFailure, AssertionError) as exc:
        status = "failed"
        checks.append({"name": stage, "passed": False, "notes": str(exc)})
    except Exception as exc:
        errors.append(f"{stage}: {type(exc).__name__}: {exc}")
    finally:
        if driver is not None and status != "passed":
            # Evidence collection must not obscure the original failure.
            cmd.deadline = time.monotonic() + 15
            with contextlib.suppress(Exception):
                driver.command("screenshot", str(output / "failure.png"))
        if device:
            # Cleanup gets its own bounded allowance after the evaluation deadline.
            cmd.deadline = time.monotonic() + 120
            try:
                cmd.run(["agent-device", "close", "--session", session], timeout=30, check=False)
                cmd.run(["xcrun", "simctl", "shutdown", device], timeout=30, check=False)
                cmd.run(["xcrun", "simctl", "delete", device], timeout=30)
            except Exception as exc:
                errors.append(f"cleanup: {type(exc).__name__}")
                status = "infra-error"
        result = {"schema_version": 1, "kind": "native-ui", "status": status,
                  "task": spec["task"], "trial_id": spec["trial_id"],
                  "backend": os.environ.get("SIMBENCH_BACKEND", "local-macos"),
                  "input": spec, "checks": checks, "errors": errors}
        write_json(output / "details.json", result)
        write_json(output / "reward.json", {"reward": float(status == "passed"),
                   "mobile_runner_ok": float(status != "infra-error")})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "execute"))
    parser.add_argument("--task", choices=sorted(PROFILES))
    parser.add_argument("--task-file", type=Path, help="Harbor task's runtime.json")
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=3000)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.timeout < 1:
        parser.error("timeout must be positive")
    if args.command != "execute":
        task = args.task or (json.loads(args.task_file.read_text())["task"] if args.task_file else None)
        if not task or not args.candidate:
            parser.error("prepare/run need --task (or --task-file) and --candidate")
        try:
            prepare(task, args.candidate.resolve(), output)
        except CandidateFailure as exc:
            output.mkdir(parents=True, exist_ok=False)
            write_json(output / "details.json", {"schema_version": 1, "kind": "native-ui",
                "task": task, "status": "failed", "checks": [
                    {"name": "candidate-workspace", "passed": False, "notes": str(exc)}],
                "errors": [], "validation_status": "requires-native-calibration"})
            write_json(output / "reward.json", {"reward": 0.0, "mobile_runner_ok": 1.0})
            parser.exit(1, f"Candidate failed preparation: {exc}\n")
        except (ValueError, OSError) as exc:
            parser.exit(2, f"Native preparation failed: {exc}\n")
    if args.command == "prepare":
        print(f"Prepared candidate at {output}; no build or simulator was started")
        return
    try:
        result = execute(output, timeout=args.timeout)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"Native input validation failed: {exc}\n")
    print(f"Native evaluation {result['status']}: {output / 'details.json'}")
    raise SystemExit({"passed": 0, "failed": 1, "infra-error": 2}[result["status"]])
