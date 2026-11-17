"""
Analyze live LTA Woodlands & Tuas checkpoint camera images with Apache-2.0 YOLOX-S (ONNX)
and lane direction polygons, writing data/checkpoint-traffic.json and data/checkpoint-history.json.
"""

from __future__ import annotations

import io
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parents[1]
CHECKPOINTS_FILE = BASE_DIR / "data" / "checkpoints.json"
TRAFFIC_FILE = BASE_DIR / "data" / "checkpoint-traffic.json"
HISTORY_FILE = BASE_DIR / "data" / "checkpoint-history.json"
MODEL_PATH = BASE_DIR / ".cache" / "models" / "yolox_s.onnx"
MODEL_URL = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.onnx"

SGT = timezone(timedelta(hours=8), name="SGT")
VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
MAX_HISTORY_ENTRIES = 2880  # ~30 days (4 weeks) at 15-minute cadence
DASHBOARD_CAMERA_IDS = {
    "woodlands": ["2701", "2702"],
    "tuas": ["4703", "4713"],
}

# Direction polygons in 1920x1069 camera pixel space for the 2 dashboard cameras per checkpoint.
# Detections outside all road polygons (trees, sea reflections, distant buildings) are ignored.
CAMERA_ZONES = {
    "2701": {
        "name": "Woodlands Causeway",
        "zones": {
            "towards_jb": [(220, 920), (1920, 140), (1920, 275), (420, 1020)],
            "towards_sg": [(420, 1020), (1920, 275), (1920, 420), (680, 1069)],
        },
    },
    "2702": {
        "name": "Woodlands Checkpoint / BKE",
        "zones": {
            "towards_jb": [(540, 220), (1920, 400), (1920, 1069), (600, 1069)],
            "towards_sg": [(260, 0), (580, 0), (570, 1069), (260, 1069)],
        },
    },
    "4703": {
        "name": "Tuas Second Link",
        "zones": {
            # Above/right of central divider: traffic heading into Singapore
            "towards_sg": [(185, 0), (1200, 0), (1920, 320), (1920, 650), (1320, 420), (700, 175)],
            # Lower/left viaduct & curved ramp (hugging deck, excluding sea/piers): bikes & vehicles towards JB
            "towards_jb": [(0, 0), (185, 0), (700, 175), (1320, 420), (1760, 580), (1720, 880), (1160, 950), (1050, 740), (780, 720), (200, 880), (0, 880), (0, 680), (650, 480), (680, 350), (0, 130)],
        },
    },
    "4713": {
        "name": "Tuas Checkpoint (Outbound to Johor)",
        "zones": {
            # Right-hand viaduct heading towards Johor (SG-bound handled by 4703)
            "towards_jb": [(1180, 20), (1860, 20), (1920, 480), (1920, 740), (1200, 580)],
        },
    },
    "4712": {
        "name": "AYE / Tuas Checkpoint",
        "zones": {
            "towards_jb": [(250, 0), (720, 0), (1100, 1069), (240, 1069)],
            "towards_sg": [(720, 0), (1920, 0), (1920, 1069), (1100, 1069)],
        },
    },
}


def point_in_polygon(x: float, y: float, polygon: list[tuple[int, int]]) -> bool:
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def classify_direction(camera_id: str, cx: float, cy: float, width: int, height: int) -> str:
    # Normalize coordinates to 1920x1069 reference frame
    nx = cx * (1920.0 / max(1, width))
    ny = cy * (1069.0 / max(1, height))
    cam_cfg = CAMERA_ZONES.get(str(camera_id))
    if not cam_cfg:
        return "other"
    for direction, poly in cam_cfg["zones"].items():
        if point_in_polygon(nx, ny, poly):
            return direction
    return "ignored"


def load_level(weighted_score: float, smooth_max: float = 25.0, moderate_max: float = 45.0) -> str:
    if weighted_score <= smooth_max:
        return "Smooth"
    if weighted_score <= moderate_max:
        return "Moderate"
    return "Heavy"


