"""Reference-copy validation for imported expo-codegen oracle runs.

This is deliberately not the benchmark verifier. It only proves that an
imported task's baseline, oracle solution, and Harbor plumbing agree.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileResult:
    path: str
    status: str


def compare_reference(
    workspace: Path,
    reference: Path,
) -> tuple[float, list[FileResult]]:
    reference_files = sorted(path for path in reference.rglob("*") if path.is_file())
    results: list[FileResult] = []

    for expected in reference_files:
        relative = expected.relative_to(reference)
        actual = workspace / relative
        if not actual.exists():
            status = "missing"
        elif not actual.is_file():
            status = "not-a-file"
        elif actual.read_bytes() == expected.read_bytes():
            status = "matched"
        else:
            status = "different"
        results.append(FileResult(path=relative.as_posix(), status=status))

    if not results:
        return 0.0, results

    matched = sum(result.status == "matched" for result in results)
    return matched / len(results), results


def write_result(
    workspace: Path,
    reference: Path,
    reward_path: Path,
    details_path: Path,
) -> float:
    score, files = compare_reference(workspace, reference)
    matched = sum(result.status == "matched" for result in files)

    reward_path.parent.mkdir(parents=True, exist_ok=True)
    reward_path.write_text(
        json.dumps(
            {
                "reward": score,
                "oracle_reference_match": score,
                "oracle_files_matched": matched,
                "oracle_files_total": len(files),
            },
            indent=2,
        )
        + "\n"
    )

    details_path.parent.mkdir(parents=True, exist_ok=True)
    details_path.write_text(
        json.dumps(
            {
                "mode": "reference-copy-smoke",
                "note": (
                    "This exact-reference check validates the imported oracle only; "
                    "it must not be used to score arbitrary agent implementations."
                ),
                "files": [asdict(result) for result in files],
            },
            indent=2,
        )
        + "\n"
    )
    return score


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("reward", type=Path)
    parser.add_argument("--details", required=True, type=Path)
    args = parser.parse_args()

    score = write_result(
        args.workspace,
        args.reference,
        args.reward,
        args.details,
    )
    print(f"Reference-copy score: {score:.4f}")


if __name__ == "__main__":
    main()
