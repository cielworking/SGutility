import importlib.util
import pathlib
import unittest

import requests


MODULE_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "update-sgpools.py"
SPEC = importlib.util.spec_from_file_location("update_sgpools", MODULE_PATH)
update_sgpools = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update_sgpools)


class FakeResponse:
    def __init__(self, status_code, text="<li>draw</li>"):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"{self.status_code} Server Error",
                response=self,
            )


class SingaporePoolsRetryTests(unittest.TestCase):
    def test_retries_503_then_returns_result(self):
        responses = [FakeResponse(503), FakeResponse(200)]
        delays = []

        def request_get(*args, **kwargs):
            return responses.pop(0)

        block = update_sgpools.get_first_li(
            "https://example.test/results",
            request_get=request_get,
            sleep=delays.append,
            max_attempts=3,
        )

        self.assertEqual("draw", block.get_text(strip=True))
        self.assertEqual([2], delays)

    def test_retries_connection_error(self):
        calls = []

        def request_get(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise requests.ConnectionError("connection closed")
            return FakeResponse(200)

        update_sgpools.get_first_li(
            "https://example.test/results",
            request_get=request_get,
            sleep=lambda delay: None,
            max_attempts=3,
        )

        self.assertEqual(2, len(calls))

    def test_does_not_retry_non_transient_status(self):
        calls = []

        def request_get(*args, **kwargs):
            calls.append(1)
            return FakeResponse(404)

        with self.assertRaises(requests.HTTPError):
            update_sgpools.get_first_li(
                "https://example.test/results",
                request_get=request_get,
                sleep=lambda delay: None,
                max_attempts=3,
            )

        self.assertEqual(1, len(calls))


if __name__ == "__main__":
    unittest.main()
