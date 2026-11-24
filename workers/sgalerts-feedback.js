const KV_KEY = "feedback_items_v1";
const MAX_ITEMS = 300;
const MAX_DAILY_SUBMISSIONS = 100;
const RATE_LIMIT_MAX = 5;
const RATE_LIMIT_WINDOW_SEC = 3600;

const ALLOWED_TOPICS = {
  feature: "Feature request",
  bug: "Bug / wrong data",
  checkpoints: "Checkpoints / AI",
  general: "General",
};

const ALLOWED_ORIGINS = new Set(["https://sgalerts.com", "https://www.sgalerts.com"]);

function corsHeaders(request) {
  const origin = request.headers.get("Origin") || "";
  return {
    "Access-Control-Allow-Origin": ALLOWED_ORIGINS.has(origin) ? origin : "https://sgalerts.com",
    "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    Vary: "Origin",
  };
}

function jsonResp(request, data, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      ...corsHeaders(request),
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      ...extraHeaders,
    },
  });
}

function constantTimeEqual(a, b) {
  if (!a || !b || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

function isAuthorized(request, env) {
  const secret = String(env.FEEDBACK_ADMIN_KEY || "").trim();
  if (!secret) return false;
  const auth = request.headers.get("Authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  return constantTimeEqual(token, secret);
}

async function hashIp(ip) {
  const data = new TextEncoder().encode("sga-fb:" + (ip || "unknown"));
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest)].slice(0, 8).map(b => b.toString(16).padStart(2, "0")).join("");
}

function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function formatSgtTime(iso) {
  try {
    const d = new Date(iso);
    const sgt = new Date(d.getTime() + 8 * 3600 * 1000);
    return sgt.toISOString().slice(0, 16).replace("T", " ") + " SGT";
  } catch {
    return iso;
  }
}

async function notifyTelegram(env, item) {
  const token = String(env.TELEGRAM_BOT_TOKEN || "").trim();
  const chatId = String(env.TELEGRAM_CHAT_ID || "").trim();
  if (!token || !chatId) return;

  const topicLabel = ALLOWED_TOPICS[item.topic] || "General";
  const stars = item.rating ? " · " + "★".repeat(item.rating) + "☆".repeat(5 - item.rating) : "";
  const lines = [
    `<b>💬 SG Alerts Feedback</b>`,
    `<b>${escapeHtml(topicLabel)}</b>${stars}`,
    `<b>Page:</b> ${escapeHtml(item.page || "/")}`,
  ];
  if (item.viewport) lines.push(`<b>Device:</b> ${escapeHtml(item.viewport)}`);
  if (item.email) lines.push(`<b>Reply to:</b> ${escapeHtml(item.email)}`);
  lines.push(`<b>Time:</b> ${escapeHtml(formatSgtTime(item.created_at))}`);
  lines.push("");
  lines.push(escapeHtml(item.message));

  await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text: lines.join("\n"),
      parse_mode: "HTML",
      disable_web_page_preview: true,
    }),
  });
}

async function loadItems(env) {
  try {
    const raw = await env.FEEDBACK_KV.get(KV_KEY, "json");
    return Array.isArray(raw) ? raw : [];
  } catch {
    return [];
  }
}

async function saveItems(env, items) {
  await env.FEEDBACK_KV.put(KV_KEY, JSON.stringify(items.slice(0, MAX_ITEMS)), {
    expirationTtl: 180 * 86400,
  });
}

export default {
  async fetch(request, env, ctx) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(request) });
    }

    // Public write-only submission endpoint
    if (request.method === "POST") {
      let body = {};
      try {
        body = await request.json();
      } catch {
        return jsonResp(request, { ok: false, error: "Invalid JSON" }, 400);
      }

      const rawTopic = String(body.topic || "general").trim().toLowerCase();
      const topic = Object.prototype.hasOwnProperty.call(ALLOWED_TOPICS, rawTopic) ? rawTopic : "general";
      const message = String(body.message || "").trim().slice(0, 2000);
      if (message.length < 3) {
        return jsonResp(request, { ok: false, error: "Please write at least 3 characters." }, 400);
      }

      const ratingNum = Number(body.rating);
      const rating = Number.isInteger(ratingNum) && ratingNum >= 1 && ratingNum <= 5 ? ratingNum : null;
      const email = String(body.email || "").trim().slice(0, 160);
      const page = String(body.page || "/").trim().slice(0, 300);
      const viewport = String(body.viewport || "").trim().slice(0, 40);

      // Global daily cap across all IPs (protects KV write quota & Telegram from distributed floods)
      const items = await loadItems(env);
      const today = new Date().toISOString().slice(0, 10);
      const todayCount = items.filter(i => String(i.created_at || "").startsWith(today)).length;
      if (todayCount >= MAX_DAILY_SUBMISSIONS) {
        return jsonResp(request, { ok: false, error: "Feedback inbox reached today's limit. Please try again tomorrow." }, 429);
      }

      // Per-IP rate limit (5 submissions per hour)
      const ip = request.headers.get("CF-Connecting-IP") || "";
      const rlKey = "rl:" + (await hashIp(ip));
      const curCount = Number((await env.FEEDBACK_KV.get(rlKey)) || 0);
      if (curCount >= RATE_LIMIT_MAX) {
        return jsonResp(request, { ok: false, error: "Too many submissions. Please try again later." }, 429);
      }

      const item = {
        id: "fb_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 7),
        created_at: new Date().toISOString(),
        topic,
        rating,
        message,
        email,
        page,
        viewport,
        status: "new",
      };

      items.unshift(item);
      await saveItems(env, items);
      ctx.waitUntil(env.FEEDBACK_KV.put(rlKey, String(curCount + 1), { expirationTtl: RATE_LIMIT_WINDOW_SEC }));
      try {
        await notifyTelegram(env, item);
      } catch {}

      return jsonResp(request, { ok: true, id: item.id }, 201);
    }

    // Strictly private admin endpoints (only owner with FEEDBACK_ADMIN_KEY can read/update/delete)
    if (!isAuthorized(request, env)) {
      return jsonResp(request, { ok: false, error: "Unauthorized" }, 401);
    }

    if (request.method === "GET") {
      const items = await loadItems(env);
      const telegramConfigured = Boolean(
        String(env.TELEGRAM_BOT_TOKEN || "").trim() && String(env.TELEGRAM_CHAT_ID || "").trim()
      );
      return jsonResp(request, { ok: true, telegram_configured: telegramConfigured, count: items.length, items });
    }

    if (request.method === "PATCH") {
      let body = {};
      try {
        body = await request.json();
      } catch {
        return jsonResp(request, { ok: false, error: "Invalid JSON" }, 400);
      }
      const id = String(body.id || "").trim();
      const status = body.status === "done" ? "done" : "new";
      if (!id) return jsonResp(request, { ok: false, error: "Missing id" }, 400);

      const items = await loadItems(env);
      const target = items.find(i => i.id === id);
      if (!target) return jsonResp(request, { ok: false, error: "Not found" }, 404);
      target.status = status;
      await saveItems(env, items);
      return jsonResp(request, { ok: true, item: target });
    }

    if (request.method === "DELETE") {
      const url = new URL(request.url);
      const id = String(url.searchParams.get("id") || "").trim();
      if (!id) return jsonResp(request, { ok: false, error: "Missing id" }, 400);

      const items = await loadItems(env);
      const next = items.filter(i => i.id !== id);
      await saveItems(env, next);
      return jsonResp(request, { ok: true, removed: items.length - next.length });
    }

    return jsonResp(request, { ok: false, error: "Method not allowed" }, 405);
  },
};
