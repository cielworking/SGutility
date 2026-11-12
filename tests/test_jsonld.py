import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOCK = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


class JsonLdTests(unittest.TestCase):
    def test_every_json_ld_block_parses(self):
        failures = []
        seen = 0
        for path in sorted(ROOT.rglob("*.html")):
            text = path.read_text(encoding="utf-8")
            for index, match in enumerate(BLOCK.finditer(text), 1):
                seen += 1
                try:
                    json.loads(match.group(1))
                except json.JSONDecodeError as error:
                    failures.append(f"{path.relative_to(ROOT)} block {index}: {error}")
        self.assertGreater(seen, 0)
        self.assertEqual(failures, [])
