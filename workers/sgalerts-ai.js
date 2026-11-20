const CORS = {
  "Access-Control-Allow-Origin": "https://sgalerts.com",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

const VEHICLE_MAP = {
  car: "car",
  motorcycle: "motorcycle",
  motorbike: "motorcycle",
  bicycle: "motorcycle",
  bus: "bus",
  truck: "truck",
};

const CAMERA_ZONES = {
  "2701": {
    name: "Woodlands Causeway",
    zones: {
      // Upper-left carriageway of the Causeway deck: outbound traffic heading to Johor Bahru
      towards_jb: [[330, 940], [1920, 235], [1920, 340], [560, 1045]],
      // Lower-right carriageway & motorcycle lane beside the 3 white water pipes: inbound traffic to Woodlands
      towards_sg: [[560, 1045], [1920, 340], [1920, 430], [680, 1069]],
    },
  },
  "2702": {
    name: "Woodlands Checkpoint / BKE",
    zones: {
      towards_jb: [[520, 220], [1920, 400], [1920, 1069], [545, 1069]],
      towards_sg: [[300, 0], [510, 0], [535, 1069], [300, 1069]],
    },
  },
  "4703": {
    name: "Tuas Second Link",
    zones: {
      towards_sg: [[185, 0], [1200, 0], [1920, 320], [1920, 650], [1320, 420], [700, 175]],
      towards_jb: [[0, 0], [185, 0], [700, 175], [1320, 420], [1760, 580], [1720, 880], [1160, 950], [750, 920], [200, 1040], [0, 1040], [0, 680], [650, 480], [680, 350], [0, 130]],
    },
    // Weekday morning contraflow (05:00-10:00 SGT): orange cones split the viaduct so outer/middle lanes carry JB->SG traffic
    contraflow_zones: {
      towards_sg: [[185, 0], [1920, 0], [1920, 860], [1760, 840], [1620, 725], [1320, 555], [1020, 415], [720, 285], [460, 185], [185, 65]],
      towards_jb: [[0, 0], [185, 0], [185, 65], [460, 185], [720, 285], [1020, 415], [1320, 555], [1620, 725], [1760, 840], [1720, 880], [1160, 950], [750, 920], [200, 1040], [0, 1040], [0, 680], [650, 480], [680, 350], [0, 130]],
    },
  },
  "4713": {
    name: "Tuas Checkpoint (Outbound to Johor)",
    zones: {
      // Right-hand JOHOR viaduct + bottom horizontal motorcycle approach lane (excludes left AYE ramp & median barrier block)
      towards_jb: [[1180, 20], [1860, 20], [1920, 480], [1920, 910], [0, 910], [0, 770], [1380, 770], [1200, 560]],
    },
  },
};

const MODEL_VERSION = "v10-yolox-detr-calibrated";

function isTuasContraflow(isoTs) {
  const d = isoTs ? new Date(isoTs) : new Date();
  const sgt = new Date(d.getTime() + 8 * 3600 * 1000);
  const day = sgt.getUTCDay(); // 1=Mon .. 5=Fri
  const hour = sgt.getUTCHours() + sgt.getUTCMinutes() / 60;
  return day >= 1 && day <= 5 && hour >= 5.0 && hour < 10.0;
}

function pointInPoly(x, y, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    const intersect = ((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / ((yj - yi) || 1e-9) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

function classifyDirection(camId, cx, cy, isoTs) {
  const cfg = CAMERA_ZONES[camId];
  if (!cfg) return "other";
  const zones = (cfg.contraflow_zones && isTuasContraflow(isoTs)) ? cfg.contraflow_zones : cfg.zones;
  for (const [dir, poly] of Object.entries(zones)) {
    if (pointInPoly(cx, cy, poly)) return dir;
  }
  return "ignored";
}

function iou(a, b) {
  const ix1 = Math.max(a.xmin, b.xmin), iy1 = Math.max(a.ymin, b.ymin);
  const ix2 = Math.min(a.xmax, b.xmax), iy2 = Math.min(a.ymax, b.ymax);
  const inter = Math.max(0, ix2 - ix1) * Math.max(0, iy2 - iy1);
  if (!inter) return 0;
  const areaA = (a.xmax - a.xmin) * (a.ymax - a.ymin);
  const areaB = (b.xmax - b.xmin) * (b.ymax - b.ymin);
  return inter / (areaA + areaB - inter + 1e-6);
}

function nms(dets, thresh = 0.42) {
  const sorted = [...dets].sort((a, b) => b.score - a.score);
  const keep = [];
  for (const d of sorted) {
    if (keep.every(k => iou(k.box, d.box) <= thresh)) keep.push(d);
  }
  return keep;
}

function loadLevel(score, smoothMax = 15, modMax = 27) {
  if (score <= smoothMax) return "Smooth";
  if (score <= modMax) return "Moderate";
  return "Heavy";
}

async function detectCameraDetr(env, cam) {
  const imgRes = await fetch(cam.image);
  if (!imgRes.ok) throw new Error("Failed image " + cam.camera_id);
  const buf = await imgRes.arrayBuffer();
  const detections = await env.AI.run("@cf/facebook/detr-resnet-50", { image: [...new Uint8Array(buf)] });
  const list = Array.isArray(detections) ? detections : (detections?.result || []);

  const candidateBoxes = [];
  for (const det of list) {
    const score = Number(det.score || 0);
    const label = VEHICLE_MAP[String(det.label || "").toLowerCase()];
    if (!label || !det.box) continue;
    const minScore = label === "motorcycle" ? 0.16 : 0.25;
    if (score < minScore) continue;
    const { xmin, ymin, xmax, ymax } = det.box;
    const isNorm = xmax <= 1.05 && ymax <= 1.05;
    const scaleX = isNorm ? 1920 : (1920 / 1333);
    const scaleY = isNorm ? 1069 : (1069 / 800);
    const box = {
      xmin: Number(xmin) * scaleX,
      ymin: Number(ymin) * scaleY,
      xmax: Number(xmax) * scaleX,
      ymax: Number(ymax) * scaleY,
    };
    const area = (box.xmax - box.xmin) * (box.ymax - box.ymin);
    if (area > 0.08 * 1920 * 1069) continue;
    candidateBoxes.push({ label, score, box });
  }

  const kept = nms(candidateBoxes, 0.42);
  const counts = { car: 0, motorcycle: 0, bus: 0, truck: 0 };
  const dir = { towards_jb: 0, towards_sg: 0 };
  let wJb = 0, wSg = 0;

  for (const det of kept) {
    const cx = (det.box.xmin + det.box.xmax) / 2;
    const cy = (det.box.ymin + det.box.ymax) / 2;
    const d = classifyDirection(String(cam.camera_id), cx, cy, cam.timestamp);
    if (d !== "towards_jb" && d !== "towards_sg") continue;

    counts[det.label] += 1;
    dir[d] += 1;
    const w = det.label === "motorcycle" ? 0.5 : (det.label === "bus" || det.label === "truck") ? 2.0 : 1.0;
    if (d === "towards_jb") wJb += w;
    else wSg += w;
  }

  return {
    camera_id: String(cam.camera_id),
    label: CAMERA_ZONES[cam.camera_id]?.name || ("Camera " + cam.camera_id),
    timestamp: cam.timestamp,
    total_vehicles: counts.car + counts.motorcycle + counts.bus + counts.truck,
    towards_jb: dir.towards_jb,
    towards_sg: dir.towards_sg,
    counts,
    wJb,
    wSg,
  };
}

function summarizeGroup(camResults) {
  const counts = { car: 0, motorcycle: 0, bus: 0, truck: 0 };
  let jb = 0, sg = 0, wJb = 0, wSg = 0;
  for (const c of camResults) {
    for (const k of Object.keys(counts)) counts[k] += c.counts[k];
    jb += c.towards_jb;
    sg += c.towards_sg;
    wJb += c.wJb;
    wSg += c.wSg;
  }
  const wTotal = counts.car + 0.5 * counts.motorcycle + 2.0 * (counts.bus + counts.truck);
  return {
    status: loadLevel(Math.max(wJb, wSg), 15, 27),
    towards_jb_status: loadLevel(wJb, 15, 27),
    towards_sg_status: loadLevel(wSg, 15, 27),
    total_vehicles: counts.car + counts.motorcycle + counts.bus + counts.truck,
    weighted_load: Math.round(wTotal * 10) / 10,
    towards_jb: jb,
    towards_sg: sg,
    counts,
    cameras: camResults.map(({ wJb: _a, wSg: _b, ...rest }) => rest),
  };
}

function getLatestCamTs(data) {
  const cams = [...(data?.woodlands?.cameras || []), ...(data?.tuas?.cameras || [])];
  const stamps = cams.map(c => c.timestamp).filter(Boolean).sort();
  return stamps.pop() || data?.last_updated || "";
}

export default {
  async fetch(request, env, ctx) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }
    const url = new URL(request.url);
    const force = url.searchParams.get("refresh") === "1";
    const cacheKey = new Request(url.origin + "/api/checkpoint-ai", { method: "GET" });
    const cache = caches.default;

    const cachedResp = await cache.match(cacheKey);
    let cachedData = null;
    if (cachedResp) {
      try {
        cachedData = await cachedResp.clone().json();
      } catch {}
    }

    if (!force && cachedResp && cachedData?.model_version === MODEL_VERSION) {
      return cachedResp;
    }

    let ghData = null;
    try {
      const ghRes = await fetch("https://raw.githubusercontent.com/cielworking/SGutility/main/data/checkpoint-traffic.json", {
        cf: { cacheTtl: 45, cacheEverything: true },
      });
      if (ghRes.ok) ghData = await ghRes.json();
    } catch {}

    try {
      const ltaRes = await fetch("https://api.data.gov.sg/v1/transport/traffic-images");
      if (!ltaRes.ok) throw new Error("LTA upstream " + ltaRes.status);
      const ltaData = await ltaRes.json();
      const allCams = ltaData?.items?.[0]?.cameras || [];
      const byId = Object.fromEntries(allCams.map(c => [String(c.camera_id), c]));

      const targetIds = ["2701", "2702", "4703", "4713"];
      const picked = targetIds.map(id => byId[id]).filter(Boolean);
      const latestTs = picked.map(c => c.timestamp).filter(Boolean).sort().pop() || new Date().toISOString();

      // 1. If GitHub Actions YOLOX-S is within 8 minutes of LTA's live frame, serve YOLOX-S at 0 Neurons
      const ghCamTs = getLatestCamTs(ghData);
      const ageMs = (Date.parse(latestTs) || 0) - (Date.parse(ghCamTs) || 0);
      if (ghData?.woodlands && ghData?.tuas && ageMs <= 8 * 60 * 1000) {
        const payload = { ...ghData, ok: true, model_version: MODEL_VERSION, source_mode: "yolox-github" };
        const resp = new Response(JSON.stringify(payload), {
          status: 200,
          headers: {
            ...CORS,
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "public, max-age=20, s-maxage=90",
            "X-AI-Cache": "GITHUB-YOLOX-FRESH",
          },
        });
        ctx.waitUntil(cache.put(cacheKey, resp.clone()));
        return resp;
      }

      // 2. If edge cache already ran DETR on this exact LTA frame timestamp, serve edge cache at 0 Neurons
      if (cachedData && cachedData.ok && getLatestCamTs(cachedData) === latestTs && cachedData.model_version === MODEL_VERSION) {
        return new Response(JSON.stringify(cachedData), {
          status: 200,
          headers: {
            ...CORS,
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "public, max-age=20, s-maxage=90",
            "X-AI-Cache": "HIT-SAME-TS",
          },
        });
      }

      // 3. GitHub cron lagged >8 min behind live camera: run real-time DETR-ResNet-50 bounding-box detector (~7 Neurons, zero VLM hallucination)
      const results = await Promise.all(picked.map(cam => detectCameraDetr(env, cam)));
      const woodlands = summarizeGroup(results.filter(r => r.camera_id === "2701" || r.camera_id === "2702"));
      const tuas = summarizeGroup(results.filter(r => r.camera_id === "4703" || r.camera_id === "4713"));

      const payload = {
        ok: true,
        model_version: MODEL_VERSION,
        model: "COCO Bounding-Box Detector (DETR-ResNet-50 live fallback)",
        source_mode: "detr-live-fallback",
        last_updated: latestTs,
        woodlands,
        tuas,
      };

      const resp = new Response(JSON.stringify(payload), {
        status: 200,
        headers: {
          ...CORS,
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": "public, max-age=20, s-maxage=90",
          "X-AI-Cache": "MISS-DETR-LIVE",
        },
      });
      ctx.waitUntil(cache.put(cacheKey, resp.clone()));
      return resp;
    } catch (err) {
      const fallback = (cachedData && cachedData.woodlands) ? cachedData : ghData;
      if (fallback && fallback.woodlands) {
        return new Response(JSON.stringify({ ...fallback, ok: true, model_version: MODEL_VERSION }), {
          status: 200,
          headers: { ...CORS, "Content-Type": "application/json; charset=utf-8", "X-AI-Cache": "FALLBACK" },
        });
      }
      return new Response(JSON.stringify({ ok: false, error: String(err) }), {
        status: 502,
        headers: { ...CORS, "Content-Type": "application/json; charset=utf-8" },
      });
    }
  },
};
