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
  // All 4 cameras use high-res Vision 24/7 returning BOTH lane fill percentage (0-100) FIRST and raw vehicle counts.
  // Empty/light lanes (<30% full) use exact raw counts; congested lanes (>=30% full) calibrate against physical lane capacity.
  "2701": 'Singapore LTA traffic cam 2701 (Woodlands Causeway). Two directions on the diagonal bridge: (1) towards_jb = upper-left lanes labeled JOHOR closest to the open water; (2) towards_sg = lower-right lanes labeled WOODLANDS directly beside the 3 thick white water pipes. Do NOT count empty bridge deck or reflections. If clear gaps of empty road appear between vehicles, car_pct MUST be 25 or less; only use 60-100 if vehicles form a solid bumper-to-bumper queue. Separate buses/trucks into heavy (not car). Reply ONLY compact JSON: {"towards_jb":{"car_pct":0,"bike_pct":0,"car":0,"motorcycle":0,"heavy":0},"towards_sg":{"car_pct":0,"bike_pct":0,"car":0,"motorcycle":0,"heavy":0}}',
  "2702": 'Singapore LTA traffic cam 2702 (Woodlands Checkpoint/BKE). Map EXACTLY to these two JSON keys: (1) towards_jb = BOTH the lower-right wide lanes labeled CAUSEWAY (cars/buses/trucks) AND the upper-right narrow curved elevated viaduct carrying ONLY MOTORCYCLES (this curved right-side motorcycle viaduct is ALWAYS towards_jb.bike_pct and towards_jb.motorcycle, NEVER towards_sg!). (2) towards_sg = ONLY the straight far-left elevated ramp labeled BKE (typically light/moderate traffic; do NOT put right-side viaduct bikes here). Estimate car_pct and bike_pct (0-100) FIRST, then counts. Reply ONLY compact JSON: {"towards_jb":{"car_pct":0,"bike_pct":0,"car":0,"motorcycle":0,"heavy":0},"towards_sg":{"car_pct":0,"bike_pct":0,"car":0,"motorcycle":0,"heavy":0}}',
  "4703": 'Singapore LTA traffic cam 4703 (Tuas Second Link). Diagonal concrete divider splits the frame into two JSON keys: (1) towards_jb = BELOW/LEFT of the divider (curved ramp under yellow JOHOR label + bottom foreground barrier lane): count cars, motorcycles, and large lorries/buses on that curved ramp. (2) towards_sg = ABOVE/RIGHT of the divider: cars/trucks queueing toward top-left PLUS the far-right motorcycle lane at the right edge of the frame (check the far-right edge carefully for clustered SG-bound motorcycles; do NOT count guardhouses/booths as trucks). Estimate car_pct and bike_pct (0-100) FIRST, then counts. Reply ONLY compact JSON: {"towards_jb":{"car_pct":0,"bike_pct":0,"car":0,"motorcycle":0,"heavy":0},"towards_sg":{"car_pct":0,"bike_pct":0,"car":0,"motorcycle":0,"heavy":0}}',
  "4703_contraflow": 'Singapore LTA traffic cam 4703 during weekday morning contraflow (Tuas Second Link). Orange cones split the lower viaduct. towards_jb = ONLY vehicles on the inner-left lane below the orange cones under JOHOR. towards_sg = upper-right & middle motorcycle sea + bottom-right guardhouse bike lane + cars along orange-cone contraflow lane + far-right lorries/buses. Estimate car_pct and bike_pct (0-100) FIRST, then counts. Reply ONLY compact JSON: {"towards_jb":{"car_pct":0,"bike_pct":0,"car":0,"motorcycle":0,"heavy":0},"towards_sg":{"car_pct":0,"bike_pct":0,"car":0,"motorcycle":0,"heavy":0}}',
  "4713": 'Singapore LTA traffic cam 4713 (Tuas Outbound to Johor). IGNORE the empty left AYE road and trees completely! Look ONLY at the right-side viaduct labeled JOHOR + bottom horizontal foreground bike lane (all towards_jb): (1) Car lanes on the left side of the JOHOR viaduct — if lines of cars stretch past the yellow JOHOR sign to the top gantry, car_pct is 85-100. (2) Motorcycle lane on the right edge directly under the yellow JOHOR sign plus bikes on the bottom horizontal foreground lane — if a busy queue of bikes fills that right lane past the sign, bike_pct is 60-100. (3) Count buses/trucks on the far-right lower lane as heavy. Estimate car_pct and bike_pct (0-100) FIRST, then counts. Reply ONLY compact JSON: {"towards_jb":{"car_pct":0,"bike_pct":0,"car":0,"motorcycle":0,"heavy":0}}',
};

