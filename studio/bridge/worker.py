"""One local free job, with a cross-process lock, cancellation and a deadline."""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

from catalog import ROOT, contained, task_dir, task_record


def process_snapshot():
    """Read identities as well as PIDs so cleanup cannot target a reused PID."""
    result = subprocess.run(
        ["/bin/ps", "-axo", "pid=,ppid=,stat=,lstart="],
        capture_output=True, text=True, check=True, timeout=3,
        env={**os.environ, "LC_ALL": "C"},
    )
    rows = {}
    for line in result.stdout.splitlines():
        fields = line.split(None, 3)
        if len(fields) == 4:
            pid, parent, status, started = fields
            rows[int(pid)] = (int(parent), started.strip(), status)
    return rows


class OwnedProcessTree:
    """Remember descendants before their parents exit and they are reparented."""

    def __init__(self, child):
        self.child = child
        self.identities = {}
        self.observe()

    def observe(self):
        rows = process_snapshot()
        if not self.identities and self.child.pid in rows:
            self.identities[self.child.pid] = rows[self.child.pid][1]
        live = {pid for pid, started in self.identities.items()
                if pid in rows and rows[pid][1] == started}
        while True:
            children = {pid for pid, (parent, _, _) in rows.items() if parent in live}
            added = children - live
            if not added:
                break
            for pid in added:
                self.identities[pid] = rows[pid][1]
            live.update(added)
        return rows

    def running(self, rows):
        return {pid for pid, started in self.identities.items()
                if pid in rows and rows[pid][1] == started and not rows[pid][2].startswith("Z")}

    def signal(self, rows, sig, only=None):
        running = self.running(rows)
        if only is not None:
            running &= only
        # Capture the full tree first, and signal the root last. Harbor's local
        # shells start new sessions, so killpg(root) alone cannot reach them.
        for pid in sorted(running, key=lambda pid: pid == self.child.pid):
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        return running


def now():
    return datetime.now(timezone.utc).isoformat()


def run(job_id: str, parent_pid: int):
    import uuid
    uuid.UUID(job_id)
    directory = contained(ROOT, ROOT / ".studio/jobs" / job_id)
    state_path = contained(ROOT, directory / "state.json")
    state = json.loads(state_path.read_text())
    def update(status, **extra):
        state.update(status=status, **extra)
        temp = directory / "state.tmp"
        temp.write_text(json.dumps(state))
        temp.replace(state_path)
    def stop_reason():
        if (directory / "cancel").exists():
            return "cancelled"
        try:
            os.kill(parent_pid, 0)
        except ProcessLookupError:
            return "interrupted"
        return None
    try:
        task = task_record(task_dir(state["task"]))
        if task["held"] or task["family"] != "expo-codegen":
            raise ValueError("Only available coding tasks can run local controls.")
        action = state["action"]
        if action not in {"guards", "policy", "harbor"}:
            raise ValueError("Unknown control action")
        if action == "policy" and "policy-behavior" not in task["measurements"]:
            raise ValueError("This task has no executable policy contract")
        # An OS lock is released on process exit, including a server crash.
        lock_path = contained(ROOT, ROOT / ".studio/execution.lock")
        with lock_path.open("a") as lock:
            while True:
                reason = stop_reason()
                if reason:
                    update(reason, finishedAt=now(), message="Stopped before execution.")
                    return
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    time.sleep(0.25)
            if action == "harbor":
                # A generated config only uses no-op/reference agents and the
                # exact reference smoke verifier; it never calls a judge.
                config = {"jobs_dir": str(ROOT / "runs"), "n_attempts": 1, "n_concurrent_trials": 1,
                          "environment": {"import_path": "expo_harbor_evals.local_env:LocalHostEnvironment", "delete": True},
                          "verifier": {"env": {"EXPO_EVAL_VERIFIER_MODE": "reference"}},
                          "agents": [{"name": "nop"}, {"name": "oracle"}],
                          "datasets": [{"path": str(ROOT / "tasks/codegen"), "task_names": [task["id"]]}]}
                config_path = directory / "harbor.json"
                config_path.write_text(json.dumps(config, indent=2))
                command = [str(Path(sys.executable).parent / "harbor"), "run", "-c", str(config_path), "--job-name", "studio-" + job_id, "--yes"]
            elif action == "guards":
                command = [sys.executable, str(ROOT / "studio/bridge/guards.py"), task["id"], str(directory / "controls.json")]
            else:
                command = [sys.executable, "-m", "expo_harbor_evals.codegen_calibrate", "--only", task["id"], "--jobs", "1",
                           "--behavior-only", "--output", str(directory / "controls.json")]
            update("running", message="Running local controls. No model or judge calls.")
            env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONUNBUFFERED": "1"}
            # Inherited judge settings are irrelevant to these explicit modes.
            with (directory / "log.txt").open("a") as log:
                # Fail before spawning if process ownership cannot be inspected.
                process_snapshot()
                child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                tree = None
                try:
                    tree = OwnedProcessTree(child)
                    started = time.monotonic()
                    reason = None
                    while True:
                        tree.observe()
                        if child.poll() is not None:
                            break
                        reason = stop_reason()
                        if not reason and time.monotonic() - started > 600:
                            reason = "interrupted"
                        if reason:
                            break
                        time.sleep(0.25)
                finally:
                    # Finish descendant cleanup before releasing execution.lock
                    # or publishing a terminal state, including on exceptions.
                    terminate(child, tree)
            update(reason or ("completed" if child.returncode == 0 else "failed"), finishedAt=now(), exitCode=child.returncode,
                   message="Stopped by request or execution deadline." if reason else "Controls finished. Read the log for bracket outcomes.")
    except Exception as exc:
        update("failed", finishedAt=now(), message=str(exc))


def terminate(child, tree=None):
    tree = tree or OwnedProcessTree(child)
    signalled = tree.signal(tree.observe(), signal.SIGTERM)
    deadline = time.monotonic() + 3
    while True:
        child.poll()
        rows = tree.observe()
        if not tree.running(rows):
            break
        # Include processes started by a still-running shutdown handler.
        signalled |= tree.signal(rows, signal.SIGTERM, tree.running(rows) - signalled)
        if time.monotonic() >= deadline:
            tree.signal(rows, signal.SIGKILL)
            break
        time.sleep(0.05)
    child.wait()
    deadline = time.monotonic() + 3
    while True:
        rows = tree.observe()
        if not tree.running(rows):
            return
        tree.signal(rows, signal.SIGKILL)
        if time.monotonic() >= deadline:
            raise RuntimeError("The owned control processes could not be stopped.")
        time.sleep(0.05)


if __name__ == "__main__":
    run(sys.argv[1], int(sys.argv[2]))
