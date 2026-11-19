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
      towards_jb: [[220, 920], [1920, 140], [1920, 275], [420, 1020]],
      towards_sg: [[420, 1020], [1920, 275], [1920, 420], [680, 1069]],
    },
  },
  "2702": {
    name: "Woodlands Checkpoint / BKE",
    zones: {
      towards_jb: [[540, 220], [1920, 400], [1920, 1069], [600, 1069]],
      towards_sg: [[260, 0], [580, 0], [570, 1069], [260, 1069]],
    },
  },
  "4703": {
    name: "Tuas Second Link",
    zones: {
      towards_sg: [[185, 0], [1200, 0], [1920, 320], [1920, 650], [1320, 420], [700, 175]],
      towards_jb: [[0, 0], [185, 0], [700, 175], [1320, 420], [1760, 580], [1720, 880], [1160, 950], [1050, 740], [780, 720], [200, 880], [0, 880], [0, 680], [650, 480], [680, 350], [0, 130]],
    },
    // Weekday morning contraflow (05:00–10:00 SGT): orange cones split the viaduct so outer/middle lanes carry JB->SG traffic
    contraflow_zones: {
      towards_sg: [[185, 0], [1920, 0], [1920, 860], [1760, 840], [1620, 725], [1320, 555], [1020, 415], [720, 285], [460, 185], [185, 65]],
      towards_jb: [[0, 0], [185, 0], [185, 65], [460, 185], [720, 285], [1020, 415], [1320, 555], [1620, 725], [1760, 840], [1720, 880], [1160, 950], [1050, 740], [780, 720], [200, 880], [0, 880], [0, 680], [650, 480], [680, 350], [0, 130]],
    },
  },
  "4713": {
    name: "Tuas Checkpoint (Outbound to Johor)",
    zones: {
      // Right-hand JOHOR viaduct + bottom horizontal motorcycle approach lane (excludes left AYE ramp)
      towards_jb: [[1180, 20], [1860, 20], [1920, 480], [1920, 910], [0, 910], [0, 760], [1250, 760], [1200, 580]],
    },
  },
};

const NIGHT_PROMPTS = {
  // All 4 cameras use Vision 24/7 with density cues so packed motorcycle & Causeway queues are estimated accurately (DETR fallback on error).
  "2701": 'Singapore LTA traffic cam 2701 (Woodlands Causeway, day or night). Use the 3 thick WHITE WATER PIPES on the lower-right as your landmark: (1) The lanes CLOSEST TO THE WHITE PIPES (lower-right half of the bridge, labeled WOODLANDS) carry traffic TOWARDS SG — including the motorcycle lane directly hugging the pipes (if a continuous packed stream of bikes lines the pipes, estimate 100-200 motorcycles; if moderate, 30-80; if sparse, count exact bikes) plus cars and lorries/buses facing bottom-left. (2) The lanes CLOSEST TO THE OPEN SEA (upper-left half of the bridge, labeled JOHOR, furthest from the pipes) carry traffic TOWARDS JB (0-3 if empty). Do not confuse the two sides. Reply ONLY valid JSON: {"towards_jb":{"car":0,"motorcycle":0,"heavy":0},"towards_sg":{"car":0,"motorcycle":0,"heavy":0}}',
  // Cam 2702 uses Vision 24/7 so dense motorcycle queues on the upper curved flyover are counted accurately (DETR misses tiny packed bikes).
  "2702": 'Singapore LTA traffic cam 2702 (Woodlands Checkpoint/BKE, day or night). Left elevated ramp labeled BKE goes towards SG. On the right side: the narrow upper elevated curved flyover is the MOTORCYCLE lane towards JB (if packed bumper-to-bumper with bikes, estimate 120-220 motorcycles; if moderate queue, 30-90; if sparse/empty, count exact bikes); the lower lanes labeled CAUSEWAY carry cars/buses/trucks towards JB. Reply ONLY valid JSON: {"towards_jb":{"car":0,"motorcycle":0,"heavy":0},"towards_sg":{"car":0,"motorcycle":0,"heavy":0}}',
  // Cam 4703 uses Vision 24/7 to count dense SG-bound cars + far-right motorcycles above the diagonal divider.
  "4703": 'Singapore LTA traffic cam 4703 (Tuas Second Link, day or night). A diagonal central concrete divider runs from top-left down to middle-right. Everything ABOVE/RIGHT of this divider goes towards SG (count ALL queuing cars, trucks/buses, AND motorcycles in the far-right lane; estimate 60-140 total if backed up). Everything BELOW/LEFT of this divider (the curved viaduct/ramp under the JOHOR label) goes towards JB (count all motorcycles, cars, and trucks). Reply ONLY valid JSON: {"towards_jb":{"car":0,"motorcycle":0,"heavy":0},"towards_sg":{"car":0,"motorcycle":0,"heavy":0}}',
  "4703_contraflow": 'Singapore LTA traffic cam 4703 during weekday morning contraflow (Tuas Second Link). Orange cones split the lower viaduct. Count ALL vehicles heading into Singapore (towards_sg): (1) the massive upper-right & middle motorcycle queue plus the bottom-right motorcycle lane around the guardhouse (if packed shoulder-to-shoulder with a sea of bikes, estimate 150-250 motorcycles; if moderate queue, 40-100; if sparse, count exact bikes), (2) cars queuing along the orange-cone contraflow lane (15-45 if lined up along the cones), and (3) lorries/buses on the far upper-right viaduct. Only count vehicles on the inner-left curved lane (below/left of the orange cones under JOHOR) as towards_jb. Reply ONLY valid JSON: {"towards_jb":{"car":0,"motorcycle":0,"heavy":0},"towards_sg":{"car":0,"motorcycle":0,"heavy":0}}',
  // Cam 4713 uses Vision 24/7 to count dense JOHOR viaduct queues + the bottom motorcycle approach lane.
  "4713": 'Singapore LTA traffic cam 4713 (Tuas Outbound to Johor, day or night). Count ALL vehicles heading towards JB: (1) cars, buses, and motorcycles queuing on the right-hand viaduct labeled JOHOR (estimate 60-130 if backed up to the top), AND (2) motorcycles riding along the bottom horizontal lane at the bottom of the frame. Ignore the left AYE ramp (keep towards_sg 0). Reply ONLY valid JSON: {"towards_jb":{"car":0,"motorcycle":0,"heavy":0}}',
};

