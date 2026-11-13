import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pages():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in {".git", "telex", "riderlink-confirmed", "node_modules"}
            and not name.startswith("_")
            and not name.startswith("tmp")
        ]
        for filename in filenames:
            if filename.endswith(".html") and not filename.startswith("_"):
                yield Path(dirpath) / filename


class ThemeTests(unittest.TestCase):
    def test_every_page_has_the_theme_control_and_prepaint_initializer(self):
        failures = []
        count = 0
        for path in pages():
            text = path.read_text(encoding="utf-8")
            count += 1
            checks = {
                "theme control": text.count('class="theme-control"'),
                "theme script": text.count("theme.js?v=1"),
                "prepaint initializer": text.count("sga-theme-mode"),
                "css v23": text.count("style.css?v=23"),
            }
            if any(value != 1 for value in checks.values()):
                failures.append((str(path.relative_to(ROOT)), checks))
        self.assertGreater(count, 30)
        self.assertEqual(failures, [])

    def test_dark_css_is_attribute_scoped_and_explicit_light_wins(self):
        css = (ROOT / "style.css").read_text(encoding="utf-8")
        self.assertIn(':root[data-theme="dark"]', css)
        self.assertIn("color-scheme: light;", css)
        self.assertNotIn("@media (prefers-color-scheme: dark)", css)
        self.assertIn("--page: #0b1220;", css)

    def test_theme_script_persists_and_listens_for_system_changes(self):
        script = (ROOT / "theme.js").read_text(encoding="utf-8")
        for token in (
            "sga-theme-mode",
            "localStorage.getItem",
            "localStorage.setItem",
            "matchMedia",
            "addEventListener(\"change\"",
            "aria-pressed",
        ):
            self.assertIn(token, script)
