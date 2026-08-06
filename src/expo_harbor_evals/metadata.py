"""Controlled vocabulary for task metadata, enforced by tests.

Every task.toml [metadata] section must carry: family, category, tier,
difficulty, and motivation (why the task exists — a link, ticket, or thread
reference). Fixed vocabularies keep the viewer's filters and the report's
groupings meaningful as the task count grows.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

FAMILIES = {"expo-codegen", "simbench", "eas-bridge"}

CATEGORIES = {
    # expo-codegen: upstream eval category
    "expo-sdk",
    "expo-router",
    "expo-ui",
    # expo-codegen: authored from field-reported failures (Expo skills feedback)
    "expo-feedback",
    # simulator-use benchmark
    "simbench",
    # EAS evaluator bridge
    "mobile-eval",
}

TIERS = {
    # expo-codegen
    "code-gen",
    # simbench, in ascending difficulty
    "forms-and-keyboard",
    "scroll-and-find",
    "keyboard-occlusion",
    "gesture-precision",
    "async-patience",
    "vision-no-tree",
    # simbench flow tier: multi-step sequences over the atomic tiers
    "app-flows",
    # eas-bridge
    "result-import",
}

DIFFICULTIES = {"easy", "medium", "hard", "mixed"}

REQUIRES_TAGS = {
    "macos-host",
    "xcode-simulator",
    "agent-device-cli",
    "docker",
}

REQUIRED_KEYS = ("family", "category", "tier", "difficulty", "motivation")


def validate_task_metadata(task_toml: Path) -> list[str]:
    """Return a list of violations for one task.toml (empty when valid)."""
    metadata = tomllib.loads(task_toml.read_text()).get("metadata", {})
    problems: list[str] = []
    for key in REQUIRED_KEYS:
        if not metadata.get(key):
            problems.append(f"missing metadata.{key}")
    checks = (
        ("family", FAMILIES),
        ("category", CATEGORIES),
        ("tier", TIERS),
        ("difficulty", DIFFICULTIES),
    )
    for key, allowed in checks:
        value = metadata.get(key)
        if value and value not in allowed:
            problems.append(f"metadata.{key}={value!r} not in {sorted(allowed)}")
    for tag in metadata.get("requires", []):
        if tag not in REQUIRES_TAGS:
            problems.append(f"metadata.requires tag {tag!r} not in {sorted(REQUIRES_TAGS)}")
    return problems
