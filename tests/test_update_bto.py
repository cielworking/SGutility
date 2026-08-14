import importlib.util
import pathlib
import unittest

from playwright.sync_api import Error as PlaywrightError


MODULE_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "update-bto.py"
SPEC = importlib.util.spec_from_file_location("update_bto", MODULE_PATH)
update_bto = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update_bto)


class BtoRetryTests(unittest.TestCase):
    def test_retries_playwright_error_then_returns_result(self):
        calls = []
        delays = []

        def fetch(playwright):
            calls.append(1)
            if len(calls) < 3:
                raise PlaywrightError("Failed to fetch")
            return [{"town": "Test"}]

        result = update_bto.fetch_with_retry(
            object(),
            fetch=fetch,
            sleep=delays.append,
            max_attempts=3,
        )

        self.assertEqual([{"town": "Test"}], result)
        self.assertEqual([5, 10], delays)

    def test_raises_after_last_attempt(self):
        calls = []

        def fetch(playwright):
            calls.append(1)
            raise PlaywrightError("Failed to fetch")

        with self.assertRaises(PlaywrightError):
            update_bto.fetch_with_retry(
                object(),
                fetch=fetch,
                sleep=lambda delay: None,
                max_attempts=3,
            )

        self.assertEqual(3, len(calls))


if __name__ == "__main__":
    unittest.main()
