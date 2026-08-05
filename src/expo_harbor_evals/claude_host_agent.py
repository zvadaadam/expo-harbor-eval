"""Development-only Harbor agent that drives the host's logged-in claude CLI.

Harbor's built-in claude-code agent isolates CLAUDE_CONFIG_DIR per trial, so it
needs ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN. This agent instead runs the
host `claude` binary with its normal config (keychain/subscription auth), which
matches how this repo's LocalHostEnvironment already executes on the host. Use
it only for local model/effort sweeps; real benchmarking should use Docker and
the built-in claude-code agent with explicit credentials.

The model is selected with ``model_name``, optionally suffixed with an effort
level: ``haiku``, ``sonnet@low``, ``fable@high``. ``reasoning_effort`` in agent
kwargs overrides the suffix.
"""

from __future__ import annotations

import json
import shlex
from typing import override

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")

# The imported tasks only require reading and editing files in the workspace;
# withholding Bash keeps a host-executed agent from running arbitrary commands.
ALLOWED_TOOLS = "Read Write Edit MultiEdit Glob Grep LS TodoWrite"

PROMPT_PREFACE = (
    "You are working in this task's app directory, which the instructions call "
    "/app. It is your current working directory; use relative paths. You can "
    "only read and edit files (no shell commands).\n\n"
)


class ClaudeHostAgent(BaseAgent):
    def __init__(
        self,
        *args,
        reasoning_effort: str | None = None,
        allowed_tools: str | None = None,
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
        self._cli_model = model or None
        self._effort = reasoning_effort
        self._allowed_tools = allowed_tools or ALLOWED_TOOLS
        self._preface = PROMPT_PREFACE if preface is None else preface

    @staticmethod
    @override
    def name() -> str:
        return "claude-host"

    @override
    def version(self) -> str | None:
        return None

    @override
    async def setup(self, environment: BaseEnvironment) -> None:
        result = await environment.exec(command="command -v claude")
        if result.return_code != 0:
            raise RuntimeError("claude CLI not found on the host PATH")

    @override
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        prompt = self._preface + instruction
        command = (
            "claude --print --output-format json "
            "--permission-mode acceptEdits "
            f"--allowedTools {shlex.quote(self._allowed_tools)} "
        )
        if self._cli_model:
            command += f"--model {shlex.quote(self._cli_model)} "
        if self._effort:
            command += f"--effort {self._effort} "
        command += (
            f"-- {shlex.quote(prompt)} "
            "> /logs/agent/claude-host.json 2> /logs/agent/claude-host-stderr.txt"
        )

        result = await environment.exec(command=command)

        envelope: dict = {}
        read_back = await environment.exec(command="cat /logs/agent/claude-host.json")
        try:
            envelope = json.loads(read_back.stdout or "")
        except (ValueError, TypeError):
            pass

        usage = envelope.get("usage") or {}
        context.n_input_tokens = usage.get("input_tokens")
        context.n_cache_tokens = usage.get("cache_read_input_tokens")
        context.n_output_tokens = usage.get("output_tokens")
        context.cost_usd = envelope.get("total_cost_usd")
        context.metadata = {
            "cli_model": self._cli_model,
            "variant": self._variant,
            "reasoning_effort": self._effort,
            "is_error": envelope.get("is_error"),
            "num_turns": envelope.get("num_turns"),
            "exit_code": result.return_code,
        }

        if envelope.get("is_error"):
            raise RuntimeError(
                f"claude CLI reported an error: {str(envelope.get('result'))[:200]}"
            )
        if result.return_code != 0:
            raise RuntimeError(
                f"claude CLI exited with code {result.return_code}: "
                f"{(read_back.stdout or '')[:200]}"
            )
