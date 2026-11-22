import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Map Python import top-level module names to PyPI package names in requirements.txt.
IMPORT_TO_PACKAGE = {
    "PIL": "pillow",
    "bs4": "beautifulsoup4",
    # urllib3 is installed as a required transitive dependency of requests.
    "urllib3": "requests",
}


def parse_requirements(path: Path) -> set[str]:
    packages: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        pkg = re.split(r"[<>=!~;\[\s]", line, maxsplit=1)[0].strip().lower()
        if pkg:
            packages.add(pkg)
    return packages


def extract_third_party_imports(folder: Path, local_modules: set[str]) -> dict[str, set[str]]:
    missing: dict[str, set[str]] = {}
    for py_file in sorted(folder.glob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names.extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names.append(node.module.split(".")[0])
            for mod in names:
                if mod in sys.stdlib_module_names or mod in local_modules:
                    continue
                missing.setdefault(mod, set()).add(py_file.relative_to(ROOT).as_posix())
    return missing


class WorkflowDependenciesTests(unittest.TestCase):
    def test_all_test_and_script_imports_are_in_requirements_txt(self):
        req_path = ROOT / "requirements.txt"
        self.assertTrue(req_path.exists(), "requirements.txt must exist")
        declared = parse_requirements(req_path)

        local_modules = {
            p.stem
            for sub in ("scripts", "tests")
            for p in (ROOT / sub).glob("*.py")
        }

        for sub in ("tests", "scripts"):
            imported = extract_third_party_imports(ROOT / sub, local_modules)
            for mod, files in sorted(imported.items()):
                pkg = IMPORT_TO_PACKAGE.get(mod, mod).lower()
                self.assertIn(
                    pkg,
                    declared,
                    f"Module '{mod}' (package '{pkg}') imported in {sorted(files)} must be listed in requirements.txt",
                )

    def test_workflows_running_unit_tests_install_full_requirements(self):
        workflows_dir = ROOT / ".github" / "workflows"
        wf_files = sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml"))
        self.assertTrue(wf_files, "Expected GitHub Actions workflow files")

        checked = 0
        for wf in wf_files:
            content = wf.read_text(encoding="utf-8")
            if "unittest discover" in content:
                checked += 1
                self.assertRegex(
                    content,
                    r"pip\s+install\s+-r\s+requirements\.txt",
                    f"{wf.name} runs unittest discover and must install '-r requirements.txt' so test dependencies stay in sync",
                )
        self.assertGreaterEqual(checked, 2, "Expected weather.yml and checkpoint-traffic.yml to be checked")