const MODEL_VERSION = "v6-mistral-calibrated";

// Physical visible lane capacities (vehicles visible in frame when 100% packed end-to-end)
const LANE_MAX_CAP = {
  "2701": { jb: { car: 55, bike: 90 }, sg: { car: 60, bike: 110 } },
  "2702": { jb: { car: 72, bike: 165 }, sg: { car: 35, bike: 45 } },
  "4703": { jb: { car: 35, bike: 55 }, sg: { car: 48, bike: 75 } },
  "4703_contraflow": { jb: { car: 28, bike: 45 }, sg: { car: 48, bike: 160 } },
  "4713": { jb: { car: 70, bike: 95 }, sg: { car: 0, bike: 0 } },
};

function applyPctFloor(rawVal, pctVal, maxCap) {
  const pct = Math.max(0, Math.min(100, Number(pctVal) || 0));
  if (!maxCap) return rawVal;
  if (pct < 30) return Math.min(rawVal, Math.round(maxCap * 0.45));
  const pctEst = Math.round((pct / 100) * maxCap);
  const ceiling = Math.round(maxCap * 1.15);
  return Math.min(Math.max(rawVal, pctEst), ceiling);
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
    const messages = [
      { role: "system", content: "You are a traffic camera counter. Output ONLY one compact valid JSON object matching the schema. No markdown fences, no commentary." },
      { role: "user", content: [
        { type: "text", text: prompt },
        { type: "image_url", image_url: { url: "data:image/jpeg;base64," + toB64(buf) } }
      ]}
    ];
    let res;
    try {
      res = await env.AI.run("@cf/mistralai/mistral-small-3.1-24b-instruct", {
        messages,
        response_format: { type: "json_object" },
        max_tokens: 220,
        temperature: 0.1,
      });
    } catch {
      res = await env.AI.run("@cf/meta/llama-4-scout-17b-16e-instruct", {
        messages,
        response_format: { type: "json_object" },
        max_tokens: 220,
        temperature: 0.1,
      });
    }
    const rawText = res?.choices?.[0]?.message?.content ?? res?.response ?? res;
    const parsed = parseJsonObject(rawText);
    if (!parsed || !parsed.towards_jb) return detectCameraDetr(env, cam, buf);

    const clamp = (n) => Math.max(0, Math.min(250, Math.round(Number(n) || 0)));
    const jb = parsed.towards_jb || {};
    const sg = cam.camera_id === "4713" ? {} : (parsed.towards_sg || {});
    const caps = LANE_MAX_CAP[promptKey] || { jb: { car: 0, bike: 0 }, sg: { car: 0, bike: 0 } };

    const jbCar = applyPctFloor(clamp(jb.car), jb.car_pct, caps.jb.car);
    const jbMoto = applyPctFloor(clamp(jb.motorcycle), jb.bike_pct, caps.jb.bike);
    const jbHeavy = clamp(jb.heavy);
    const sgCar = applyPctFloor(clamp(sg.car), sg.car_pct, caps.sg.car);
    const sgMoto = applyPctFloor(clamp(sg.motorcycle), sg.bike_pct, caps.sg.bike);
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
    if (!force && cachedResp && cachedData?.model_version === MODEL_VERSION) {
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

      // Free-tier guard: even with ?refresh=1, never re-run AI if LTA's photo timestamp & model version haven't changed
      if (cachedData && cachedData.ok && cachedData.last_updated === latestTs && cachedData.model_version === MODEL_VERSION) {
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
        model_version: MODEL_VERSION,
        model: "Workers AI Mistral-3.1 Vision (live)",
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
