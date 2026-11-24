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
        # Upper-left Johor-bound carriageway (above central concrete median: e.g. lorry at (1000,690), car at (1260,595))
        self.assertEqual(mod.classify_direction("2701", 1000, 690, 1920, 1069), "towards_jb")
        self.assertEqual(mod.classify_direction("2701", 1260, 595, 1920, 1069), "towards_jb")
        # Lower-right Woodlands-bound carriageway & bike lane (between central median and KTM railway fence)
        self.assertEqual(mod.classify_direction("2701", 1240, 660, 1920, 1069), "towards_sg")
        self.assertEqual(mod.classify_direction("2701", 964, 898, 1920, 1069), "towards_sg")
        self.assertEqual(mod.classify_direction("2701", 880, 943, 1920, 1069), "towards_sg")
        # KTM railway tracks, PUB water pipes, and sea are ignored
        self.assertEqual(mod.classify_direction("2701", 1150, 890, 1920, 1069), "ignored")
        self.assertEqual(mod.classify_direction("2701", 200, 150, 1920, 1069), "ignored")

    def test_direction_zones_for_woodlands_2702(self):
        mod = load_analyzer()
        # CAUSEWAY bus/car queue and upper outbound BKE queue belong to towards_jb
        self.assertEqual(mod.classify_direction("2702", 1100, 740, 1920, 1069), "towards_jb")
        self.assertEqual(mod.classify_direction("2702", 1220, 860, 1920, 1069), "towards_jb")
        self.assertEqual(mod.classify_direction("2702", 490, 100, 1920, 1069), "towards_jb")
        # BKE exit carriageway belongs to towards_sg, but BKE City overhead gantry sign is ignored
        self.assertEqual(mod.classify_direction("2702", 380, 500, 1920, 1069), "towards_sg")
        self.assertEqual(mod.classify_direction("2702", 420, 920, 1920, 1069), "ignored")

    def test_tuas_contraflow_windows(self):
        mod = load_analyzer()
        # Weekday morning contraflow
        self.assertTrue(mod.is_tuas_contraflow("2026-11-23T07:30:00+08:00"))
        # Sunday night return contraflow (10:31 PM SGT)
        self.assertTrue(mod.is_tuas_contraflow("2026-11-22T22:31:00+08:00"))
        # Midday weekday (no contraflow)
        self.assertFalse(mod.is_tuas_contraflow("2026-11-23T14:00:00+08:00"))

    def test_direction_zones_for_tuas_4703(self):
        mod = load_analyzer()
        # 4703 covers towards_sg (upper-right carriageway) and towards_jb (lower curved viaduct & bike ramp); sea is ignored
        self.assertEqual(mod.classify_direction("4703", 1250, 220, 1920, 1069, "2026-11-23T14:00:00+08:00"), "towards_sg")
        self.assertEqual(mod.classify_direction("4703", 820, 450, 1920, 1069, "2026-11-23T14:00:00+08:00"), "towards_jb")
        self.assertEqual(mod.classify_direction("4703", 200, 400, 1920, 1069, "2026-11-23T14:00:00+08:00"), "ignored")
        # During Sunday night contraflow, middle viaduct lanes belong to towards_sg
        self.assertEqual(mod.classify_direction("4703", 1100, 380, 1920, 1069, "2026-11-22T22:31:00+08:00"), "towards_sg")

    def test_direction_zones_for_tuas_4713(self):
        mod = load_analyzer()
        # 4713 right-hand JOHOR queue + bottom bike lane are towards_jb; left AYE & concrete median barrier are ignored
        self.assertEqual(mod.classify_direction("4713", 1450, 350, 1920, 1069), "towards_jb")
        self.assertEqual(mod.classify_direction("4713", 600, 840, 1920, 1069), "towards_jb")
        self.assertEqual(mod.classify_direction("4713", 600, 420, 1920, 1069), "ignored")
        self.assertEqual(mod.classify_direction("4713", 1540, 700, 1920, 1069), "ignored")

    def test_worker_and_python_polygons_stay_in_sync(self):
        import re

        mod = load_analyzer()
        worker_src = (ROOT / "workers" / "sgalerts-ai.js").read_text(encoding="utf-8")
        m = re.search(r"const CAMERA_ZONES = (\{.*?\n\});", worker_src, re.S)
        self.assertIsNotNone(m, "CAMERA_ZONES block missing in workers/sgalerts-ai.js")
        js_obj = re.sub(r"//[^\n]*", "", m.group(1))
        js_obj = re.sub(r"(\b[a-zA-Z_][a-zA-Z0-9_]*\b)\s*:", r'"\1":', js_obj)
        js_obj = re.sub(r",\s*([}\]])", r"\1", js_obj)
        worker_zones = json.loads(js_obj)

        for cid in ("2701", "2702", "4703", "4713"):
            py_cfg = mod.CAMERA_ZONES[cid]
            js_cfg = worker_zones[cid]
            for key in ("zones", "contraflow_zones"):
                if key in py_cfg:
                    self.assertIn(key, js_cfg, f"{cid}.{key} missing in worker")
                    for direction, poly in py_cfg[key].items():
                        expected = [[x, y] for x, y in poly]
                        self.assertEqual(js_cfg[key][direction], expected, f"Polygon drift in {cid}.{key}.{direction}")

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

    def test_yolo11_4class_decoder_maps_to_coco_vehicle_ids(self):
        import numpy as np

        mod = load_analyzer()
        # Synthetic YOLO11 4-class ONNX output: shape (1, 8, 2) -> 2 anchors
        # Anchor 0: class 0 (car -> COCO 2), Anchor 1: class 1 (motorcycle -> COCO 3)
        raw = [np.zeros((1, 8, 2), dtype=np.float32)]
        raw[0][0, :4, 0] = [100.0, 200.0, 40.0, 30.0]
        raw[0][0, 4, 0] = 0.85
        raw[0][0, :4, 1] = [300.0, 400.0, 15.0, 20.0]
        raw[0][0, 5, 1] = 0.72

        xywh, cls_ids, conf = mod.decode_yolo11_outputs(raw)
        self.assertEqual(xywh.shape, (2, 4))
        self.assertEqual(list(cls_ids), [2, 3])
        self.assertAlmostEqual(float(conf[0]), 0.85, places=5)
        self.assertAlmostEqual(float(conf[1]), 0.72, places=5)

    def test_2702_bike_viaduct_estimator_empty_returns_zero(self):
        from PIL import Image

        mod = load_analyzer()
        empty_night = Image.new("RGB", (1920, 1069), (45, 48, 52))
        self.assertEqual(mod.estimate_2702_bike_viaduct_count(empty_night), 0)

    def test_4703_visual_contraflow_headlights_vs_taillights(self):
        from PIL import Image, ImageDraw

        mod = load_analyzer()
        # Saturday night (outside scheduled contraflow) with blazing saturated white headlights in wedge -> True
        img_white = Image.new("RGB", (1920, 1069), (30, 32, 38))
        ImageDraw.Draw(img_white).rectangle([800, 300, 1300, 500], fill=(250, 250, 246))
        self.assertTrue(mod.detect_4703_contraflow(img_white, "2026-11-21T21:00:00+08:00"))

        # Normal Monday night with white car roofs (220,220,220) and red taillights -> must NOT false-trigger contraflow
        img_normal = Image.new("RGB", (1920, 1069), (30, 32, 38))
        ImageDraw.Draw(img_normal).rectangle([800, 300, 1200, 480], fill=(220, 220, 220))
        ImageDraw.Draw(img_normal).rectangle([1200, 420, 1360, 520], fill=(210, 40, 40))
        self.assertFalse(mod.detect_4703_contraflow(img_normal, "2026-11-23T20:31:00+08:00"))

        # Sunday night (inside scheduled contraflow) with strong red tail-lights in wedge -> visually overrides to False
        img_red = Image.new("RGB", (1920, 1069), (30, 32, 38))
        ImageDraw.Draw(img_red).rectangle([800, 300, 1300, 500], fill=(220, 40, 40))
        self.assertFalse(mod.detect_4703_contraflow(img_red, "2026-11-22T21:00:00+08:00"))

    def test_yolo26_e2e_decoder_and_smart_zoom_subtiles(self):
        import numpy as np

        mod = load_analyzer()
        # Synthetic YOLO26 NMS-free E2E output: shape (1, 2, 6) -> [x1, y1, x2, y2, conf, cls]
        raw = [np.array([[[10.0, 20.0, 50.0, 60.0, 0.91, 0.0], [100.0, 120.0, 130.0, 150.0, 0.84, 1.0]]], dtype=np.float32)]
        xyxy, cls_ids, conf = mod.decode_yolo26_e2e_outputs(raw)
        self.assertEqual(xyxy.shape, (2, 4))
        self.assertEqual(list(cls_ids), [2, 3])
        self.assertAlmostEqual(float(conf[0]), 0.91, places=5)

        subtiles = mod.split_smart_zoom_subtiles(300, 200, 1100, 800)
        self.assertEqual(len(subtiles), 4)
        for sx1, sy1, sx2, sy2 in subtiles:
            self.assertGreaterEqual(sx1, 300)
            self.assertGreaterEqual(sy1, 200)
            self.assertLessEqual(sx2, 1100)
            self.assertLessEqual(sy2, 800)
            self.assertLess(sx1, sx2)
            self.assertLess(sy1, sy2)

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
