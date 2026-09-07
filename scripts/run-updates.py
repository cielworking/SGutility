import os
import pathlib
import subprocess
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

UPDATERS = (
    "scripts/update-coe.py",
    "scripts/update-petrol.py",
    "scripts/update-quickinfo.py",
    "scripts/update-sgpools.py",
    "scripts/update-bto.py",
    "scripts/update-news.py",
    "scripts/update-checkpoints.py",
    "scripts/update-petrol-discounts.py",
)


def write_step_summary(failures):
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")

    if not summary_path:
        return

    if failures:
        lines = [
            "## Dashboard update failures",
            "",
            "Successful sources were still updated and committed.",
            "",
        ]
        lines.extend(
            f"- `{script}` exited with status {return_code}"
            for script, return_code in failures
        )
    else:
        lines = [
            "## Dashboard updates completed",
            "",
            "All data sources updated successfully.",
        ]

    with pathlib.Path(summary_path).open("a", encoding="utf-8") as summary:
        summary.write("\n".join(lines) + "\n")


def run_updates(updaters=UPDATERS, repo_root=REPO_ROOT, runner=None):
    runner = runner or subprocess.run
    failures = []

    for script in updaters:
        script_path = repo_root / script
        print(f"::group::{script}", flush=True)

        try:
            completed = runner(
                [sys.executable, str(script_path)],
                cwd=repo_root,
                check=False,
            )
            return_code = completed.returncode
        except OSError as error:
            print(f"Unable to start {script}: {error}", file=sys.stderr)
            return_code = 1
        finally:
            print("::endgroup::", flush=True)

        if return_code:
            failures.append((script, return_code))
            print(
                f"::error title=Updater failed::{script} exited with "
                f"status {return_code}",
                file=sys.stderr,
            )

    write_step_summary(failures)

    if failures:
        failed_scripts = ", ".join(script for script, _ in failures)
        print(
            f"{len(failures)} updater(s) failed: {failed_scripts}. "
            "Other data sources were still processed.",
            file=sys.stderr,
        )
        return 1

    print("All dashboard updaters completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_updates())