function isSgtNight(isoTs) {
  const d = isoTs ? new Date(isoTs) : new Date();
  const sgtHour = (d.getUTCHours() + 8 + d.getUTCMinutes() / 60) % 24;
  return sgtHour >= 19.0 || sgtHour < 6.75;
}

function isTuasContraflow(isoTs) {
  const d = isoTs ? new Date(isoTs) : new Date();
  const sgt = new Date(d.getTime() + 8 * 3600 * 1000);
  const day = sgt.getUTCDay(); // 1=Mon .. 5=Fri
  const hour = sgt.getUTCHours() + sgt.getUTCMinutes() / 60;
  return day >= 1 && day <= 5 && hour >= 5.0 && hour < 10.0;
}

function toB64(buf) {
  const u8 = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < u8.length; i += 8192) {
    s += String.fromCharCode(...u8.subarray(i, i + 8192));
  }
  return btoa(s);
}

function parseJsonObject(rawText) {
  if (!rawText) return null;
  if (typeof rawText === "object") return rawText;
  const s = String(rawText);
  const start = s.indexOf("{");
  const end = s.lastIndexOf("}");
  if (start === -1 || end <= start) return null;
  try {
    return JSON.parse(s.slice(start, end + 1));
  } catch {
    return null;
  }
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

function nms(dets, thresh = 0.45) {
  const sorted = [...dets].sort((a, b) => b.score - a.score);
  const keep = [];
  for (const d of sorted) {
    if (keep.every(k => iou(k.box, d.box) <= thresh)) keep.push(d);
  }
  return keep;
}

function loadLevel(score, smoothMax, modMax) {
  if (score <= smoothMax) return "Smooth";
  if (score <= modMax) return "Moderate";
  return "Heavy";
}

async function detectCameraDetr(env, cam, buf) {
  const detections = await env.AI.run("@cf/facebook/detr-resnet-50", { image: [...new Uint8Array(buf)] });
  const list = Array.isArray(detections) ? detections : (detections?.result || []);

  const candidateBoxes = [];
  for (const det of list) {
    const score = Number(det.score || 0);
    const label = VEHICLE_MAP[String(det.label || "").toLowerCase()];
    if (!label || !det.box) continue;
    const minScore = label === "motorcycle" ? 0.18 : 0.25;
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

  const kept = nms(candidateBoxes, 0.45);
  const counts = { car: 0, motorcycle: 0, bus: 0, truck: 0 };
  const dir = { towards_jb: 0, towards_sg: 0 };
  let wJb = 0, wSg = 0;

  for (const det of kept) {
    const cx = (det.box.xmin + det.box.xmax) / 2;
    const cy = (det.box.ymin + det.box.ymax) / 2;
    const d = classifyDirection(cam.camera_id, cx, cy, cam.timestamp);
    if (d !== "towards_jb" && d !== "towards_sg") continue;

    counts[det.label] += 1;
    dir[d] += 1;
    const w = det.label === "motorcycle" ? 0.5 : (det.label === "bus" || det.label === "truck") ? 2.0 : 1.0;
    if (d === "towards_jb") wJb += w;
    else wSg += w;
  }

  return {
    camera_id: cam.camera_id,
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

async function detectCameraNightVision(env, cam, buf) {
  const promptKey = (cam.camera_id === "4703" && isTuasContraflow(cam.timestamp)) ? "4703_contraflow" : cam.camera_id;
  const prompt = NIGHT_PROMPTS[promptKey];
  if (!prompt) return detectCameraDetr(env, cam, buf);
  try {
    const res = await env.AI.run("@cf/meta/llama-4-scout-17b-16e-instruct", {
      messages: [{ role: "user", content: [
        { type: "text", text: prompt },
        { type: "image_url", image_url: { url: "data:image/jpeg;base64," + toB64(buf) } }
      ]}],
      max_tokens: 150,
      temperature: 0.1,
    });
    const parsed = parseJsonObject(res?.choices?.[0]?.message?.content || res?.response || res);
    if (!parsed || !parsed.towards_jb) return detectCameraDetr(env, cam, buf);

    const clamp = (n) => Math.max(0, Math.min(250, Math.round(Number(n) || 0)));
    const jb = parsed.towards_jb || {};
    const sg = cam.camera_id === "4713" ? {} : (parsed.towards_sg || {});

    const jbCar = clamp(jb.car), jbMoto = clamp(jb.motorcycle), jbHeavy = clamp(jb.heavy);
    const sgCar = clamp(sg.car), sgMoto = clamp(sg.motorcycle), sgHeavy = clamp(sg.heavy);

    const counts = {
      car: jbCar + sgCar,
      motorcycle: jbMoto + sgMoto,
      bus: 0,
      truck: jbHeavy + sgHeavy,
    };
    const towards_jb = jbCar + jbMoto + jbHeavy;
    const towards_sg = sgCar + sgMoto + sgHeavy;
    const wJb = jbCar + 0.5 * jbMoto + 2.0 * jbHeavy;
    const wSg = sgCar + 0.5 * sgMoto + 2.0 * sgHeavy;

    return {
      camera_id: cam.camera_id,
      label: CAMERA_ZONES[cam.camera_id]?.name || ("Camera " + cam.camera_id),
      timestamp: cam.timestamp,
      total_vehicles: towards_jb + towards_sg,
      towards_jb,
      towards_sg,
      counts,
      wJb,
      wSg,
    };
  } catch {
    return detectCameraDetr(env, cam, buf);
  }
}

async function detectCamera(env, cam, nightMode) {
  const imgRes = await fetch(cam.image);
  if (!imgRes.ok) throw new Error("Failed image " + cam.camera_id);
  const buf = await imgRes.arrayBuffer();
  return detectCameraNightVision(env, cam, buf);
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
    status: loadLevel(wTotal, 25, 45),
    towards_jb_status: loadLevel(wJb, 20, 36),
    towards_sg_status: loadLevel(wSg, 20, 36),
    total_vehicles: counts.car + counts.motorcycle + counts.bus + counts.truck,
    weighted_load: Math.round(wTotal * 10) / 10,
    towards_jb: jb,
    towards_sg: sg,
    counts,
    cameras: camResults.map(({ wJb: _a, wSg: _b, ...rest }) => rest),
  };
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

    // Standard loads always use up to 120s shared edge cache (0 AI Neurons spent)
    if (!force && cachedResp) {
      return cachedResp;
    }

    try {
      const ltaRes = await fetch("https://api.data.gov.sg/v1/transport/traffic-images");
      if (!ltaRes.ok) throw new Error("LTA upstream " + ltaRes.status);
      const ltaData = await ltaRes.json();
      const allCams = ltaData?.items?.[0]?.cameras || [];
      const byId = Object.fromEntries(allCams.map(c => [String(c.camera_id), c]));

      const targetIds = ["2701", "2702", "4703", "4713"];
      const picked = targetIds.map(id => byId[id]).filter(Boolean);
      const latestTs = picked.map(c => c.timestamp).filter(Boolean).sort().pop() || new Date().toISOString();

      // Free-tier guard: even with ?refresh=1, never re-run AI if LTA's photo timestamp hasn't changed
      if (cachedData && cachedData.ok && cachedData.last_updated === latestTs) {
        return new Response(JSON.stringify(cachedData), {
          status: 200,
          headers: {
            ...CORS,
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "public, max-age=20, s-maxage=120",
            "X-AI-Cache": "HIT-SAME-TS",
          },
        });
      }

      const nightMode = isSgtNight(latestTs);
      const results = await Promise.all(picked.map(cam => detectCamera(env, cam, nightMode)));

      const woodlands = summarizeGroup(results.filter(r => r.camera_id === "2701" || r.camera_id === "2702"));
      const tuas = summarizeGroup(results.filter(r => r.camera_id === "4703" || r.camera_id === "4713"));

      const payload = {
        ok: true,
        model: nightMode ? "Workers AI Llama-4-Scout Vision (night live)" : "Workers AI Vision + DETR (day live)",
        last_updated: latestTs,
        woodlands,
        tuas,
      };

      const resp = new Response(JSON.stringify(payload), {
        status: 200,
        headers: {
          ...CORS,
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": "public, max-age=20, s-maxage=120",
          "X-AI-Cache": "MISS-FRESH",
        },
      });
      ctx.waitUntil(cache.put(cacheKey, resp.clone()));
      return resp;
    } catch (err) {
      if (cachedData && cachedData.ok) {
        return new Response(JSON.stringify(cachedData), {
          status: 200,
          headers: { ...CORS, "Content-Type": "application/json; charset=utf-8", "X-AI-Cache": "FALLBACK-CACHED" },
        });
      }
      return new Response(JSON.stringify({ ok: false, error: String(err) }), {
        status: 502,
        headers: { ...CORS, "Content-Type": "application/json; charset=utf-8" },
      });
    }
  }
};
