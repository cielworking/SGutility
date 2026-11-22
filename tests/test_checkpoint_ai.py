import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_analyzer():
    spec = importlib.util.spec_from_file_location("analyze_checkpoints", ROOT / "scripts" / "analyze-checkpoints.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckpointAiTests(unittest.TestCase):
    def test_load_level_thresholds(self):
        mod = load_analyzer()
        self.assertEqual(mod.load_level(0), "Smooth")
        self.assertEqual(mod.load_level(18), "Smooth")
        self.assertEqual(mod.load_level(25), "Smooth")
        self.assertEqual(mod.load_level(26), "Moderate")
        self.assertEqual(mod.load_level(45), "Moderate")
        self.assertEqual(mod.load_level(46), "Heavy")

    def test_dashboard_camera_selection_uses_two_cameras_each(self):
        mod = load_analyzer()
        self.assertEqual(mod.DASHBOARD_CAMERA_IDS["woodlands"], ["2701", "2702"])
        self.assertEqual(mod.DASHBOARD_CAMERA_IDS["tuas"], ["4703", "4713"])

    def test_direction_zones_for_woodlands_2701(self):
        mod = load_analyzer()
        # Point in upper-left Johor-bound carriageway vs lower-right Woodlands carriageway vs ignored water
        self.assertEqual(mod.classify_direction("2701", 1150, 650, 1920, 1069), "towards_jb")
        self.assertEqual(mod.classify_direction("2701", 1150, 775, 1920, 1069), "towards_sg")
        self.assertEqual(mod.classify_direction("2701", 200, 150, 1920, 1069), "ignored")

    def test_direction_zones_for_tuas_4703(self):
        mod = load_analyzer()
        # 4703 covers towards_sg (upper-right carriageway) and towards_jb (lower curved viaduct & bike ramp); sea is ignored
        self.assertEqual(mod.classify_direction("4703", 1250, 220, 1920, 1069), "towards_sg")
        self.assertEqual(mod.classify_direction("4703", 820, 450, 1920, 1069), "towards_jb")
        self.assertEqual(mod.classify_direction("4703", 200, 400, 1920, 1069), "ignored")

    def test_direction_zones_for_tuas_4713(self):
        mod = load_analyzer()
        # 4713 right-hand JOHOR queue is towards_jb; left AYE carriageway is ignored (4703 covers towards_sg)
        self.assertEqual(mod.classify_direction("4713", 1450, 350, 1920, 1069), "towards_jb")
        self.assertEqual(mod.classify_direction("4713", 600, 420, 1920, 1069), "ignored")

    def test_hourly_averages_grouping(self):
        mod = load_analyzer()
        res = mod.compute_hourly_averages([
            {"timestamp_sgt": "2026-11-16T10:00:00+08:00", "woodlands_load": 10.0, "tuas_load": 4.0},
            {"timestamp_sgt": "2026-11-16T10:15:00+08:00", "woodlands_load": 20.0, "tuas_load": 6.0},
        ])
        self.assertEqual(len(res["by_day_hour"]), 1)
        row = res["by_day_hour"][0]
        self.assertEqual(row["day"], "Mon")
        self.assertEqual(row["hour"], 10)
        self.assertEqual(row["samples"], 2)
        self.assertEqual(row["woodlands_avg_load"], 15.0)
        self.assertEqual(row["tuas_avg_load"], 5.0)

    def test_camera_sahi_tiles_are_valid_and_bounded(self):
        mod = load_analyzer()
        for cid in ("2701", "2702", "4703", "4713"):
            tiles = mod.build_camera_tiles(cid, 1920, 1069)
            self.assertGreaterEqual(len(tiles), 5)
            self.assertEqual(tiles[0], (0, 0, 1920, 1069))
            for x1, y1, x2, y2 in tiles:
                self.assertGreaterEqual(x1, 0)
                self.assertGreaterEqual(y1, 0)
                self.assertLessEqual(x2, 1920)
                self.assertLessEqual(y2, 1069)
                self.assertLess(x1, x2)
                self.assertLess(y1, y2)

    def test_generated_traffic_json_schema(self):
        traffic_path = ROOT / "data" / "checkpoint-traffic.json"
        self.assertTrue(traffic_path.exists())
        data = json.loads(traffic_path.read_text(encoding="utf-8"))
        for loc in ("woodlands", "tuas"):
            self.assertIn(loc, data)
            self.assertIn(data[loc]["status"], {"Smooth", "Moderate", "Heavy"})
            self.assertIn("total_vehicles", data[loc])
            self.assertIn("towards_jb", data[loc])
            self.assertIn("towards_sg", data[loc])