def ensure_model() -> Path:
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not MODEL_PATH.exists() or MODEL_PATH.stat().st_size < 10_000_000:
        print(f"Downloading YOLOX-S ONNX model to {MODEL_PATH}...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    return MODEL_PATH


def preprocess_crop(img, input_size=(640, 640)):
    import numpy as np
    from PIL import Image

    w, h = img.size
    scale = min(input_size[0] / h, input_size[1] / w)
    nw, nh = int(w * scale), int(h * scale)
    resized = img.resize((nw, nh), Image.BILINEAR)
    padded = Image.new("RGB", (input_size[1], input_size[0]), (114, 114, 114))
    padded.paste(resized, (0, 0))
    arr = np.asarray(padded, dtype=np.float32)[:, :, ::-1].transpose(2, 0, 1)[None, ...]
    return arr, scale


def decode_outputs(outputs, img_size=(640, 640)):
    import numpy as np

    preds = outputs[0][0]
    if np.max(np.abs(preds[:, :2])) >= 20.0:
        return preds
    grids, expanded_strides = [], []
    for s in (8, 16, 32):
        hs, ws = img_size[0] // s, img_size[1] // s
        xv, yv = np.meshgrid(np.arange(ws), np.arange(hs))
        grid = np.stack((xv, yv), 2).reshape(1, -1, 2)
        grids.append(grid)
        expanded_strides.append(np.full((*grid.shape[:2], 1), s))
    grids_arr = np.concatenate(grids, 1)[0]
    strides_arr = np.concatenate(expanded_strides, 1)[0]
    decoded = preds.copy()
    decoded[:, :2] = (decoded[:, :2] + grids_arr) * strides_arr
    decoded[:, 2:4] = np.exp(decoded[:, 2:4]) * strides_arr
    return decoded


def nms(boxes, scores, iou_thresh: float = 0.40) -> list[int]:
    import numpy as np

    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
        order = order[np.where(iou <= iou_thresh)[0] + 1]
    return keep


def detect_vehicles(sess, img, conf_thresh: float = 0.20):
    import numpy as np

    inp_name = sess.get_inputs()[0].name
    out_name = sess.get_outputs()[0].name
    W, H = img.size
    regions = [(0, 0, W, H)]
    if W >= 640 and H >= 640:
        xs = [0, max(0, (W - 640) // 2), max(0, W - 640)]
        ys = [0, max(0, H - 640)]
        for y in ys:
            for x in xs:
                regions.append((x, y, x + 640, y + 640))

    all_boxes, all_scores, all_cls = [], [], []
    for rx1, ry1, rx2, ry2 in regions:
        crop = img.crop((rx1, ry1, rx2, ry2))
        blob, scale = preprocess_crop(crop)
        raw = sess.run([out_name], {inp_name: blob})
        preds = decode_outputs(raw)
        cls_scores = preds[:, 5:] * preds[:, 4:5]
        cls_ids = cls_scores.argmax(axis=1)
        conf = cls_scores.max(axis=1)
        mask = (conf >= conf_thresh) & np.isin(cls_ids, list(VEHICLE_CLASSES.keys()))
        filt = preds[mask]
        if not len(filt):
            continue
        cx, cy, bw, bh = filt[:, 0], filt[:, 1], filt[:, 2], filt[:, 3]
        boxes = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], axis=1) / scale
        boxes[:, [0, 2]] += rx1
        boxes[:, [1, 3]] += ry1
        areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        valid = areas < (0.08 * W * H)
        if np.any(valid):
            all_boxes.append(boxes[valid])
            all_scores.append(conf[mask][valid])
            all_cls.append(cls_ids[mask][valid])

    if not all_boxes:
        return np.empty((0, 4)), np.empty((0,)), np.empty((0,), dtype=int)
    boxes = np.concatenate(all_boxes, axis=0)
    scores = np.concatenate(all_scores, axis=0)
    clss = np.concatenate(all_cls, axis=0)
    keep = nms(boxes, scores, 0.40)
    return boxes[keep], scores[keep], clss[keep]


def analyze_checkpoint_group(sess, cameras: list[dict]) -> dict:
    from PIL import Image

    totals = {"car": 0, "motorcycle": 0, "bus": 0, "truck": 0}
    directions = {"towards_jb": 0, "towards_sg": 0}
    weighted_jb = 0.0
    weighted_sg = 0.0
    cam_summaries = []

    for cam in cameras:
        cid = str(cam.get("camera_id", ""))
        url = cam.get("image")
        if not url:
            continue
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        except Exception as exc:
            cam_summaries.append({"camera_id": cid, "error": str(exc)})
            continue

        W, H = img.size
        boxes, _, clss = detect_vehicles(sess, img)
        cam_counts = {"car": 0, "motorcycle": 0, "bus": 0, "truck": 0}
        cam_dir = {"towards_jb": 0, "towards_sg": 0}

        for box, cls_id in zip(boxes, clss):
            cx = float((box[0] + box[2]) / 2.0)
            cy = float((box[1] + box[3]) / 2.0)
            direction = classify_direction(cid, cx, cy, W, H)
            if direction == "ignored":
                continue
            label = VEHICLE_CLASSES[int(cls_id)]
            weight = 0.5 if label == "motorcycle" else (2.0 if label in ("bus", "truck") else 1.0)
            cam_counts[label] += 1
            totals[label] += 1
            if direction in cam_dir:
                cam_dir[direction] += 1
                directions[direction] += 1
                if direction == "towards_jb":
                    weighted_jb += weight
                else:
                    weighted_sg += weight

        cam_summaries.append({
            "camera_id": cid,
            "label": CAMERA_ZONES.get(cid, {}).get("name", f"Camera {cid}"),
            "timestamp": cam.get("timestamp"),
            "total_vehicles": sum(cam_counts.values()),
            "towards_jb": cam_dir["towards_jb"],
            "towards_sg": cam_dir["towards_sg"],
            "counts": cam_counts,
        })

    weighted_total = totals["car"] + 0.5 * totals["motorcycle"] + 2.0 * (totals["bus"] + totals["truck"])
    return {
        "status": load_level(weighted_total, smooth_max=25.0, moderate_max=45.0),
        "towards_jb_status": load_level(weighted_jb, smooth_max=20.0, moderate_max=36.0),
        "towards_sg_status": load_level(weighted_sg, smooth_max=20.0, moderate_max=36.0),
        "total_vehicles": sum(totals.values()),
        "weighted_load": round(weighted_total, 1),
        "towards_jb": directions["towards_jb"],
        "towards_sg": directions["towards_sg"],
        "counts": totals,
        "cameras": cam_summaries,
    }


def compute_hourly_averages(snapshots: list[dict]) -> dict:
    buckets: dict[str, dict] = {}
    for snap in snapshots:
        ts = snap.get("timestamp_sgt")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            continue
        key = f"{dt.strftime('%a')}-{dt.hour:02d}"
        entry = buckets.setdefault(
            key,
            {"day": dt.strftime("%a"), "hour": dt.hour, "samples": 0, "woodlands_sum": 0.0, "tuas_sum": 0.0},
        )
        entry["samples"] += 1
        entry["woodlands_sum"] += float(snap.get("woodlands_load", 0))
        entry["tuas_sum"] += float(snap.get("tuas_load", 0))

    summary = []
    for item in buckets.values():
        n = max(1, item["samples"])
        summary.append({
            "day": item["day"],
            "hour": item["hour"],
            "samples": n,
            "woodlands_avg_load": round(item["woodlands_sum"] / n, 1),
            "tuas_avg_load": round(item["tuas_sum"] / n, 1),
        })
    return {"by_day_hour": summary}


def update_history(traffic: dict) -> dict:
    existing = {"snapshots": []}
    if HISTORY_FILE.exists():
        try:
            existing = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = {"snapshots": []}

    snapshots = existing.get("snapshots") if isinstance(existing.get("snapshots"), list) else []
    now_sgt = datetime.now(SGT)
    snap = {
        "timestamp_sgt": now_sgt.isoformat(),
        "woodlands_status": traffic["woodlands"]["status"],
        "woodlands_vehicles": traffic["woodlands"]["total_vehicles"],
        "woodlands_load": traffic["woodlands"]["weighted_load"],
        "woodlands_to_jb": traffic["woodlands"]["towards_jb"],
        "woodlands_to_sg": traffic["woodlands"]["towards_sg"],
        "tuas_status": traffic["tuas"]["status"],
        "tuas_vehicles": traffic["tuas"]["total_vehicles"],
        "tuas_load": traffic["tuas"]["weighted_load"],
        "tuas_to_jb": traffic["tuas"]["towards_jb"],
        "tuas_to_sg": traffic["tuas"]["towards_sg"],
    }
    snapshots.append(snap)
    snapshots = snapshots[-MAX_HISTORY_ENTRIES:]

    history = {
        "model": "YOLOX-S ONNX (road-zone vehicle detection)",
        "last_updated": traffic["last_updated"],
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
        **compute_hourly_averages(snapshots),
    }
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
    return history


def select_dashboard_cameras(cameras: list[dict], location_key: str) -> list[dict]:
    wanted = DASHBOARD_CAMERA_IDS.get(location_key, [])
    by_id = {str(cam.get("camera_id", "")): cam for cam in cameras}
    selected = [by_id[cid] for cid in wanted if cid in by_id]
    return selected if selected else cameras[:2]


def main() -> None:
    import onnxruntime as ort

    if not CHECKPOINTS_FILE.exists():
        raise FileNotFoundError(f"Missing {CHECKPOINTS_FILE}")
    checkpoints = json.loads(CHECKPOINTS_FILE.read_text(encoding="utf-8"))

    model_path = ensure_model()
    sess = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])

    now_utc = datetime.now(timezone.utc)
    woodlands = analyze_checkpoint_group(sess, select_dashboard_cameras(checkpoints.get("woodlands", []), "woodlands"))
    tuas = analyze_checkpoint_group(sess, select_dashboard_cameras(checkpoints.get("tuas", []), "tuas"))

    traffic = {
        "model": "YOLOX-S ONNX (COCO vehicles in calibrated road polygons)",
        "source_name": checkpoints.get("source_name", "LTA / data.gov.sg"),
        "last_updated": now_utc.isoformat(),
        "note": "AI counts visible vehicles on public LTA approach cameras. Actual immigration counter queues inside the complex may differ.",
        "woodlands": woodlands,
        "tuas": tuas,
    }
    TRAFFIC_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRAFFIC_FILE.write_text(json.dumps(traffic, indent=2), encoding="utf-8")
    history = update_history(traffic)

    print(
        f"AI Traffic -> Woodlands: {woodlands['status']} ({woodlands['total_vehicles']} vehicles, "
        f"JB:{woodlands['towards_jb']} SG:{woodlands['towards_sg']}) | "
        f"Tuas: {tuas['status']} ({tuas['total_vehicles']} vehicles, "
        f"JB:{tuas['towards_jb']} SG:{tuas['towards_sg']}) | History samples: {history['snapshot_count']}"
    )


if __name__ == "__main__":
    main()
