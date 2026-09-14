"""The bounded pilot must retain served-model evidence and tool restrictions."""

import asyncio
import json
import shlex
from pathlib import Path
from types import SimpleNamespace

import yaml
from harbor.models.agent.context import AgentContext
from harbor.models.job.config import JobConfig

from expo_harbor_evals.claude_host_agent import ClaudeHostAgent

ROOT = Path(__file__).resolve().parents[1]


def test_pilot_selects_exactly_four_attempts_without_retries(tmp_path):
    config = JobConfig.model_validate(yaml.safe_load((ROOT / "jobs/codegen/new-feedback-pilot.yaml").read_text()))
    tasks = asyncio.run(config.datasets[0].get_task_configs())
    assert {t.path.name for t in tasks} == {
        "feedback-12-native-fixed-amount-column", "feedback-13-auth-field-render-path"}
    assert len(tasks) * len(config.agents) * config.n_attempts == 4
    assert config.retry.max_retries == 0
    assert config.verifier.env["REWARDKIT_MODEL"] == "claude-sonnet-5"
    for entry in config.agents:
        agent = ClaudeHostAgent(logs_dir=tmp_path, model_name=entry.model_name, **entry.kwargs)
        assert agent._clean_config
        assert agent._cli_model in {"claude-sonnet-5", "claude-haiku-4-5-20251001"}
        if "haiku" in agent._cli_model:
            assert agent._effort is None  # Haiku has no effort axis.


def test_clean_config_restricts_tools_and_records_served_model(tmp_path):
    envelope = {"is_error": False, "usage": {"input_tokens": 12, "output_tokens": 34},
                "total_cost_usd": 0.03, "modelUsage": {"claude-sonnet-5": {"costUSD": 0.03}}}
    commands = []

    class Environment:
        async def exec_agent(self, command):
            commands.append(shlex.split(command))
            return SimpleNamespace(return_code=0)

        async def exec(self, command):
            return SimpleNamespace(stdout=json.dumps(envelope))

    agent = ClaudeHostAgent(logs_dir=tmp_path, model_name="claude-sonnet-5@medium", clean_config=True)
    context = AgentContext()
    asyncio.run(agent.run("Repair the app", Environment(), context))
    (command,) = commands
    assert "--safe-mode" in command and "--restricted" in command
    assert "--fallback-model" not in command
    assert "Bash" not in command[command.index("--tools") + 1].split()
    assert command[command.index("--mcp-config") + 1] == '{"mcpServers":{}}'
    assert context.metadata["model_usage"] == envelope["modelUsage"]
    assert context.cost_usd == 0.03 and context.n_output_tokens == 34
