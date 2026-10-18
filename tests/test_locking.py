import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from app.locking import CrossProcessFileLock, InstanceGuard


class CrossProcessLockTests(unittest.TestCase):
    def test_second_lock_cannot_enter_until_first_releases(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "shared.lock"
            first = CrossProcessFileLock(path)
            second = CrossProcessFileLock(path)
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.release()
            self.assertTrue(second.acquire())
            second.release()

    def test_instance_guard_rejects_duplicate_launch(self):
        with tempfile.TemporaryDirectory() as td:
            first = InstanceGuard(Path(td))
            second = InstanceGuard(Path(td))
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            self.assertIn("já está aberto", second.reason)
            first.release()
            self.assertTrue(second.acquire())
            second.release()

    def test_handoff_blocks_ordinary_launch_and_allows_installed_child(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            parent = InstanceGuard(root)
            self.assertTrue(parent.acquire())
            token = parent.create_handoff(root / "install")
            normal = InstanceGuard(root)
            self.assertFalse(normal.acquire())
            self.assertIn("atualização", normal.reason)
            parent.release()
            child = InstanceGuard(root)
            self.assertTrue(child.acquire(handoff_token=token))
            self.assertFalse(child.handoff_path.exists())
            child.release()

    def test_lock_is_shared_with_a_separate_process(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "multi-process.lock"
            code = (
                "import sys,time; from pathlib import Path; "
                "from app.locking import CrossProcessFileLock; "
                "lock=CrossProcessFileLock(Path(sys.argv[1]), timeout=1); "
                "print('ACQUIRED', flush=True) if lock.acquire() else sys.exit(3); "
                "time.sleep(1.2); lock.release()"
            )
            env = dict(os.environ)
            project_root = str(Path(__file__).resolve().parents[1])
            env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")
            child = subprocess.Popen(
                [sys.executable, "-c", code, str(path)],
                cwd=project_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, env=env,
            )
            try:
                self.assertEqual(child.stdout.readline().strip(), "ACQUIRED")
                contender = CrossProcessFileLock(path, timeout=0.05)
                self.assertFalse(contender.acquire())
                child.wait(timeout=5)
                self.assertEqual(child.returncode, 0, child.stderr.read())
                self.assertTrue(contender.acquire())
                contender.release()
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=3)
                if child.stdout:
                    child.stdout.close()
                if child.stderr:
                    child.stderr.close()


if __name__ == "__main__":
    unittest.main()
