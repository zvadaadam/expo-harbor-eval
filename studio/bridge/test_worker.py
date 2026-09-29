"""Cancellation must reach Harbor shells which start their own sessions."""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

import worker


def wait_for(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.025)
    raise AssertionError("Timed out waiting for the test control process")


def running(pid):
    row = worker.process_snapshot().get(pid)
    return row is not None and not row[2].startswith("Z")


class WorkerTests(unittest.TestCase):
    def spawn_tree(self, ignore_term=False):
        leaf = (
            "import os,signal,time; "
            + ("signal.signal(signal.SIGTERM,signal.SIG_IGN); " if ignore_term else "")
            + "print(os.getpid(),flush=True); time.sleep(60)"
        )
        command = (
            "import subprocess,sys,time; "
            f"child=subprocess.Popen([sys.executable,'-c',{leaf!r}],"
            "stdout=subprocess.PIPE,text=True,start_new_session=True); "
            "print(child.stdout.readline().strip(),flush=True); time.sleep(60)"
        )
        parent = subprocess.Popen(
            [sys.executable, "-c", command], stdout=subprocess.PIPE,
            text=True, start_new_session=True,
        )
        child_pid = int(parent.stdout.readline())
        self.addCleanup(parent.stdout.close)
        self.addCleanup(self.cleanup_tree, parent, child_pid)
        return parent, child_pid

    @staticmethod
    def cleanup_tree(parent, child_pid):
        for pid in (child_pid, parent.pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        parent.wait()

    def test_terminate_reaches_detached_descendant(self):
        parent, child_pid = self.spawn_tree()
        self.assertEqual(os.getpgid(child_pid), child_pid)
        self.assertNotEqual(os.getpgid(parent.pid), os.getpgid(child_pid))
        worker.terminate(parent)
        self.assertIsNotNone(parent.returncode)
        self.assertFalse(running(child_pid))

    def test_tracks_reparented_descendant_and_escalates_to_kill(self):
        parent, child_pid = self.spawn_tree(ignore_term=True)
        tree = worker.OwnedProcessTree(parent)
        # A Harbor process can exit before a detached verifier does. Retain
        # ownership instead of relying on its now-missing PPID relationship.
        parent.terminate()
        parent.wait()
        self.assertTrue(running(child_pid))
        worker.terminate(parent, tree)
        self.assertFalse(running(child_pid))

    def test_cancellation_holds_execution_lock_through_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job_id = str(uuid4())
            directory = root / ".studio/jobs" / job_id
            directory.mkdir(parents=True)
            state_path = directory / "state.json"
            state_path.write_text(json.dumps({"task": "test-task", "action": "harbor", "status": "queued"}))
            launcher = root / ".venv/bin/harbor"
            launcher.parent.mkdir(parents=True)
            marker = root / "ready.json"
            leaf = "import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print(os.getpid(),flush=True); time.sleep(60)"
            launcher.write_text(
                f"#!{sys.executable}\n"
                "import json,os,subprocess,sys,time\n"
                f"child=subprocess.Popen([sys.executable,'-c',{leaf!r}],stdout=subprocess.PIPE,text=True,start_new_session=True)\n"
                f"with open({str(marker)!r},'w') as f: json.dump([os.getpid(),int(child.stdout.readline())],f)\n"
                "time.sleep(60)\n"
            )
            launcher.chmod(0o755)
            cleanup_checked = []
            original_terminate = worker.terminate

            def checked_terminate(child, tree=None):
                # Cancellation must not open the slot for a second control
                # while the resistant detached verifier is still running.
                with (root / ".studio/execution.lock").open("a") as contender:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertEqual(json.loads(state_path.read_text())["status"], "running")
                original_terminate(child, tree)
                cleanup_checked.append(True)

            with patch.object(worker, "ROOT", root), patch.object(worker, "task_dir", return_value=root), \
                    patch.object(worker, "task_record", return_value={"held": False, "family": "expo-codegen", "id": "test-task"}), \
                    patch.object(worker, "sys", SimpleNamespace(executable=str(launcher.parent / "python"))), \
                    patch.object(worker, "terminate", side_effect=checked_terminate):
                thread = threading.Thread(target=worker.run, args=(job_id, os.getpid()), daemon=True)
                thread.start()
                try:
                    wait_for(lambda: marker.exists() and marker.stat().st_size > 0)
                    (directory / "cancel").touch()
                    thread.join(timeout=12)
                    self.assertFalse(thread.is_alive(), "Worker did not finish cancellation")
                    self.assertEqual(cleanup_checked, [True])
                    state = json.loads(state_path.read_text())
                    self.assertEqual(state["status"], "cancelled")
                    self.assertIn("finishedAt", state)
                    self.assertTrue(all(not running(pid) for pid in json.loads(marker.read_text())))
                    with (root / ".studio/execution.lock").open("a") as lock:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    (directory / "cancel").touch()
                    if marker.exists():
                        for pid in json.loads(marker.read_text()):
                            try:
                                os.kill(pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                    thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
