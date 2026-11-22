"""
Analyze live LTA Woodlands & Tuas checkpoint camera images with Apache-2.0 YOLOX-M (ONNX)
using per-camera road-focused SAHI zoom tiles and lane direction polygons, writing
data/checkpoint-traffic.json and data/checkpoint-history.json.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parents[1]
CHECKPOINTS_FILE = BASE_DIR / "data" / "checkpoints.json"
TRAFFIC_FILE = BASE_DIR / "data" / "checkpoint-traffic.json"
HISTORY_FILE = BASE_DIR / "data" / "checkpoint-history.json"
CUSTOM_MODEL_PATH = BASE_DIR / ".cache" / "models" / "sgalerts_custom.onnx"
MODEL_PATH = BASE_DIR / ".cache" / "models" / "yolox_m.onnx"
MODEL_URL = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_m.onnx"

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
            # Upper-left carriageway of the Causeway deck: outbound traffic heading to Johor Bahru
            "towards_jb": [(330, 940), (1920, 235), (1920, 340), (560, 1045)],
            # Lower-right carriageway & motorcycle lane beside the 3 white water pipes: inbound traffic to Woodlands
            "towards_sg": [(560, 1045), (1920, 340), (1920, 430), (680, 1069)],
        },
    },
    "2702": {
        "name": "Woodlands Checkpoint / BKE",
        "zones": {
            "towards_jb": [(520, 220), (1920, 400), (1920, 1069), (545, 1069)],
            "towards_sg": [(300, 0), (510, 0), (535, 1069), (300, 1069)],
        },
    },
    "4703": {
        "name": "Tuas Second Link",
        "zones": {
            # Above/right of central divider: traffic heading into Singapore
            "towards_sg": [(185, 0), (1200, 0), (1920, 320), (1920, 650), (1320, 420), (700, 175)],
            # Lower/left viaduct & curved ramp (hugging deck, excluding sea/piers): bikes & vehicles towards JB
            "towards_jb": [(0, 0), (185, 0), (700, 175), (1320, 420), (1760, 580), (1720, 880), (1160, 950), (750, 920), (200, 1040), (0, 1040), (0, 680), (650, 480), (680, 350), (0, 130)],
        },
        # Weekday morning contraflow (05:00-10:00 SGT): orange cones split the viaduct so outer/middle lanes carry JB->SG traffic
        "contraflow_zones": {
            "towards_sg": [(185, 0), (1920, 0), (1920, 860), (1760, 840), (1620, 725), (1320, 555), (1020, 415), (720, 285), (460, 185), (185, 65)],
            "towards_jb": [(0, 0), (185, 0), (185, 65), (460, 185), (720, 285), (1020, 415), (1320, 555), (1620, 725), (1760, 840), (1720, 880), (1160, 950), (750, 920), (200, 1040), (0, 1040), (0, 680), (650, 480), (680, 350), (0, 130)],
        },
    },
    "4713": {
        "name": "Tuas Checkpoint (Outbound to Johor)",
        "zones": {
            # Right-hand viaduct heading towards Johor + bottom horizontal motorcycle approach lane (excludes median barrier block)
            "towards_jb": [(1180, 20), (1860, 20), (1920, 480), (1920, 910), (0, 910), (0, 770), (1380, 770), (1200, 560)],
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


def is_tuas_contraflow(iso_ts: str | None) -> bool:
    try:
        dt = datetime.fromisoformat(iso_ts) if iso_ts else datetime.now(SGT)
        dt_sgt = dt.astimezone(SGT)
    except Exception:
        dt_sgt = datetime.now(SGT)
    hour = dt_sgt.hour + dt_sgt.minute / 60.0
    return dt_sgt.weekday() < 5 and 5.0 <= hour < 10.0


def classify_direction(camera_id: str, cx: float, cy: float, width: int, height: int, iso_ts: str | None = None) -> str:
    # Normalize coordinates to 1920x1069 reference frame
    nx = cx * (1920.0 / max(1, width))
    ny = cy * (1069.0 / max(1, height))
    cam_cfg = CAMERA_ZONES.get(str(camera_id))
    if not cam_cfg:
        return "other"
    zones = cam_cfg["contraflow_zones"] if ("contraflow_zones" in cam_cfg and is_tuas_contraflow(iso_ts)) else cam_cfg["zones"]
    for direction, poly in zones.items():
        if point_in_polygon(nx, ny, poly):
            return direction
    return "ignored"


def load_level(weighted_score: float, smooth_max: float = 25.0, moderate_max: float = 45.0) -> str:
    if weighted_score <= smooth_max:
        return "Smooth"
    if weighted_score <= moderate_max:
        return "Moderate"
    return "Heavy"


# Per-camera road-focused SAHI zoom tiles in 1920x1069 reference coordinates.
# Concentrates inference resolution on distant Causeway/viaduct decks & motorcycle lanes
# instead of wasting compute on sky, sea, and buildings.
CAMERA_TILES = {
    "2701": [
        (1220, 200, 1920, 520),   # Far Causeway deck (small distant cars & buses)
        (920, 360, 1620, 740),    # Mid-far Causeway deck & inbound motorcycle lane
        (560, 520, 1320, 960),    # Mid Causeway deck & water-pipe motorcycle lane
        (260, 680, 1080, 1069),   # Near Causeway deck (both directions)
    ],
    "2702": [
        (300, 0, 1060, 520),      # Distant BKE / Woodlands Checkpoint lanes
        (300, 260, 1260, 860),    # Mid BKE both directions
        (860, 340, 1920, 1069),   # Right outbound queues towards Woodlands
        (280, 520, 1260, 1069),   # Lower inbound & outbound lanes
    ],
    "4703": [
        (100, 0, 1020, 420),      # Far Tuas Second Link viaduct
        (560, 120, 1520, 680),    # Mid viaduct both directions & contraflow zone
        (1160, 220, 1920, 840),   # Right viaduct towards SG / contraflow
        (0, 360, 960, 1040),      # Lower-left curved motorcycle & car ramp
        (740, 480, 1780, 1040),   # Lower-mid viaduct ramp towards JB
    ],
    "4713": [
        (1160, 10, 1880, 520),    # Far JOHOR viaduct top
        (1180, 320, 1920, 920),   # Mid JOHOR viaduct merge
        (0, 620, 800, 960),       # Bottom horizontal motorcycle approach (left)
        (600, 620, 1440, 960),    # Bottom horizontal motorcycle approach (mid-right)
    ],
    "4712": [
        (240, 0, 1120, 580),      # Distant AYE towards Tuas
        (240, 460, 1180, 1069),   # Near AYE towards Tuas
        (720, 0, 1920, 600),      # Distant AYE towards SG
        (900, 460, 1920, 1069),   # Near AYE towards SG
    ],
}


def ensure_model() -> Path:
    custom_env = os.environ.get("SGALERTS_CUSTOM_ONNX", "").strip()
    if custom_env:
        env_path = Path(custom_env)
        if env_path.exists() and env_path.stat().st_size > 1_000_000:
            return env_path
    if CUSTOM_MODEL_PATH.exists() and CUSTOM_MODEL_PATH.stat().st_size > 1_000_000:
        return CUSTOM_MODEL_PATH
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not MODEL_PATH.exists() or MODEL_PATH.stat().st_size < 50_000_000:
        print(f"Downloading YOLOX-M ONNX model to {MODEL_PATH}...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    return MODEL_PATH


def build_camera_tiles(camera_id: str | None, width: int, height: int) -> list[tuple[int, int, int, int]]:
    regions: list[tuple[int, int, int, int]] = [(0, 0, width, height)]
    if width < 640 or height < 640:
        return regions
    preset = CAMERA_TILES.get(str(camera_id or ""))
    if preset:
        sx, sy = width / 1920.0, height / 1069.0
        for x1, y1, x2, y2 in preset:
            rx1 = max(0, min(width - 1, int(round(x1 * sx))))
            ry1 = max(0, min(height - 1, int(round(y1 * sy))))
            rx2 = max(rx1 + 1, min(width, int(round(x2 * sx))))
            ry2 = max(ry1 + 1, min(height, int(round(y2 * sy))))
            regions.append((rx1, ry1, rx2, ry2))
        return regions
    xs = [0, max(0, (width - 640) // 2), max(0, width - 640)]
    ys = [0, max(0, height - 640)]
    for y in ys:
        for x in xs:
            regions.append((x, y, min(width, x + 640), min(height, y + 640)))
    return regions


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


def detect_vehicles(sess, img, camera_id: str | None = None, conf_thresh: float = 0.25, bike_conf_thresh: float = 0.15):
    import numpy as np

    inp_name = sess.get_inputs()[0].name
    out_name = sess.get_outputs()[0].name
    W, H = img.size
    regions = build_camera_tiles(camera_id, W, H)

    all_boxes, all_scores, all_cls = [], [], []
    for rx1, ry1, rx2, ry2 in regions:
        crop = img.crop((rx1, ry1, rx2, ry2))
        blob, scale = preprocess_crop(crop)
        raw = sess.run([out_name], {inp_name: blob})
        preds = decode_outputs(raw)
        cls_scores = preds[:, 5:] * preds[:, 4:5]
        cls_ids = cls_scores.argmax(axis=1)
        conf = cls_scores.max(axis=1)
        is_veh = np.isin(cls_ids, list(VEHICLE_CLASSES.keys()))
        is_bike = (cls_ids == 3) & (conf >= bike_conf_thresh)
        is_other = (cls_ids != 3) & is_veh & (conf >= conf_thresh)
        mask = is_bike | is_other
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


def analyze_checkpoint_group(sess, cameras: list[dict], save_samples_dir: Path | None = None) -> dict:
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
            if save_samples_dir is not None:
                save_samples_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(SGT).strftime("%Y%m%d_%H%M%S")
                img.save(save_samples_dir / f"cam_{cid}_{stamp}.jpg", quality=92)
        except Exception as exc:
            cam_summaries.append({"camera_id": cid, "error": str(exc)})
            continue

        W, H = img.size
        boxes, _, clss = detect_vehicles(sess, img, camera_id=cid)
        cam_counts = {"car": 0, "motorcycle": 0, "bus": 0, "truck": 0}
        cam_dir = {"towards_jb": 0, "towards_sg": 0}

        for box, cls_id in zip(boxes, clss):
            cx = float((box[0] + box[2]) / 2.0)
            cy = float((box[1] + box[3]) / 2.0)
            direction = classify_direction(cid, cx, cy, W, H, cam.get("timestamp"))
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
    jb_status = load_level(weighted_jb, smooth_max=15.0, moderate_max=27.0)
    sg_status = load_level(weighted_sg, smooth_max=15.0, moderate_max=27.0)
    return {
        "status": load_level(max(weighted_jb, weighted_sg), smooth_max=15.0, moderate_max=27.0),
        "towards_jb_status": jb_status,
        "towards_sg_status": sg_status,
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
        "model": "YOLOX-M ONNX (road-zone SAHI tiled detection)",
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

    parser = argparse.ArgumentParser(description="Analyze LTA checkpoint cameras with YOLOX-M ONNX.")
    parser.add_argument(
        "--save-samples",
        type=Path,
        default=None,
        help="Optional directory to archive raw camera frames for Colab distillation/fine-tuning.",
    )
    args = parser.parse_args()

    if not CHECKPOINTS_FILE.exists():
        raise FileNotFoundError(f"Missing {CHECKPOINTS_FILE}")
    checkpoints = json.loads(CHECKPOINTS_FILE.read_text(encoding="utf-8"))

    model_path = ensure_model()
    sess = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])

    now_utc = datetime.now(timezone.utc)
    woodlands = analyze_checkpoint_group(
        sess,
        select_dashboard_cameras(checkpoints.get("woodlands", []), "woodlands"),
        save_samples_dir=args.save_samples,
    )
    tuas = analyze_checkpoint_group(
        sess,
        select_dashboard_cameras(checkpoints.get("tuas", []), "tuas"),
        save_samples_dir=args.save_samples,
    )

    model_label = (
        f"Custom Distilled ONNX ({model_path.name})"
        if model_path.name != MODEL_PATH.name
        else "YOLOX-M ONNX (road-zone SAHI tiled detection)"
    )
    traffic = {
        "model": model_label,
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
