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
  // All 4 cameras use Vision 24/7 returning BOTH raw vehicle counts AND lane fill tiers ("empty"|"sparse"|"moderate"|"heavy"|"packed")
  // so dense queues never undercount while empty/sparse roads stay exact.
  "2701": 'Singapore LTA traffic cam 2701 (Woodlands Causeway). Landmarks: 3 thick WHITE WATER PIPES on lower-right = TOWARDS SG (WOODLANDS); outermost lanes closest to OPEN SEA on upper-left = TOWARDS JB (JOHOR). For each direction give raw counts AND lane fill tier ("empty"|"sparse"|"moderate"|"heavy"|"packed"): car_fill and bike_fill (packed = continuous solid bumper-to-bumper queue stretching across the bridge; heavy = long queue >50% of bridge; moderate = noticeable cluster; sparse = few scattered vehicles; empty = 0-2). Reply ONLY valid JSON: {"towards_jb":{"car":0,"motorcycle":0,"heavy":0,"car_fill":"sparse","bike_fill":"sparse"},"towards_sg":{"car":0,"motorcycle":0,"heavy":0,"car_fill":"sparse","bike_fill":"sparse"}}',
  "2702": 'Singapore LTA traffic cam 2702 (Woodlands Checkpoint/BKE). THREE zones: (1) Left elevated ramp (BKE) = TOWARDS SG. (2) Upper-right narrow curved elevated viaduct = STRICTLY MOTORCYCLES TOWARDS JB (never count as cars; if solid wall of bikes along the curve set bike_fill="packed"). (3) Lower wide lanes (CAUSEWAY) = cars/buses/trucks TOWARDS JB (set car_fill="packed" if backed up solid). Use fill tiers "empty"|"sparse"|"moderate"|"heavy"|"packed". Reply ONLY valid JSON: {"towards_jb":{"car":0,"motorcycle":0,"heavy":0,"car_fill":"sparse","bike_fill":"sparse"},"towards_sg":{"car":0,"motorcycle":0,"heavy":0,"car_fill":"sparse","bike_fill":"sparse"}}',
  "4703": 'Singapore LTA traffic cam 4703 (Tuas Second Link). Diagonal concrete divider splits the frame: (1) ABOVE/RIGHT of divider = TOWARDS SG: cars/trucks plus far-right motorcycle lane (set car_fill="packed" if cars queue to top-left; set bike_fill="packed" if far-right lane has a dense mass of bikes). (2) BELOW/LEFT of divider (curved ramp under JOHOR + lower barrier lane) = TOWARDS JB: count motorcycles and vehicles on curved ramp/bottom lane (set bike_fill="heavy" or "packed" if steady stream of 20+ bikes). Fill tiers: "empty"|"sparse"|"moderate"|"heavy"|"packed". Reply ONLY valid JSON: {"towards_jb":{"car":0,"motorcycle":0,"heavy":0,"car_fill":"sparse","bike_fill":"sparse"},"towards_sg":{"car":0,"motorcycle":0,"heavy":0,"car_fill":"sparse","bike_fill":"sparse"}}',
  "4703_contraflow": 'Singapore LTA traffic cam 4703 during weekday morning contraflow (Tuas Second Link). Orange cones split the lower viaduct. TOWARDS SG = upper-right & middle motorcycle sea + bottom-right guardhouse bike lane + cars along orange-cone contraflow lane + far-right lorries/buses (set bike_fill="packed" if massive sea of bikes; car_fill="heavy"/"packed" if lined up along cones). TOWARDS JB = only vehicles on inner-left lane below orange cones under JOHOR. Fill tiers: "empty"|"sparse"|"moderate"|"heavy"|"packed". Reply ONLY valid JSON: {"towards_jb":{"car":0,"motorcycle":0,"heavy":0,"car_fill":"sparse","bike_fill":"sparse"},"towards_sg":{"car":0,"motorcycle":0,"heavy":0,"car_fill":"sparse","bike_fill":"sparse"}}',
  "4713": 'Singapore LTA traffic cam 4713 (Tuas Outbound to Johor). Right-hand viaduct labeled JOHOR + bottom horizontal bike lane = TOWARDS JB (ignore left AYE ramp). Look closely at TWO separate lanes on the right viaduct: (1) Left 2 lanes of JOHOR viaduct = CARS (set car_fill="packed" if 2 solid lines of cars stretch all the way up the bridge; "heavy" if halfway). (2) Right edge of JOHOR viaduct directly under yellow JOHOR label + bottom foreground lane = MOTORCYCLES (set bike_fill="packed" if thick solid stream of bikes stretches up past JOHOR label; "heavy" if long queue). Fill tiers: "empty"|"sparse"|"moderate"|"heavy"|"packed". Reply ONLY valid JSON: {"towards_jb":{"car":0,"motorcycle":0,"heavy":0,"car_fill":"sparse","bike_fill":"sparse"}}',
};

