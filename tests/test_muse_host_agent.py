"""MuseHostAgent contract tests: model-spec parsing, the exact CLI flag set,
and the JSONL event summary.

The flag set is the fragile surface against Muse Code 0.1.0 churn — these
tests pin the safety-relevant flags (no personal-skill ingestion, no web
tools, shell only when a cell opts in) so an upgrade or edit that drops one
breaks loudly. Event fixtures mirror the real ``muse exec --json`` stream
captured from 0.1.0's echo provider.
"""

from __future__ import annotations

import importlib
import json
import shlex
from pathlib import Path

import pytest
import yaml

from expo_harbor_evals.muse_host_agent import MuseHostAgent, summarize_events

REPO = Path(__file__).resolve().parents[1]
MUSE_JOB_YAMLS = (REPO / "jobs/simbench-muse.yaml", REPO / "jobs/codegen-muse.yaml")


def _agent(tmp_path: Path, model_name: str, **kwargs) -> MuseHostAgent:
    return MuseHostAgent(logs_dir=tmp_path, model_name=model_name, **kwargs)


def _event(payload_type: str, payload: dict, session: str = "sess-1") -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "stream": {"kind": "session", "id": session},
            "record_type": "event",
            "payload_type": payload_type,
            "payload": payload,
        }
    )


def test_model_spec_splits_effort_and_variant(tmp_path: Path) -> None:
    agent = _agent(tmp_path, "muse-spark-1.2@low#agent-device")
    assert agent._cli_model == "muse-spark-1.2"
    assert agent._effort == "low"
    assert agent._variant == "agent-device"

    bare = _agent(tmp_path, "muse-spark-1.2")
    assert bare._cli_model == "muse-spark-1.2"
    assert bare._effort is None
    assert bare._variant is None


def test_invalid_effort_and_steps_raise(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="reasoning_effort"):
        _agent(tmp_path, "muse-spark-1.2@turbo")
    with pytest.raises(ValueError, match="max_model_steps"):
        _agent(tmp_path, "muse-spark-1.2", max_model_steps=0)


def test_command_pins_safety_flags(tmp_path: Path) -> None:
    agent = _agent(tmp_path, "muse-spark-1.2@low", max_model_steps=200)
    command = agent._build_command("do the task")
    for flag in (
        "muse exec --json",
        "--yolo",
        "--no-foreign-personal-context",
        "--disable-web-tools",
        "--disable-shell",
        "--model muse-spark-1.2",
        "--reasoning-effort low",
        "--max-model-steps 200",
        f"-- {shlex.quote('do the task')}",
        "> /logs/agent/muse-host.jsonl",
    ):
        assert flag in command, f"missing {flag!r}"


def test_allow_shell_drops_only_the_shell_restriction(tmp_path: Path) -> None:
    command = _agent(tmp_path, "muse-spark-1.2", allow_shell=True)._build_command("x")
    assert "--disable-shell" not in command
    assert "--no-foreign-personal-context" in command
    assert "--disable-web-tools" in command


def test_summarize_events_reads_terminal_session_and_usage() -> None:
    lines = "\n".join(
        [
            _event("runtime.command.accepted", {"kind": "command_accepted"}),
            _event(
                "model.turn.usage",
                {
                    "usage": {
                        "input_tokens": 700,
                        "cached_input_tokens": 5000,
                        "output_tokens": 19,
                    },
                    "total_cost_usd": 0.12,
                },
            ),
            _event(
                "run.terminal.completed",
                {"terminal": "completed", "text": "done", "reason": None},
            ),
        ]
    )
    summary = summarize_events(lines)
    assert summary["n_events"] == 3
    assert summary["session_id"] == "sess-1"
    assert summary["terminal"] == "completed"
    assert summary["final_text"] == "done"
    assert summary["usage"]["input_tokens"] == 700
    assert summary["cost_usd"] == 0.12


def test_summarize_events_surfaces_failure_and_garbage() -> None:
    failed = summarize_events(
        _event("run.terminal.failed", {"terminal": "failed", "reason": "step limit"})
    )
    assert failed["terminal"] == "failed"
    assert failed["terminal_reason"] == "step limit"

    garbage = summarize_events("not json\n\x00\n")
    assert garbage["n_events"] == 0
    assert garbage["terminal"] is None


def test_muse_job_yamls_construct_the_agent(tmp_path: Path) -> None:
    """Every muse agent entry in the job yamls must instantiate cleanly, so a
    kwarg typo in a yaml fails here instead of at trial time."""
    seen = 0
    for path in MUSE_JOB_YAMLS:
        config = yaml.safe_load(path.read_text())
        for entry in config["agents"]:
            module_name, class_name = entry["import_path"].split(":")
            cls = getattr(importlib.import_module(module_name), class_name)
            agent = cls(
                logs_dir=tmp_path,
                model_name=entry["model_name"],
                **entry.get("kwargs", {}),
            )
            assert agent._cli_model == "muse-spark-1.2"
            seen += 1
    assert seen == 4
