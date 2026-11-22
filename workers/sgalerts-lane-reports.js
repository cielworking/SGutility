const CORS = {
  "Access-Control-Allow-Origin": "https://sgalerts.com",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

const VALID_CODES = {
  WLFC: { checkpoint: "woodlands", lane: "WL", status: "fc" },
  WLNFC: { checkpoint: "woodlands", lane: "WL", status: "nfc" },
  WRFC: { checkpoint: "woodlands", lane: "WR", status: "fc" },
  WRNFC: { checkpoint: "woodlands", lane: "WR", status: "nfc" },
  TLFC: { checkpoint: "tuas", lane: "TL", status: "fc" },
  TLNFC: { checkpoint: "tuas", lane: "TL", status: "nfc" },
  TRFC: { checkpoint: "tuas", lane: "TR", status: "fc" },
  TRNFC: { checkpoint: "tuas", lane: "TR", status: "nfc" },
};

const LANES = {
  WL: { checkpoint: "woodlands", label: "Woodlands Left", zone: "Zones 3 & 4", fcCode: "WLFC", nfcCode: "WLNFC" },
  WR: { checkpoint: "woodlands", label: "Woodlands Right", zone: "Zones 1 & 2", fcCode: "WRFC", nfcCode: "WRNFC" },
  TL: { checkpoint: "tuas", label: "Tuas Left", zone: "D2", fcCode: "TLFC", nfcCode: "TLNFC" },
  TR: { checkpoint: "tuas", label: "Tuas Right", zone: "D1", fcCode: "TRFC", nfcCode: "TRNFC" },
};

const RECENT_WINDOW_MS = 90 * 60 * 1000; // 90 minutes
const COOLDOWN_SECONDS = 600; // 10 minutes per lane per device
const MAX_REPORTS_PER_DAY = 500;

function getSgtDateInfo(nowMs = Date.now()) {
  const sgtMs = nowMs + 8 * 3600 * 1000;
  const d = new Date(sgtMs);
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  const dateKey = `${y}-${m}-${day}`;
  const nextMidnightSgtMs = Date.UTC(y, d.getUTCMonth(), d.getUTCDate() + 1, 0, 0, 0) - 8 * 3600 * 1000;
  const ttlSeconds = Math.max(120, Math.ceil((nextMidnightSgtMs - nowMs) / 1000) + 60);
  return { dateKey, ttlSeconds };
}

async function hashIp(ip, salt) {
  const data = new TextEncoder().encode(`${ip}|${salt}`);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest).slice(0, 8))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function summarize(reports, nowMs, dateKey) {
  const cutoff = nowMs - RECENT_WINDOW_MS;
  const lanes = {};

  for (const [laneId, meta] of Object.entries(LANES)) {
    let todayFc = 0, todayNfc = 0;
    let recentFc = 0, recentNfc = 0;
    let latest = null;

    for (const item of reports) {
      const spec = VALID_CODES[item.code];
      if (!spec || spec.lane !== laneId) continue;
      if (spec.status === "fc") todayFc++;
      else todayNfc++;
      if (item.ts >= cutoff) {
        if (spec.status === "fc") recentFc++;
        else recentNfc++;
      }
      if (!latest || item.ts > latest.ts) {
        latest = { code: item.code, status: spec.status, ts: item.ts };
      }
    }

    const todayTotal = todayFc + todayNfc;
    const recentTotal = recentFc + recentNfc;
    lanes[laneId] = {
      ...meta,
      today: {
        fc: todayFc,
        nfc: todayNfc,
        total: todayTotal,
        fc_pct: todayTotal ? Math.round((todayFc / todayTotal) * 100) : 0,
        nfc_pct: todayTotal ? Math.round((todayNfc / todayTotal) * 100) : 0,
      },
      recent_90m: {
        fc: recentFc,
        nfc: recentNfc,
        total: recentTotal,
        fc_pct: recentTotal ? Math.round((recentFc / recentTotal) * 100) : 0,
        nfc_pct: recentTotal ? Math.round((recentNfc / recentTotal) * 100) : 0,
      },
      latest,
    };
  }

  return {
    date_sgt: dateKey,
    recent_window_mins: 90,
    resets_at: "00:00 SGT daily",
    updated_at: new Date(nowMs).toISOString(),
    lanes,
  };
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      ...CORS,
    },
  });
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }

    const nowMs = Date.now();
    const { dateKey, ttlSeconds } = getSgtDateInfo(nowMs);
    const kvKey = `reports:${dateKey}`;

    if (request.method === "GET") {
      const raw = await env.LANE_REPORTS.get(kvKey, "json");
      const list = Array.isArray(raw) ? raw : [];
      return jsonResponse(summarize(list, nowMs, dateKey));
    }

    if (request.method === "POST") {
      let body = {};
      try {
        body = await request.json();
      } catch {
        return jsonResponse({ error: "Invalid JSON body" }, 400);
      }

      const code = String(body.code || "").trim().toUpperCase();
      const spec = VALID_CODES[code];
      if (!spec) {
        return jsonResponse({ error: "Invalid report code" }, 400);
      }

      const clientIp = request.headers.get("CF-Connecting-IP") || "anon";
      const ipHash = await hashIp(clientIp, dateKey);
      const rlKey = `rl:${dateKey}:${spec.lane}:${ipHash}`;
      const existingRl = await env.LANE_REPORTS.get(rlKey);
      if (existingRl) {
        const raw = await env.LANE_REPORTS.get(kvKey, "json");
        const list = Array.isArray(raw) ? raw : [];
        return jsonResponse(
          {
            error: "You already reported this lane recently. Please wait 10 minutes before updating again.",
            cooldown: true,
            ...summarize(list, nowMs, dateKey),
          },
          429
        );
      }

      const raw = await env.LANE_REPORTS.get(kvKey, "json");
      const list = Array.isArray(raw) ? raw : [];
      list.push({ code, ts: nowMs });
      const trimmed = list.slice(-MAX_REPORTS_PER_DAY);

      await Promise.all([
        env.LANE_REPORTS.put(kvKey, JSON.stringify(trimmed), { expirationTtl: ttlSeconds }),
        env.LANE_REPORTS.put(rlKey, "1", { expirationTtl: COOLDOWN_SECONDS }),
      ]);

      return jsonResponse({ ok: true, recorded: code, ...summarize(trimmed, nowMs, dateKey) });
    }

    return jsonResponse({ error: "Method not allowed" }, 405);
  },
};
