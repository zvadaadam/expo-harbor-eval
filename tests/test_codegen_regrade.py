import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from harbor.models.task.config import EnvironmentConfig
from harbor.models.trial.paths import TrialPaths

from expo_harbor_evals.codegen_regrade import recover_legacy_trial
from expo_harbor_evals.local_env import LocalHostEnvironment


@pytest.mark.parametrize("verifier_session,definition_name", [
    ("trial__verifier__default", "environment"), ("regrade__env", "tests"),
])
def test_verifier_uses_fresh_root_and_preserves_candidate_deletions(tmp_path, verifier_session, definition_name):
    definition = tmp_path / definition_name
    definition.mkdir()
    (definition / "deleted.js").write_text("baseline")
    (definition / "test.sh").write_text("trusted verifier")
    args = dict(environment_dir=definition, environment_name="task",
                trial_paths=TrialPaths(trial_dir=tmp_path / "trial"),
                task_env_config=EnvironmentConfig(workdir="/app"))
    # The agent always gets environment/; a regrade's only environment is tests/.
    agent_definition = tmp_path / "agent-environment"
    import shutil
    shutil.copytree(definition, agent_definition)
    agent = LocalHostEnvironment(session_id="trial__env", **{**args, "environment_dir": agent_definition})
    verifier = LocalHostEnvironment(session_id=verifier_session, **args)

    async def run():
        await agent.start(False)
        app = agent._map_path("/app")
        (app / "deleted.js").unlink()
        (app / "test.sh").unlink()
        (app / "candidate.js").write_text("actual candidate")
        (app / ".env.local").write_text("must not export")
        (app / "node_modules").mkdir()
        (app / "node_modules/cached.js").write_text("dependency")
        artifact = tmp_path / "artifact"
        await agent.download_dir_with_exclusions(source_dir="/app", target_dir=artifact,
                                                 exclude=[".env.*", "node_modules"])
        assert sorted(p.name for p in artifact.iterdir()) == ["candidate.js"]
        await verifier.start(False)
        assert verifier._map_path("/tests/test.sh").read_text() == "trusted verifier"
        assert verifier._root != agent._root
        assert (app / "candidate.js").read_text() == "actual candidate"
        await verifier.upload_dir(artifact, "/app")
        assert not verifier._map_path("/app/deleted.js").exists()
        assert verifier._map_path("/app/candidate.js").read_text() == "actual candidate"
        await verifier.stop(True)
        assert (app / "candidate.js").exists()

    asyncio.run(run())


def make_legacy(tmp_path):
    source = tmp_path / "old-trial"
    app = source / "_local_env/app"
    app.mkdir(parents=True)
    (app / "policy.js").write_text("module.exports = 1;")
    (source / "result.json").write_text(json.dumps({"finished_at": "2026-09-16T00:00:00Z", "exception_info": None}))
    task = tmp_path / "task"
    task.mkdir()
    (task / "task.toml").write_text('artifacts = [{source="/app", destination="app", exclude=[]}]')
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps({"trials": [{"task": "task", "trial": "runs/old-trial",
        "source_sha256": {"policy.js": hashlib.sha256((app / "policy.js").read_bytes()).hexdigest()}}]}))
    return source, task, audit


def test_legacy_recovery_preserves_original_and_binds_recorded_hashes(tmp_path):
    source, task, audit = make_legacy(tmp_path)
    before = (source / "result.json").read_bytes()
    recovered = recover_legacy_trial(source, tmp_path / "recovered", audit, task)
    assert (source / "result.json").read_bytes() == before
    assert not (source / "artifacts").exists()
    assert (recovered / "artifacts/app/policy.js").read_text() == "module.exports = 1;"
    manifest = json.loads((recovered / "artifacts/manifest.json").read_text())
    assert manifest[0]["source"] == "/app"
    assert manifest[0]["exclude"] == []
    provenance = json.loads((recovered / "recovery.json").read_text())
    assert provenance["source_result_sha256"] == hashlib.sha256(before).hexdigest()
    with pytest.raises(FileExistsError):
        recover_legacy_trial(source, recovered, audit, task)


def test_changed_legacy_candidate_cannot_be_regraded_as_original(tmp_path):
    source, task, audit = make_legacy(tmp_path)
    (source / "_local_env/app/policy.js").write_text("changed after pilot")
    with pytest.raises(ValueError, match="recorded source hashes"):
        recover_legacy_trial(source, tmp_path / "recovered", audit, task)
    assert not (tmp_path / "recovered").exists()
