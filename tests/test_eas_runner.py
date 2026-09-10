import io
import json
import os
import tarfile
from pathlib import Path

import pytest

from expo_harbor_evals.eas_runner import artifact_url, load_eas_config, prepare, unpack

REPO = Path(__file__).resolve().parents[1]


def tar(path, entries):
    with tarfile.open(path, "w:gz") as tf:
        for name, value in entries:
            data = json.dumps(value).encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


def test_artifact_shard_identity_and_traversal(tmp_path):
    archive = tmp_path / "shard.tar.gz"
    spec = {"shard_id": "correct"}
    tar(archive, [("manifest.json", {"shard_id": "wrong"})])
    with pytest.raises(ValueError, match="different source"):
        unpack(archive, tmp_path / "out", spec)
    tar(archive, [("manifest.json", spec), ("../escaped.json", {})])
    with pytest.raises(ValueError, match="unsafe"):
        unpack(archive, tmp_path / "out", spec)
    assert not (tmp_path / "escaped.json").exists()
    tar(archive, [("./manifest.json", spec), ("calibration/calibration.json", {"ok": True})])
    unpack(archive, tmp_path / "out", spec)
    assert json.loads((tmp_path / "out/manifest.json").read_text()) == spec


def test_artifacts_selected_by_identity_not_first_url():
    run = {"jobs": [{"artifacts": [{"name": "other", "downloadUrl": "wrong"},
                                   {"name": "simbench-evidence", "downloadUrl": "correct"}]}]}
    assert artifact_url(run) == "correct"
    run["jobs"] *= 2
    with pytest.raises(ValueError, match="Ambiguous"):
        artifact_url(run)


def test_prepared_upload_contains_only_selected_sources(tmp_path):
    target = tmp_path / "project"
    task = "simbench-ios-01-goldennotes-create-note"
    spec = prepare(REPO, target, "00000000-0000-0000-0000-000000000001", task, 1)
    assert spec["task"] == task
    assert (target / "src/expo_harbor_evals/simbench_env.py").exists()
    assert not (target / ".env").exists()
    assert not (target / ".env.local").exists()
    assert not (target / "src/expo_harbor_evals/sandbox_probe.py").exists()
    assert not (target / ".context").exists()
    assert not (target / "tasks/codegen").exists()
    assert list((target / "tasks/simbench").iterdir()) == [target / "tasks/simbench" / task]


def test_prepared_native_shard_binds_the_actual_candidate(tmp_path):
    task = "sdk-04-image-picker-canceled-assets-guard"
    target = tmp_path / "project"
    candidate = REPO / "tasks/codegen" / task / "solution/reference-alternative"
    spec = prepare(REPO, target, "00000000-0000-0000-0000-000000000001", task, 1, candidate=candidate)
    assert spec["kind"] == "candidate-eas-shard"
    assert (target / "NOTICE.md").read_bytes() == (REPO / "NOTICE.md").read_bytes()
    assert (target / "candidate/app/submitted/App.tsx").read_bytes() == (candidate / "App.tsx").read_bytes()
    assert "candidate/input.json" in spec["files"]
    assert not (target / ".env.local").exists()
    assert not (target / "tasks/simbench").exists()
    if (target / "suites/mobile-v2.json").exists():
        for filename in json.loads((target / "suites/mobile-v2.json").read_text())["engine"]:
            assert (target / filename).exists()


def test_local_config_precedence_and_literal_values(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "environ", {k: v for k, v in os.environ.items()
                        if k not in ("EXPO_TOKEN", "EAS_EVAL_PROJECT_ID", "UNRELATED_SETTING")})
    (tmp_path / ".env").write_text('EXPO_TOKEN=base-token\nEAS_EVAL_PROJECT_ID=base-project\n')
    (tmp_path / ".env.local").write_text(
        'EXPO_TOKEN="literal-${HOME}-$(touch marker)"\nUNRELATED_SETTING=ignored\n')
    load_eas_config(tmp_path)
    assert os.environ["EXPO_TOKEN"] == "literal-${HOME}-$(touch marker)"
    assert os.environ["EAS_EVAL_PROJECT_ID"] == "base-project"
    assert "UNRELATED_SETTING" not in os.environ
    monkeypatch.setenv("EXPO_TOKEN", "ci-token")
    load_eas_config(tmp_path)
    assert os.environ["EXPO_TOKEN"] == "ci-token"


def test_prepare_uses_dotenv_project_without_exposing_token(tmp_path, monkeypatch, capsys):
    import expo_harbor_evals.eas_runner as runner
    import sys
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(os, "environ", {k: v for k, v in os.environ.items()
                        if k not in ("EXPO_TOKEN", "EAS_EVAL_PROJECT_ID")})
    project_id = "00000000-0000-0000-0000-000000000001"
    (tmp_path / ".env.local").write_text(f'EXPO_TOKEN=test-secret\nEAS_EVAL_PROJECT_ID={project_id}\n')
    seen = []
    def fake_prepare(repo, destination, selected_id, task, attempts):
        seen.append(selected_id)
        return {"shard_id": "test-shard"}
    monkeypatch.setattr(runner, "prepare", fake_prepare)
    monkeypatch.setattr(sys, "argv", ["expo-eas-eval", "prepare", "--output", "payload"])
    runner.main()
    assert seen == [project_id]
    assert "test-secret" not in capsys.readouterr().out
    override = "00000000-0000-0000-0000-000000000002"
    monkeypatch.setattr(sys, "argv", ["expo-eas-eval", "prepare", "--output", "payload", "--project-id", override])
    runner.main()
    assert seen[-1] == override


def test_prepare_missing_project_has_actionable_error(tmp_path, monkeypatch, capsys):
    import expo_harbor_evals.eas_runner as runner
    import sys
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EAS_EVAL_PROJECT_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["expo-eas-eval", "prepare", "--output", "payload"])
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 2
    assert "EAS_EVAL_PROJECT_ID in .env.local" in capsys.readouterr().err
    assert not (tmp_path / "payload").exists()
