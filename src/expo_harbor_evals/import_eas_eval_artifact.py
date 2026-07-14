from __future__ import annotations

import argparse
import json
import tarfile
import tempfile
from pathlib import Path

from expo_harbor_evals.scoring import normalize_evaluator_result, zero_reward


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "artifact", type=Path, help="result.json, eval-out dir, or eval-out.tar.gz"
    )
    parser.add_argument("reward", type=Path, help="Harbor reward.json to write")
    parser.add_argument("--details", type=Path, help="Optional details JSON path")
    args = parser.parse_args()

    details = {"ok": True, "errors": [], "artifact": str(args.artifact)}
    reward = zero_reward()
    try:
        result_path, raw = load_result(args.artifact)
        reward = normalize_evaluator_result(raw)
        details["result_path"] = str(result_path)
        details["test_overview"] = raw.get("test_overview")
    except Exception as exc:
        details["ok"] = False
        details["errors"].append(str(exc))

    args.reward.parent.mkdir(parents=True, exist_ok=True)
    args.reward.write_text(json.dumps(reward, indent=2) + "\n")
    if args.details:
        args.details.parent.mkdir(parents=True, exist_ok=True)
        args.details.write_text(json.dumps(details, indent=2) + "\n")


def load_result(path: Path) -> tuple[Path, dict]:
    result_path = resolve_result_path(path)
    if result_path is not None:
        return result_path, json.loads(result_path.read_text())

    if path.is_file() and path.suffixes[-2:] == [".tar", ".gz"]:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with tarfile.open(path, "r:gz") as tf:
                tf.extractall(root, filter="data")
            for candidate in root.rglob("result.json"):
                return candidate, json.loads(candidate.read_text())

    raise FileNotFoundError(f"Could not find evaluator result.json in {path}")


def resolve_result_path(path: Path) -> Path | None:
    if path.is_file() and path.name == "result.json":
        return path
    if path.is_dir():
        for candidate in (path / "result.json", path / "eval-out" / "result.json"):
            if candidate.exists():
                return candidate
    return None
