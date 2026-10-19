import importlib.util
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


update = module("update_weather", "update-weather.py")
render = module("render_weather", "render-weather-pages.py")
layout = module("weather_layout", "weather_layout.py")
air_layout = module("air_quality_layout", "air_quality_layout.py")


class WeatherTests(unittest.TestCase):
    def test_air_snapshot_escapes_script_content_and_preserves_zero(self):
        cache = {"sg_psi": {"data": {"readings": {"psi_twenty_four_hourly": {"north": 0}}}}, "my_haze": {"data": [{"location": "</script><script>alert(1)</script>"}]}}
        content = air_layout.render_air_quality(cache)
        self.assertIn('id="air-number">0</strong>', content)
        self.assertNotIn('</script><script>alert(1)', content)
        self.assertIn('\\u003c/script>', content)

    def test_air_history_sorts_and_deduplicates_official_report_times(self):
        first = {"timestamp": "2026-10-18T23:00:00+08:00", "readings": {"psi_twenty_four_hourly": {"north": 100}}}
        second = {"timestamp": "2026-10-19T00:00:00+08:00", "readings": {"psi_twenty_four_hourly": {"north": 101}}}
        with patch.object(update, 'get', side_effect=[{"code": 0,"data": {"items": [first]}}, {"code": 0,"data": {"items": [second, first]}}]):
            rows=update.singapore_air_history('psi')
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['timestamp'],first['timestamp'])

    def test_regional_outlook_uses_official_regions_and_drops_expired_periods(self):
        now = layout.datetime.now(layout.TZ)
        old = {"timePeriod": {"start": (now-timedelta(hours=2)).isoformat(), "end": (now-timedelta(hours=1)).isoformat()}, "regions": {"north": {"text": "Old rain"}}}
        new = {"timePeriod": {"start": now.isoformat(), "end": (now+timedelta(hours=2)).isoformat()}, "regions": {"north": {"text": "Thundery Showers"}}}
        content = layout.regional_cards({"periods": [old,new]})
        self.assertEqual(content.count('class="region-card"'),5)
        self.assertNotIn('Old rain',content)
        self.assertIn('Thundery Showers',content)
        self.assertIn('South',content)

    def test_combined_page_does_not_render_all_neighbourhoods_as_cards(self):
        cache = {"sg_rain": {"data": {"forecasts": [{"area": "Ang Mo Kio", "forecast": "Cloudy"}]}}}
        content = layout.render_combined(cache)
        self.assertIn('<option value="Ang Mo Kio">',content)
        self.assertNotIn('<h3>Ang Mo Kio</h3>',content)
        self.assertIn('id="radar-time"',content)
        self.assertIn('id="radar-play"',content)
    def test_feed_failure_retains_previous_data_and_time(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data").mkdir()
            path = root / "data/weather.json"
            path.write_text(json.dumps({"sg_rain": {"data": {"previous": True}, "fetched_at": "2026-01-01T00:00:00+08:00", "ok": True}}))
            with patch.object(update, "ROOT", root), patch.object(update, "get", side_effect=ValueError("bad upstream")):
                update.main()
            result = json.loads(path.read_text())
            self.assertEqual(result["sg_rain"]["data"], {"previous": True})
            self.assertEqual(result["sg_rain"]["fetched_at"], "2026-01-01T00:00:00+08:00")
            self.assertFalse(result["sg_rain"]["ok"])

    def test_haze_cache_excludes_non_display_fields(self):
        feature = {"attributes": {"STATION_ID": "test", "STATION_LOCATION": "Test", "STATE_NAME": "Johor", "DATETIME": 1792404000000, "API": 0, "CLASS": "Good", "OP_PHONE": "private", "OP_EMAIL": "private"}}
        with patch.object(update, "get", return_value={"features": [feature]}):
            rows = update.malaysia_haze()
        self.assertNotIn("private", json.dumps(rows))
        self.assertEqual(rows[0]["api"], 0)
        self.assertEqual(rows[0]["reported_at"], "2026-10-19T10:00:00+08:00")

    def test_empty_successful_singapore_response_is_rejected(self):
        with patch.object(update, "get", return_value={"code": 0, "data": {"items": [{}]}}):
            with self.assertRaises(ValueError):
                update.sg("two-hr-forecast")

    def test_stale_expired_future_and_missing_feeds_are_flagged(self):
        current = render.NOW.isoformat()
        self.assertNotIn('class="feed-status is-stale"', render.freshness({"ok": True, "fetched_at": current}))
        for feed, stamp, end in [({}, None, None), ({"ok": False}, current, None), ({"ok": True}, (render.NOW - timedelta(hours=4)).isoformat(), None), ({"ok": True}, current, (render.NOW - timedelta(minutes=1)).isoformat()), ({"ok": True}, (render.NOW + timedelta(hours=8)).isoformat(), None)]:
            self.assertIn('class="feed-status is-stale"', render.freshness(feed, stamp, end))

    def test_missing_warning_dates_do_not_break_render(self):
        content, *_ = render.render_content("malaysia", "rain-forecast", {"my_warnings": {"data": [{"valid_to": None, "valid_from": None}]}})
        self.assertIn("No currently valid warnings", content)

    def test_source_text_is_escaped(self):
        row = {"date": "<script>alert(1)</script>", "summary_forecast": "<img src=x onerror=alert(1)>"}
        content = render.weather_tile(row)
        self.assertNotIn("<script>", content)
        self.assertNotIn("<img", content)


if __name__ == "__main__":
    unittest.main()
