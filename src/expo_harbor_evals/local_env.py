"""Development-only Harbor environment for machines without Docker.

This is not a sandbox. It executes commands on the host inside a per-trial
directory and exists only to make the Harbor task contract runnable locally.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import hashlib
import os
import signal
import shutil
from fnmatch import fnmatch
from pathlib import Path
from typing import override

from harbor.environments.base import BaseEnvironment, ExecResult
from harbor.environments.capabilities import EnvironmentCapabilities

from expo_harbor_evals.codegen_rewardkit_runner import SCAFFOLDING_FILES
from expo_harbor_evals.evaluation_identity import trial_identity
from expo_harbor_evals.simbench_evidence import write_json


class LocalHostEnvironment(BaseEnvironment):
    def __init__(self, *args, keep_root: bool = False, allow_unversioned_tasks: bool = False, **kwargs) -> None:
        self._allow_unversioned_tasks = allow_unversioned_tasks
        self._keep_root = keep_root
        self._root: Path | None = None
        super().__init__(*args, **kwargs)

    @staticmethod
    @override
    def type() -> str:
        return "local-host-dev"

    @property
    @override
    def capabilities(self) -> EnvironmentCapabilities:
        return EnvironmentCapabilities(mounted=False)

    @override
    def _validate_definition(self) -> None:
        self.environment_dir.mkdir(parents=True, exist_ok=True)

    @override
    async def start(self, force_build: bool) -> None:
        # Harbor starts a separate verifier while retaining the source env.
        # Each role needs its own root, or verifier setup deletes the candidate.
        verifier = "__verifier__" in self.session_id or self.environment_dir.name == "tests"
        suffix = "-" + hashlib.sha256(self.session_id.encode()).hexdigest()[:12] if verifier else ""
        self._root = self.trial_paths.trial_dir.resolve() / ("_local_env" + suffix)
        if self._root.exists():
            shutil.rmtree(self._root)
        for name in (
            "logs/agent",
            "logs/verifier",
            "logs/artifacts",
            "tests",
            "solution",
            "app",
        ):
            (self._root / name).mkdir(parents=True, exist_ok=True)
        if (self.environment_dir.parent / "task.toml").exists():
            config_path = self.trial_paths.config_path
            config = json.loads(config_path.read_text()) if config_path.exists() else {}
            job_path = self.trial_paths.trial_dir.parent / "config.json"
            job = json.loads(job_path.read_text()) if job_path.exists() else {}
            identity = trial_identity(self.environment_dir.parent, config, job, allow_unversioned=self._allow_unversioned_tasks)
            identity["backend"] = os.environ.get("SIMBENCH_BACKEND", self.type())
            write_json(self.trial_paths.trial_dir / "evaluation.json", identity)
        # There is no image build in this environment, so environment/ must
        # always be materialized into the workdir (a Dockerfile's `COPY . /app`
        # equivalent). Harbor's base helper only does this for prebuilt
        # docker_image tasks and would leave /app empty here.
        workdir_target = self._map_path(self.task_env_config.workdir or "/app")
        workdir_target.mkdir(parents=True, exist_ok=True)
        if verifier:
            # Harbor 0.23 builds separate verifiers from tests/ and skips
            # uploading tests afterwards. Materialize that image contract.
            shutil.copytree(self.environment_dir, self._map_path("/tests"),
                            dirs_exist_ok=True, ignore=shutil.ignore_patterns(*SCAFFOLDING_FILES))
        elif self.environment_dir.is_dir():
            shutil.copytree(
                self.environment_dir,
                workdir_target,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(*SCAFFOLDING_FILES),
            )

    @override
    async def stop(self, delete: bool) -> None:
        if delete and not self._keep_root and self._root and self._root.exists():
            shutil.rmtree(self._root)

    @override
    async def upload_file(self, source_path: Path | str, target_path: str) -> None:
        target = self._map_path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)

    @override
    async def upload_dir(self, source_dir: Path | str, target_dir: str) -> None:
        target = self._map_path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_dir, target, dirs_exist_ok=True)

    @override
    async def download_file(self, source_path: str, target_path: Path | str) -> None:
        source = self._map_path(source_path)
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)

    @override
    async def download_dir(self, source_dir: str, target_dir: Path | str) -> None:
        source = self._map_path(source_dir)
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, dirs_exist_ok=True)

    @override
    async def download_dir_with_exclusions(
        self, *, source_dir: str, target_dir: Path | str, exclude: list[str],
    ) -> None:
        """Copy local artifacts directly; container /tmp tar paths do not map here."""
        source = self._map_path(source_dir)
        def ignored(directory, names):
            relative = Path(directory).relative_to(source)
            skipped = [name for name in names if any(
                fnmatch(name, pattern) or fnmatch((relative / name).as_posix(), pattern)
                for pattern in exclude
            )]
            for name in set(names) - set(skipped):
                if (Path(directory) / name).is_symlink():
                    raise ValueError("Cannot capture symlinked submission artifacts")
            return skipped
        shutil.copytree(source, Path(target_dir), dirs_exist_ok=True, ignore=ignored, symlinks=True)

    def _wrap_command(self, mapped_command: str) -> str:
        """Hook for subclasses to wrap the mapped command (e.g. in a sandbox)."""
        return mapped_command

    @override
    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int | None = None,
        user: str | int | None = None,
    ) -> ExecResult:
        mapped_command = self._wrap_command(self._map_command(command))
        mapped_cwd = self._map_path(cwd) if cwd else self._default_cwd()
        mapped_cwd.mkdir(parents=True, exist_ok=True)

        run_env = os.environ.copy()
        run_env.update(
            {
                "HARBOR_LOCAL_ROOT": str(self._root),
                "HARBOR_LOGS_DIR": str(self._map_path("/logs")),
                "HARBOR_TESTS_DIR": str(self._map_path("/tests")),
                "HARBOR_SOLUTION_DIR": str(self._map_path("/solution")),
                "HARBOR_APP_DIR": str(self._map_path("/app")),
            }
        )
        merged = self._merge_env(env)
        if merged:
            run_env.update({key: str(value) for key, value in merged.items()})

        process = None
        try:
            process = await asyncio.create_subprocess_shell(
                mapped_command,
                cwd=str(mapped_cwd),
                env=run_env,
                executable="/bin/bash",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            stdout_b, stderr_b = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_sec,
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            # Shell children include the agent and its device commands. Killing
            # only the shell leaves them mutating state during verification.
            if process is not None:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                await process.communicate()
            raise
        stdout = stdout_b.decode(errors="replace") if stdout_b else None
        stderr = stderr_b.decode(errors="replace") if stderr_b else None
        callback = self._output_callback()
        if callback:
            if stdout:
                await callback(stdout, "stdout")
            if stderr:
                await callback(stderr, "stderr")
        return ExecResult(
            stdout=stdout, stderr=stderr, return_code=process.returncode or 0
        )

    def _default_cwd(self) -> Path:
        return self._map_path(self.task_env_config.workdir or "/app")

    def _map_command(self, command: str) -> str:
        mapped = command
        for remote in ("/logs", "/tests", "/solution", "/app"):
            mapped = mapped.replace(remote, str(self._map_path(remote)))
        return mapped

    def _map_path(self, path: str | Path | None) -> Path:
        if self._root is None:
            raise RuntimeError("LocalHostEnvironment has not been started")
        if path is None:
            return self._default_cwd()
        raw = str(path)
        if raw == "/":
            return self._root
        if raw.startswith("/"):
            return self._root / raw.lstrip("/")
        return self._root / raw
