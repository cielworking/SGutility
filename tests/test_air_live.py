import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AirLiveTests(unittest.TestCase):
    def test_singapore_haze_template_has_live_hooks(self):
        template = (ROOT / "scripts" / "render-weather-pages.py").read_text(encoding="utf-8")
        for token in (
            "data-air-live",
            "air-live.js?v=1",
            "data-air-psi-value",
            "data-air-pm25-value",
            "data-air-status",
            "data-air-reported-time",
        ):
            self.assertIn(token, template)

    def test_live_script_uses_separate_validated_endpoints(self):
        script = (ROOT / "air-live.js").read_text(encoding="utf-8")
        for token in (
            "api-open.data.gov.sg/v2/real-time/api/",
            'metric === "psi" ? "psi" : "pm25"',
            "psi_twenty_four_hourly",
            "pm25_one_hourly",
            "AbortSignal.timeout",
            "Invalid reading",
            "Live PSI loaded; PM2.5 could not refresh",
            "saved readings remain visible",
        ):
            self.assertIn(token, script)


if __name__ == "__main__":
    unittest.main()
