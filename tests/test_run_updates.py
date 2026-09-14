import importlib.util
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


MODULE_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "run-updates.py"
SPEC = importlib.util.spec_from_file_location("run_updates", MODULE_PATH)
run_updates = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_updates)


class UpdateRunnerTests(unittest.TestCase):
    def test_continues_after_failure_and_reports_nonzero(self):
        calls = []
        return_codes = iter([0, 1, 0])

        def runner(command, **kwargs):
            calls.append(command)
            return SimpleNamespace(returncode=next(return_codes))

        with tempfile.TemporaryDirectory() as directory:
            summary = pathlib.Path(directory) / "summary.md"

            with patch.dict(
                "os.environ",
                {"GITHUB_STEP_SUMMARY": str(summary)},
                clear=False,
            ):
                result = run_updates.run_updates(
                    updaters=("one.py", "two.py", "three.py"),
                    repo_root=pathlib.Path(directory),
                    runner=runner,
                )

            self.assertEqual(1, result)
            self.assertEqual(3, len(calls))
            self.assertIn("`two.py` exited with status 1", summary.read_text())

    def test_returns_zero_when_all_updaters_succeed(self):
        def runner(command, **kwargs):
            return SimpleNamespace(returncode=0)

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict("os.environ", {}, clear=True):
                result = run_updates.run_updates(
                    updaters=("one.py", "two.py"),
                    repo_root=pathlib.Path(directory),
                    runner=runner,
                )

        self.assertEqual(0, result)


if __name__ == "__main__":
    unittest.main()
