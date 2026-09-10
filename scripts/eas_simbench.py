"""Worker entry point; all task selection comes from the prepared source manifest."""

import json
import subprocess
import shutil
from pathlib import Path

from expo_harbor_evals.simbench_evidence import digest, write_json

spec = json.loads(Path("eval-source.json").read_text())
for name, checksum in spec["files"].items():
    if digest(Path(name).read_bytes()) != checksum:
        raise SystemExit(f"Source checksum mismatch: {name}")
write_json(Path("eval-output/manifest.json"), spec)
with Path("eval-output/toolchain.txt").open("w") as output:
    for command in (["xcodebuild", "-version"], ["agent-device", "--version"],
                    ["xcrun", "simctl", "list", "runtimes", "-j"]):
        subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, check=True)
if spec["kind"] == "candidate-eas-shard":
    shutil.copytree("candidate", "eval-output/native-eval")
    result = subprocess.run(["expo-mobile-eval", "execute", "--output", "eval-output/native-eval",
                             "--timeout", "2100"])
    # Keep evidence and dependency locks, not node_modules/Pods/build products.
    for name in ("app", "derived"):
        shutil.rmtree(Path("eval-output/native-eval") / name, ignore_errors=True)
else:
    result = subprocess.run([
        "expo-simbench-calibrate", "--task", spec["task"], "--attempts", str(spec["attempts"]),
        "--timeout", "2100", "--output", "eval-output/calibration",
    ])
raise SystemExit(result.returncode)
