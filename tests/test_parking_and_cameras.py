import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ParkingAndCameraTests(unittest.TestCase):
    def test_svy21_albert_centre_conversion(self):
        parking = load_module("update_parking", "scripts/update-parking.py")
        lat, lng = parking.svy21_to_wgs84(31490.4942, 30314.7936)
        self.assertAlmostEqual(lat, 1.301063, places=4)
        self.assertAlmostEqual(lng, 103.854118, places=4)

    def test_speed_cameras_feed_schema(self):
        path = ROOT / "data" / "speed-cameras.json"
        self.assertTrue(path.exists())
        data = json.loads(path.read_text(encoding="utf-8"))
        cams = data.get("cameras") or []
        self.assertGreaterEqual(len(cams), 50)
        sample = cams[0]
        self.assertIn("road_group", sample)
        self.assertTrue(1.15 <= sample["latitude"] <= 1.50)
        self.assertTrue(103.58 <= sample["longitude"] <= 104.10)

    def test_carparks_feed_schema(self):
        path = ROOT / "data" / "carparks.json"
        self.assertTrue(path.exists())
        data = json.loads(path.read_text(encoding="utf-8"))
        carparks = data.get("carparks") or []
        self.assertGreaterEqual(len(carparks), 2000)
        self.assertGreater(data["counts"]["live_car_feeds"], 1000)
        self.assertGreater(data["counts"]["live_bike_feeds"], 100)

    def test_sitemap_includes_parking_and_speed_cameras(self):
        renderer = load_module("render_static", "scripts/render-static-pages.py")
        xml = renderer.render_sitemap({})
        self.assertIn("<loc>https://sgalerts.com/parking.html</loc>", xml)
        self.assertIn("<loc>https://sgalerts.com/speed-cameras.html</loc>", xml)
