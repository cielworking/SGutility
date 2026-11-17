const KV_KEY = "reactions_v1";
const MAX_ITEMS = 100;
const MAX_AGE_SEC = 7 * 86400;
const MAX_DAILY_WRITES = 900;

const CORS = {
  "Access-Control-Allow-Origin": "https://sgalerts.com",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function pruneItems(items, nowSec) {
  const entries = Object.entries(items || {}).filter(([, v]) => {
    if (!v || typeof v !== "object") return false;
    const up = Number(v.up || 0);
    const down = Number(v.down || 0);
    const ts = Number(v.ts || 0);
    if (up <= 0 && down <= 0) return false;
    if (ts > 0 && nowSec - ts > MAX_AGE_SEC) return false;
    return true;
  });
  entries.sort((a, b) => Number(b[1].ts || 0) - Number(a[1].ts || 0));
  return Object.fromEntries(entries.slice(0, MAX_ITEMS));
}

async function loadState(env, nowSec, today) {
  let raw = null;
  try {
    raw = await env.REACTIONS_KV.get(KV_KEY, "json");
  } catch {}
  if (!raw || typeof raw !== "object") {
    return { day: today, writes: 0, items: {} };
  }
  const writes = raw.day === today ? Number(raw.writes || 0) : 0;
  const items = pruneItems(raw.items || {}, nowSec);
  return { day: today, writes, items };
}

export default {
  async fetch(request, env, ctx) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }

    const url = new URL(request.url);
    const cacheKey = new Request(url.origin + "/api/reactions", { method: "GET" });
    const cache = caches.default;
    const nowSec = Math.floor(Date.now() / 1000);
    const today = new Date().toISOString().slice(0, 10);

    if (request.method === "GET") {
      const cached = await cache.match(cacheKey);
      if (cached) return cached;

      const state = await loadState(env, nowSec, today);
      const resp = new Response(JSON.stringify({ ok: true, items: state.items, writes: state.writes }), {
        status: 200,
        headers: {
          ...CORS,
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": "public, max-age=5, s-maxage=15",
        },
      });
      ctx.waitUntil(cache.put(cacheKey, resp.clone()));
      return resp;
    }

    if (request.method === "POST") {
      let body = {};
      try {
        body = await request.json();
      } catch {
        return new Response(JSON.stringify({ ok: false, error: "Invalid JSON" }), { status: 400, headers: { ...CORS, "Content-Type": "application/json" } });
      }
      const id = String(body.id || "").trim().slice(0, 500);
      const add = body.add === "up" || body.add === "down" ? body.add : "";
      const remove = body.remove === "up" || body.remove === "down" ? body.remove : "";
      if (!id || (!add && !remove)) {
        return new Response(JSON.stringify({ ok: false, error: "Missing id or reaction" }), { status: 400, headers: { ...CORS, "Content-Type": "application/json" } });
      }

      const state = await loadState(env, nowSec, today);
      const current = state.items[id] || { up: 0, down: 0, ts: nowSec };
      if (remove) current[remove] = Math.max(0, Number(current[remove] || 0) - 1);
      if (add) current[add] = Math.max(0, Number(current[add] || 0) + 1);
      current.ts = nowSec;

      if (current.up <= 0 && current.down <= 0) {
        delete state.items[id];
      } else {
        state.items[id] = current;
      }
      state.items = pruneItems(state.items, nowSec);

      let mode = "kv";
      if (state.writes < MAX_DAILY_WRITES) {
        state.writes += 1;
        await env.REACTIONS_KV.put(KV_KEY, JSON.stringify(state), { expirationTtl: 14 * 86400 });
      } else {
        mode = "quota_guard_local";
      }

      const freshGet = new Response(JSON.stringify({ ok: true, items: state.items, writes: state.writes }), {
        status: 200,
        headers: {
          ...CORS,
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": "public, max-age=5, s-maxage=15",
        },
      });
      ctx.waitUntil(cache.put(cacheKey, freshGet));

      return new Response(JSON.stringify({
        ok: true,
        mode,
        id,
        counts: state.items[id] || { up: 0, down: 0 },
        items: state.items,
      }), {
        status: 200,
        headers: { ...CORS, "Content-Type": "application/json; charset=utf-8" },
      });
    }

    return new Response("Method not allowed", { status: 405, headers: CORS });
  }
};