const FILL_FLOORS = {
  "2701": {
    jb: { car: { moderate: 10, heavy: 25, packed: 50 }, bike: { moderate: 15, heavy: 40, packed: 90 } },
    sg: { car: { moderate: 12, heavy: 28, packed: 55 }, bike: { moderate: 20, heavy: 50, packed: 110 } },
  },
  "2702": {
    jb: { car: { moderate: 15, heavy: 35, packed: 65 }, bike: { moderate: 30, heavy: 80, packed: 150 } },
    sg: { car: { moderate: 8, heavy: 18, packed: 35 }, bike: { moderate: 8, heavy: 20, packed: 45 } },
  },
  "4703": {
    jb: { car: { moderate: 8, heavy: 18, packed: 35 }, bike: { moderate: 12, heavy: 28, packed: 50 } },
    sg: { car: { moderate: 12, heavy: 26, packed: 45 }, bike: { moderate: 15, heavy: 38, packed: 70 } },
  },
  "4703_contraflow": {
    jb: { car: { moderate: 6, heavy: 14, packed: 28 }, bike: { moderate: 10, heavy: 24, packed: 45 } },
    sg: { car: { moderate: 12, heavy: 26, packed: 45 }, bike: { moderate: 35, heavy: 80, packed: 150 } },
  },
  "4713": {
    jb: { car: { moderate: 16, heavy: 38, packed: 68 }, bike: { moderate: 20, heavy: 50, packed: 95 } },
    sg: { car: {}, bike: {} },
  },
};

function applyFillFloor(rawVal, tier, table) {
  const key = String(tier || "").toLowerCase().trim();
  const floor = (table && table[key]) ? table[key] : 0;
  return Math.max(rawVal, floor);
}

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
      max_tokens: 200,
      temperature: 0.1,
    });
    const parsed = parseJsonObject(res?.choices?.[0]?.message?.content || res?.response || res);
    if (!parsed || !parsed.towards_jb) return detectCameraDetr(env, cam, buf);

    const clamp = (n) => Math.max(0, Math.min(250, Math.round(Number(n) || 0)));
    const jb = parsed.towards_jb || {};
    const sg = cam.camera_id === "4713" ? {} : (parsed.towards_sg || {});
    const floors = FILL_FLOORS[promptKey] || { jb: { car: {}, bike: {} }, sg: { car: {}, bike: {} } };

    const jbCar = applyFillFloor(clamp(jb.car), jb.car_fill, floors.jb.car);
    const jbMoto = applyFillFloor(clamp(jb.motorcycle), jb.bike_fill, floors.jb.bike);
    const jbHeavy = clamp(jb.heavy);
    const sgCar = applyFillFloor(clamp(sg.car), sg.car_fill, floors.sg.car);
    const sgMoto = applyFillFloor(clamp(sg.motorcycle), sg.bike_fill, floors.sg.bike);
    const sgHeavy = clamp(sg.heavy);

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
