"""Development-only Harbor environment for machines without Docker.

This is not a sandbox. It executes commands on the host inside a per-trial
directory and exists only to make the Harbor task contract runnable locally.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import override

from harbor.environments.base import BaseEnvironment, ExecResult
from harbor.environments.capabilities import EnvironmentCapabilities


class LocalHostEnvironment(BaseEnvironment):
    def __init__(self, *args, keep_root: bool = False, **kwargs) -> None:
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
        self._root = self.trial_paths.trial_dir.resolve() / "_local_env"
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
        if self.task_env_config.workdir:
            self._map_path(self.task_env_config.workdir).mkdir(
                parents=True, exist_ok=True
            )
        await self._upload_environment_dir_after_start()

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
    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int | None = None,
        user: str | int | None = None,
    ) -> ExecResult:
        mapped_command = self._map_command(command)
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

        try:
            process = await asyncio.create_subprocess_shell(
                mapped_command,
                cwd=str(mapped_cwd),
                env=run_env,
                executable="/bin/bash",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, stderr_b = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            process.kill()
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
