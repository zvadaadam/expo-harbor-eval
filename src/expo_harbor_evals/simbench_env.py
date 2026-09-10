"""Development/CI Mac environment with a disposable simulator per trial.

Device ownership is separate from the seatbelt wrapper: provisioning and
cleanup run as trusted harness operations. This is not adversarial isolation.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid

from expo_harbor_evals.mac_sandbox_env import MacSandboxEnvironment
from expo_harbor_evals.evaluation_identity import fingerprint
from expo_harbor_evals.simbench_evidence import write_json


class SimbenchEnvironment(MacSandboxEnvironment):
    def __init__(self, *args, device_type="com.apple.CoreSimulator.SimDeviceType.iPhone-17",
                 runtime: str | None = None, **kwargs):
        self._device_type = device_type
        self._runtime = runtime or os.environ.get("SIMBENCH_RUNTIME")
        self._device: str | None = None
        self._session = "harbor-" + uuid.uuid4().hex[:12]
        super().__init__(*args, **kwargs)

    @staticmethod
    def type() -> str:
        return "simbench-macos"

    async def _simctl(self, *args: str, check=True) -> str:
        process = await asyncio.create_subprocess_exec(
            "xcrun", "simctl", *args, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), 180)
        except BaseException:
            process.kill()
            await process.communicate()
            raise
        if check and process.returncode:
            raise RuntimeError(f"simctl {args[0]}: {stderr.decode()[-500:]}")
        return stdout.decode().strip()

    async def start(self, force_build: bool) -> None:
        await super().start(force_build)
        runtimes = json.loads(await self._simctl("list", "runtimes", "-j"))["runtimes"]
        compatible = [r for r in runtimes if r.get("isAvailable")
                      and ".iOS-" in r["identifier"]
                      and (not r.get("supportedDeviceTypes") or any(
                          d["identifier"] == self._device_type for d in r["supportedDeviceTypes"]))]
        if self._runtime:
            compatible = [r for r in compatible if self._runtime in (r["identifier"], r["version"])]
        if not compatible:
            raise RuntimeError("No compatible iOS runtime; install it in Xcode or set SIMBENCH_RUNTIME")
        runtime = max(compatible, key=lambda r: tuple(map(int, r["version"].split("."))))
        identity_path = self.trial_paths.trial_dir / "evaluation.json"
        if identity_path.exists():
            identity = json.loads(identity_path.read_text())
            identity["runtime"] = runtime["identifier"]
            identity["experiment_sha256"] = fingerprint({"experiment": identity.get("experiment_sha256"),
                "runtime": runtime["identifier"], "device_type": self._device_type})
            write_json(identity_path, identity)
        self._device = await self._simctl("create", self._session, self._device_type, runtime["identifier"])
        write_json(self._map_path("/logs/artifacts/device.json"), {
            "device": self._device, "runtime": runtime["identifier"],
            "runtime_version": runtime["version"], "device_type": self._device_type,
            "session": self._session, "status": "created",
        })
        try:
            await self._simctl("boot", self._device)
            await self._simctl("bootstatus", self._device, "-b")
        except BaseException:
            await self._delete_device()
            raise

    def _merge_env(self, env):
        merged = super()._merge_env(env) or {}
        if self._device:
            merged.update({
                "SIMBENCH_DEVICE": self._device,
                "SIMBENCH_DEVICE_NAME": self._session,
                "SIMBENCH_TRIAL_ID": self.trial_paths.trial_dir.name,
                "SIMBENCH_BACKEND": os.environ.get("SIMBENCH_BACKEND", "local-macos"),
                "AGENT_DEVICE_SESSION": self._session,
                "AGENT_DEVICE_IOS_DEVICE": self._session,
                "AGENT_DEVICE_PLATFORM": "ios",
            })
        return merged

    async def _delete_device(self):
        if self._device:
            await self._simctl("shutdown", self._device, check=False)
            await self._simctl("delete", self._device)
            self._device = None

    async def stop(self, delete: bool) -> None:
        # Release the device even when retaining the workspace for debugging.
        # Keep the workspace + device record when cleanup fails, for recovery.
        try:
            process = await asyncio.create_subprocess_exec(
                "agent-device", "close", "--session", self._session,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(process.wait(), 30)
            except TimeoutError:
                process.kill()
                await process.wait()
        except FileNotFoundError:
            pass
        await self._delete_device()
        await super().stop(delete)
