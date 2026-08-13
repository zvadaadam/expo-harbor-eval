"""Development-only Harbor agent that drives the host's logged-in muse CLI.

Muse Code (Meta's terminal coding agent, ``muse``) ships a headless mode —
``muse exec`` — that this agent drives the way ClaudeHostAgent drives
``claude --print``: on the host, with the CLI's own credentials (``muse
login`` browser sign-in or ``muse auth set``). There is no Harbor built-in
for muse; use this only for local sweeps under MacSandboxEnvironment.

Flag choices, all deliberate (verified against Muse Code 0.1.0):

- ``--yolo`` turns off muse's own approval prompts and sandbox (its sandbox
  is bubblewrap, Linux-only anyway); write containment belongs to the
  seatbelt environment, matching how the claude cells run.
- ``--no-foreign-personal-context``: by default muse ingests the host's
  personal Claude Code / Codex skills ("Including your 38 ... skills"),
  which would leak Adam's Expo guidance into trials. Always excluded.
- ``--disable-web-tools`` for parity with the claude cells, which expose no
  web tools.
- ``--disable-shell`` unless ``allow_shell=True``: muse has no allowed-tools
  list, so this is the only CLI-side way to hold the codegen tasks to
  file-edit-only discipline. Simbench cells set ``allow_shell: true`` — the
  simulator driver CLIs are the whole point there.

The model is selected with ``model_name``, optionally suffixed with a
reasoning effort and/or a ``#variant`` results tag, mirroring the claude
agent's scheme: ``muse-spark-1.2``, ``muse-spark-1.2@low#agent-device``.
Muse's stdout is JSONL session events; the run is healthy only if a
``run.terminal.*`` event reports ``completed``. Token/cost extraction is
best-effort until the first authed run pins the meta-provider event shape —
absent usage stays ``None`` (never a fake $0), which report/export already
handle.
"""

from __future__ import annotations

import json
import shlex
from typing import Any, override

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

EFFORT_LEVELS = ("none", "minimal", "low", "medium", "high", "xhigh", "ultra")

PROMPT_PREFACE = (
    "You are working in this task's app directory, which the instructions call "
    "/app. It is your current working directory; use relative paths. Only read "
    "and edit files inside it; shell commands are disabled for this task.\n\n"
)

_USAGE_INPUT_KEYS = ("input_tokens", "prompt_tokens")
_USAGE_OUTPUT_KEYS = ("output_tokens", "completion_tokens")
_USAGE_CACHE_KEYS = ("cached_input_tokens", "cache_read_input_tokens")
_COST_KEYS = ("total_cost_usd", "cost_usd")


