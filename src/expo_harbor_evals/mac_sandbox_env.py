"""macOS seatbelt-sandboxed variant of the local Harbor environment.

Wraps every command in ``sandbox-exec`` with a per-trial profile. Agent
commands additionally hide evaluator answers; trusted setup and verification
can read them. Writes are denied except in the trial root, temp dirs, and the caches the claude
CLI and uv need. This is the pragmatic macOS answer for mobile-native evals
where Linux containers can't help (iOS simulators, EAS, Xcode): the trial
still executes on the host, but it cannot modify files outside its sandbox.

Not as strong as a VM (Tart et al. remain the CI-grade isolation); it is a
write-containment layer for local runs.
"""

from __future__ import annotations

import shlex
from contextvars import ContextVar
from pathlib import Path
from typing import override

from expo_harbor_evals.local_env import LocalHostEnvironment

_agent_profile: ContextVar[Path | None] = ContextVar("agent_profile", default=None)

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
  (subpath "{home}/.config/muse")
  (subpath "{home}/.local/share/muse")
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

    async def exec_agent(self, command: str, **kwargs):
        """Hide evaluator answers from host-agent commands, not from verification.

        This narrows ordinary filesystem access. It does not make the shared
        host or its simulator control services an adversarial security boundary.
        """
        assert self._root is not None
        blocked = [self._root / name for name in ("tests", "solution", "logs/verifier", "logs/artifacts")]
        # Exported drafts also carry their verifier and oracle beside environment/.
        blocked.append(self.environment_dir.parent)
        repo_root = next((p for p in self.environment_dir.parents
                          if (p / "suites/mobile-v2.json").is_file()), None)
        if repo_root is None:
            task_root = next((p for p in self.environment_dir.parents if p.name == "tasks"), None)
            repo_root = task_root.parent if task_root else None
        if repo_root:
            # Drafts and exports contain the same hidden answers as library tasks.
            blocked += [repo_root / name for name in
                        ("tasks", ".studio", "outputs", ".context", "runs", "src", "suites", "mobile", ".git")]
        if getattr(self, "_device", None):
            blocked.append(Path.home() / "Library/Developer/CoreSimulator/Devices" / self._device / "data/Containers/Data/Application")
        profile_path = self._root / "agent.sb"
        # JSON escaping is also valid for seatbelt's quoted path strings.
        import json
        # Seatbelt profiles cannot be nested. Combine write containment and
        # answer hiding in the one profile used by this command's context.
        lines = [PROFILE_TEMPLATE.format(root=self._root.resolve(), home=Path.home().resolve())]
        lines += [f"(deny file-read* (subpath {json.dumps(str(p.resolve()))}))" for p in blocked]
        lines += [f"(allow file-read* (subpath {json.dumps(str((self._root / name).resolve()))}))"
                  for name in ("app", "logs/agent")]
        lines += [f"(deny file-write* (literal {json.dumps(str(p.resolve()))}))"
                  for p in (profile_path, self._profile_path)]
        profile_path.write_text("\n".join(lines) + "\n")
        token = _agent_profile.set(profile_path)
        try:
            return await self.exec(command=command, **kwargs)
        finally:
            _agent_profile.reset(token)

    @override
    def _wrap_command(self, mapped_command: str) -> str:
        if self._profile_path is None:
            raise RuntimeError("MacSandboxEnvironment has not been started")
        return (
            f"sandbox-exec -f {shlex.quote(str(_agent_profile.get() or self._profile_path))} "
            f"/bin/bash -c {shlex.quote(mapped_command)}"
        )
