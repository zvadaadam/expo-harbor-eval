"""Build a portable task-review site from the actual task definitions."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path

WEB = Path(__file__).with_name("web")
REPOSITORY = "https://github.com/zvadaadam/expo-harbor-eval"
TEXT_SUFFIXES = {".md", ".py", ".sh", ".swift", ".tsx", ".ts", ".jsx", ".js", ".cjs", ".mjs", ".json", ".toml", ".yaml", ".yml", ".plist"}


def read_json(path: Path, default):
    return json.loads(path.read_text()) if path.is_file() else default


def task_files(task: Path, tracked: set[str]) -> list[dict]:
    files = []
    for path in sorted(task.rglob("*")):
        relative = path.relative_to(task)
        if not path.is_file() or path.is_symlink() or any(p in {"__pycache__", ".git"} for p in relative.parts):
            continue
        # Keep intentionally vendored teaching fixtures, never installed dependencies.
        if "node_modules" in relative.parts and str(path.resolve()) not in tracked:
            continue
        if path.suffix not in TEXT_SUFFIXES and path.name != "Dockerfile":
            continue
        if path.name in {"package-lock.json", "baseline-manifest.json"}:
            continue
        if relative.parts[0] == "environment":
            role = "Starting app"
        elif relative.parts[:2] == ("solution", "reference"):
            role = "Reference fix"
        elif relative.parts[:2] == ("solution", "reference-alternative"):
            role = "Alternative fix"
        elif relative.parts[:2] == ("solution", "distractor"):
            role = "Wrong fix"
        elif relative.parts[0] == "solution":
            role = "Scripted control"
        elif relative.parts[0] == "tests":
            if relative.parts[:2] == ("tests", "reference"):
                continue  # The verifier's identical reference copy adds no review context.
            role = "Verifier"
        else:
            continue
        content = path.read_text()
        files.append({"path": str(relative), "role": role, "content": content,
                      "language": path.suffix.lstrip("."), "lines": len(content.splitlines())})
    return files


def build_catalog(repo: Path) -> dict:
    tasks = []
    tracked_result = subprocess.run(["git", "ls-files", "-z", "--", "tasks"], cwd=repo,
                                    capture_output=True, check=False)
    tracked = {str((repo / p).resolve()) for p in tracked_result.stdout.decode().split("\0") if p}
    reviews = read_json(repo / "tasks/feedback-reviews.json", {"items": []})
    for path in sorted((repo / "tasks").rglob("task.toml")):
        task = path.parent
        definition = tomllib.loads(path.read_text())
        meta = definition["metadata"]
        rubric_file = task / "tests/requirements/rubric.toml"
        rubric = tomllib.loads(rubric_file.read_text()) if rubric_file.exists() else {}
        instruction = (task / "instruction.md").read_text()
        files = task_files(task, tracked)
        for name in meta.get("authoring_checks", []):
            check = (repo / name).resolve()
            if not check.is_relative_to(repo.resolve()) or check.suffix not in TEXT_SUFFIXES:
                raise ValueError(f"Invalid authoring check path: {name}")
            content = check.read_text()
            files.append({"path": name, "repositoryPath": name, "role": "Authoring check",
                          "content": content, "language": check.suffix.lstrip("."),
                          "lines": len(content.splitlines())})
        task_reviews = [item for item in reviews["items"] if any(
            task.name in f["taskIds"] for f in item["findings"])]
        title = re.sub(r"^(feedback|router|sdk|ui|simbench-ios)-\d+-", "", task.name)
        title = title.replace("goldennotes-", "").replace("goldenlab-", "").replace("-", " ")
        native = read_json(task / "tests/requirements/runtime.json", None)
        content_hash = hashlib.sha256(json.dumps([instruction, meta, rubric, files], sort_keys=True).encode()).hexdigest()
        tasks.append({
            "id": task.name, "title": title[0].upper() + title[1:],
            "path": str(task.relative_to(repo)), "instruction": instruction,
            "description": definition.get("task", {}).get("description", ""),
            "metadata": meta, "family": meta["family"], "category": meta["category"],
            "criteria": rubric.get("criterion", []), "files": files,
            "calibration": read_json(task / "tests/requirements/calibration.json", {}),
            "native": native, "reviews": task_reviews, "revision": content_hash,
            "validation": meta.get("validation_status", "not-recorded"),
        })
    return {"schemaVersion": 1, "repository": REPOSITORY, "tasks": tasks,
            "feedbackReview": reviews, "suite": read_json(repo / "suites/mobile-v2.json", {}).get("suite", "unversioned")}


def theme_css() -> str:
    css = "/*\n" + (WEB / "licenses.txt").read_text().replace("*/", "* /") + "\n*/\n"
    css += (WEB / "expo-theme.css").read_text()
    for name, family in [("inter-latin.woff2", "Inter"), ("jetbrains-mono-latin.woff2", "JetBrains Mono")]:
        font = WEB / name
        css += f"@font-face{{font-family:'{family}';font-weight:100 900;font-display:swap;src:url(data:font/woff2;base64,{base64.b64encode(font.read_bytes()).decode()}) format('woff2')}}"
    return css


def build_html(repo: Path, *, local_viewer: bool = False) -> str:
    data = build_catalog(repo)
    data["localViewer"] = local_viewer
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    css = theme_css() + (WEB / "catalog.css").read_text()
    return (WEB / "catalog.html").read_text().replace("/* CATALOG_CSS */", css).replace(
        "/* CATALOG_DATA */", payload).replace("/* CATALOG_JS */", (WEB / "catalog.js").read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("-o", "--output", type=Path, default=Path("outputs/catalog/index.html"))
    args = parser.parse_args()
    document = build_html(args.repo.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document)
    print(f"Task review site: {args.output.resolve()}")


if __name__ == "__main__":
    main()