def _find_usage_like(node: Any) -> dict | None:
    """Depth-first search for a dict that looks like a token-usage block."""
    if isinstance(node, dict):
        if any(k in node for k in _USAGE_INPUT_KEYS) and any(
            k in node for k in _USAGE_OUTPUT_KEYS
        ):
            return node
        for value in node.values():
            found = _find_usage_like(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_usage_like(value)
            if found is not None:
                return found
    return None


def _find_cost(node: Any) -> float | None:
    if isinstance(node, dict):
        for key in _COST_KEYS:
            if isinstance(node.get(key), (int, float)):
                return float(node[key])
        for value in node.values():
            found = _find_cost(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_cost(value)
            if found is not None:
                return found
    return None


def summarize_events(jsonl_text: str) -> dict:
    """Reduce a ``muse exec --json`` JSONL stream to the fields Harbor needs.

    Returns n_events=0 when nothing on the stream parses as an event — the
    caller must treat that as a failed trial, mirroring the claude agent's
    missing-envelope guard. ``usage``/``cost_usd`` come from the last
    usage-looking payload (assumed cumulative; re-check on muse upgrades).
    """
    n_events = 0
    session_id = None
    terminal = None
    terminal_reason = None
    final_text = None
    usage: dict | None = None
    cost_usd: float | None = None

    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        n_events += 1

        stream = event.get("stream") or {}
        if session_id is None and stream.get("kind") == "session":
            session_id = stream.get("id")

        payload = event.get("payload") or {}
        payload_type = str(event.get("payload_type") or "")
        if payload_type.startswith("run.terminal"):
            terminal = payload.get("terminal")
            terminal_reason = payload.get("reason")
            final_text = payload.get("text")

        found_usage = _find_usage_like(payload)
        if found_usage is not None:
            usage = found_usage
        found_cost = _find_cost(payload)
        if found_cost is not None:
            cost_usd = found_cost

    return {
        "n_events": n_events,
        "session_id": session_id,
        "terminal": terminal,
        "terminal_reason": terminal_reason,
        "final_text": final_text,
        "usage": usage,
        "cost_usd": cost_usd,
    }


def _usage_value(usage: dict | None, keys: tuple[str, ...]) -> int | None:
    if not usage:
        return None
    for key in keys:
        if isinstance(usage.get(key), int):
            return usage[key]
    return None


class MuseHostAgent(BaseAgent):
    def __init__(
        self,
        *args,
        reasoning_effort: str | None = None,
        allow_shell: bool = False,
        max_model_steps: int | None = None,
        preface: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        model = self._parsed_model_name or ""
        # "#tag" distinguishes otherwise-identical configs (e.g. the same
        # model driving different simulator tools) in results; it is not
        # passed to the CLI.
        self._variant = None
        if "#" in model:
            model, self._variant = model.split("#", 1)
        if "@" in model:
            model, suffix = model.split("@", 1)
            reasoning_effort = reasoning_effort or suffix
        if reasoning_effort is not None and reasoning_effort not in EFFORT_LEVELS:
            raise ValueError(
                f"reasoning_effort must be one of {EFFORT_LEVELS}, "
                f"got {reasoning_effort!r}"
            )
        if max_model_steps is not None and max_model_steps <= 0:
            raise ValueError(f"max_model_steps must be positive, got {max_model_steps}")
        self._cli_model = model or None
        self._effort = reasoning_effort
        self._allow_shell = allow_shell
        self._max_model_steps = max_model_steps
        self._preface = PROMPT_PREFACE if preface is None else preface
        self._muse_version: str | None = None

    @staticmethod
    @override
    def name() -> str:
        return "muse-host"

    @override
    def version(self) -> str | None:
        return self._muse_version

    @override
    async def setup(self, environment: BaseEnvironment) -> None:
        result = await environment.exec(command="command -v muse")
        if result.return_code != 0:
            raise RuntimeError(
                "muse CLI not found on the host PATH "
                "(install: curl -fsSL https://dev.meta.ai/install.sh | bash)"
            )
        version = await environment.exec(command="muse --version")
        if version.return_code == 0:
            self._muse_version = (version.stdout or "").strip() or None

    def _build_command(self, prompt: str) -> str:
        command = (
            "muse exec --json --yolo --no-foreign-personal-context "
            "--disable-web-tools "
        )
        if not self._allow_shell:
            command += "--disable-shell "
        if self._cli_model:
            command += f"--model {shlex.quote(self._cli_model)} "
        if self._effort:
            command += f"--reasoning-effort {self._effort} "
        if self._max_model_steps:
            command += f"--max-model-steps {self._max_model_steps} "
        command += (
            f"-- {shlex.quote(prompt)} "
            "> /logs/agent/muse-host.jsonl 2> /logs/agent/muse-host-stderr.txt"
        )
        return command

    @override
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        result = await environment.exec(command=self._build_command(self._preface + instruction))

        read_back = await environment.exec(command="cat /logs/agent/muse-host.jsonl")
        summary = summarize_events(read_back.stdout or "")
        usage = summary["usage"]

        context.n_input_tokens = _usage_value(usage, _USAGE_INPUT_KEYS)
        context.n_cache_tokens = _usage_value(usage, _USAGE_CACHE_KEYS)
        context.n_output_tokens = _usage_value(usage, _USAGE_OUTPUT_KEYS)
        context.cost_usd = summary["cost_usd"]
        context.metadata = {
            "cli_model": self._cli_model,
            "variant": self._variant,
            "reasoning_effort": self._effort,
            "muse_version": self._muse_version,
            "session_id": summary["session_id"],
            "terminal": summary["terminal"],
            "n_events": summary["n_events"],
            "exit_code": result.return_code,
        }

        if summary["terminal"] is not None and summary["terminal"] != "completed":
            raise RuntimeError(
                f"muse run terminal state {summary['terminal']!r} "
                f"(reason: {str(summary['terminal_reason'])[:200]})"
            )
        stderr_tail = ""
        if result.return_code != 0 or summary["n_events"] == 0:
            stderr = await environment.exec(
                command="tail -c 400 /logs/agent/muse-host-stderr.txt"
            )
            stderr_tail = stderr.stdout or ""
        if result.return_code != 0:
            raise RuntimeError(
                f"muse CLI exited with code {result.return_code}: {stderr_tail}"
            )
        if summary["n_events"] == 0:
            # A zero exit with no parseable events must not read as a healthy
            # trial: it would record success with no usage, cost, or output.
            raise RuntimeError(
                "muse CLI exited 0 but /logs/agent/muse-host.jsonl has no "
                f"parseable session events: {stderr_tail!r}"
            )
        if summary["terminal"] is None:
            raise RuntimeError(
                "muse CLI exited 0 but the event stream has no run.terminal "
                "event — the run did not finish cleanly"
            )
