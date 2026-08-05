"""macOS seatbelt-sandboxed variant of the local Harbor environment.

Wraps every command in ``sandbox-exec`` with a per-trial profile: reads are
unrestricted (the agent must read the task and its toolchain), writes are
denied everywhere except the trial root, temp dirs, and the caches the claude
CLI and uv need. This is the pragmatic macOS answer for mobile-native evals
where Linux containers can't help (iOS simulators, EAS, Xcode): the trial
still executes on the host, but it cannot modify files outside its sandbox.

Not as strong as a VM (Tart et al. remain the CI-grade isolation); it is a
write-containment layer for local runs.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import override

from expo_harbor_evals.local_env import LocalHostEnvironment

PROFILE_TEMPLATE = """(version 1)
(allow default)
(deny file-write*)
(allow file-write*
  (subpath "{root}")
  (subpath "/dev")
  (subpath "/private/tmp")
  (subpath "/private/var/folders")
  (subpath "{home}/.claude")
  (literal "{home}/.claude.json")
  (literal "{home}/.claude.json.backup")
  (literal "{home}/.claude.json.lock")
  (subpath "{home}/.cache")
  (subpath "{home}/.npm")
  (subpath "{home}/.agent-device")
  (subpath "{home}/.argent")
  (subpath "{home}/.maestro")
  (subpath "{home}/Library/Caches")
)
"""


class MacSandboxEnvironment(LocalHostEnvironment):
    _profile_path: Path | None = None

    @staticmethod
    @override
    def type() -> str:
        return "mac-sandbox-dev"

    @override
    async def start(self, force_build: bool) -> None:
        await super().start(force_build)
        assert self._root is not None
        profile = PROFILE_TEMPLATE.format(
            root=self._root.resolve(),
            home=Path.home().resolve(),
        )
        self._profile_path = self._root / "sandbox.sb"
        self._profile_path.write_text(profile)

    @override
    def _wrap_command(self, mapped_command: str) -> str:
        if self._profile_path is None:
            raise RuntimeError("MacSandboxEnvironment has not been started")
        return (
            f"sandbox-exec -f {shlex.quote(str(self._profile_path))} "
            f"/bin/bash -c {shlex.quote(mapped_command)}"
        )
