let coePrices = {};
let btoProjects = {};
let petrolPrices = {};
let petrolDiscounts = {};
let quickInfo = {};
let sgpoolsResults = {};
let newsResults = {};
let checkpointData = {};
let isRolling = false;
let selectedDiscountFuel = "ron95";
let hideGambling = localStorage.getItem("hideGambling") === "true";

async function loadData() {
  try {
    const needsNews = hasElement("news-result");
    const needsCheckpoint = hasElement("checkpointResult");
    const needsPetrol = hasElement("petrolResult");
    const needsCoe = hasElement("coeResult");
    const needsBto = hasElement("btoResult");
    const needsQuickInfo = hasElement("quickInfo");
    const needsSgPools = hasElement("sgpoolsResult");

    if (needsCoe) {
      coePrices = await fetch("./data/coe-prices.json").then(r => r.json());
    }

    if (needsBto) {
      btoProjects = await fetch("./data/bto-projects.json").then(r => r.json());
    }

    if (needsPetrol) {
      petrolPrices = await fetch("./data/petrol-prices.json").then(r => r.json());
      petrolDiscounts = await fetch("./data/petrol-discounts.json").then(r => r.json());
    }

    if (needsQuickInfo) {
      quickInfo = await fetch("./data/quick-info.json").then(r => r.json());
    }

    if (needsNews) {
      newsResults = await fetch("./data/news.json").then(r => r.json());
    }

    if (needsCheckpoint) {
      await refreshCheckpointData();
    }

    if (needsSgPools) {
      try {
        sgpoolsResults = await fetch("./data/sgpools-results.json").then(r => r.json());
        applyGamblingVisibility();
      } catch (e) {
        console.error("Singapore Pools results failed:", e);
      }
    }

    renderNews();
    renderCheckpoints();
    renderSourceLinks();
    renderCoePrices();
    renderBtoProjects();
    renderPetrolPrices();
    renderQuickInfo();

  } catch (err) {
    console.error("Dashboard load failed:", err);
  }
}

function hasElement(id) {
  return Boolean(document.getElementById(id));
}

async function refreshCheckpointData() {
  const btn = document.querySelector(".refresh-btn");

  if (btn) {
    btn.disabled = true;
    btn.textContent = "Refreshing...";
  }

  try {
    const res = await fetch("https://api.data.gov.sg/v1/transport/traffic-images");
    const payload = await res.json();

    const cameras = payload.items[0].cameras;

    const woodlands = [];
    const tuas = [];

    cameras.forEach(cam => {
      const lat = cam.location.latitude;
      const lon = cam.location.longitude;

      const item = {
        camera_id: cam.camera_id,
        image: cam.image,
        timestamp: cam.timestamp,
        latitude: lat,
        longitude: lon
      };

      if (lat >= 1.42 && lat <= 1.48 && lon >= 103.74 && lon <= 103.80) {
        woodlands.push(item);
      }

      if (lat >= 1.30 && lat <= 1.37 && lon >= 103.62 && lon <= 103.68) {
        tuas.push(item);
      }
    });

    checkpointData = {
      source_name: "LTA / data.gov.sg live API",
      source_url: "https://api.data.gov.sg/v1/transport/traffic-images",
      last_updated: new Date().toISOString(),
      woodlands,
      tuas
    };

    renderCheckpoints();

  } catch (err) {
    console.error("Live checkpoint refresh failed:", err);

    try {
      checkpointData = await fetch("./data/checkpoints.json").then(r => r.json());
      renderCheckpoints();
    } catch (fallbackErr) {
      console.error("Cached checkpoint data failed:", fallbackErr);
    }
  }

  if (btn) {
    btn.disabled = false;
    btn.textContent = "🔄 Refresh";
  }
}

function formatTimestamp(timestamp) {
  if (!timestamp) return "Unknown";

  return new Date(timestamp).toLocaleString("en-SG", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function money(value) {
  return new Intl.NumberFormat("en-SG", {
    style: "currency",
    currency: "SGD"
  }).format(value || 0);
}

function renderSourceLinks() {
  setSourceHref("coeSourceLink", coePrices.source_url);
  setSourceHref("btoSourceLink", btoProjects.source_url);
  setSourceHref("petrolSourceLink", petrolPrices.source_url);
  setSourceHref("quickSourceLink", quickInfo.source_url);

  if (sgpoolsResults.source_url) {
    setSourceHref("sgpoolsSourceLink", sgpoolsResults.source_url);
  }
}

function setSourceHref(id, url) {
  const link = document.getElementById(id);
  if (!link || !url) return;

  link.href = url;
}

/* =========================
   NEWS
   ========================= */

function renderNews() {
  const box = document.getElementById("news-result");
  if (!box) return;

  if (!newsResults.headlines || newsResults.headlines.length === 0) {
    box.innerHTML = "No headlines available.";
    return;
  }

  const topNews = newsResults.headlines.slice(0, 20);

  box.innerHTML = `
    <div class="news-topbar">
      <span>Last fetched: ${formatTimestamp(newsResults.last_updated)}</span>

      <div class="news-controls">
        <button type="button" onclick="scrollNews(-1)">‹</button>
        <button type="button" onclick="scrollNews(1)">›</button>
      </div>
    </div>

    <div id="newsScroller" class="news-scroller">
      ${topNews.map(item => `
        <a class="news-card-item" href="${item.url}" target="_blank" rel="noopener noreferrer">
          <span class="news-tag news-${item.category.toLowerCase()}">${item.category}</span>
          <strong>${item.title}</strong>
          <small>${item.source}${item.published ? " · " + item.published : ""}</small>
        </a>
      `).join("")}
    </div>
  `;
}

function scrollNews(direction) {
  const scroller = document.getElementById("newsScroller");
  if (!scroller) return;

  scroller.scrollBy({
    left: direction * 320,
    behavior: "smooth"
  });
}

/* =========================
   CHECKPOINT CAMERAS
   ========================= */

function renderCheckpoints() {
  const box = document.getElementById("checkpointResult");
  if (!box) return;

  const woodlands = checkpointData.woodlands || [];
  const tuas = checkpointData.tuas || [];
  const filter = box.dataset.checkpointFilter || "all";

  function cameraGroup(title, cameras) {
    return `
      <div class="checkpoint-group">
        <h3>${title}</h3>

        ${
          cameras.length
            ? `<div class="checkpoint-grid">
                ${cameras.slice(0, 4).map(cam => `
                  <div class="checkpoint-camera"
                       onclick="openImageModal('${cam.image}', '${title} - Camera ${cam.camera_id}')">
                    <img src="${cam.image}" alt="${title} traffic camera ${cam.camera_id}">
                    <span>Camera ${cam.camera_id}</span>
                  </div>
                `).join("")}
              </div>`
            : `<p class="checkpoint-empty">No camera images found.</p>`
        }
      </div>
    `;
  }

  box.innerHTML = `
    <div class="checkpoint-layout">
      ${filter !== "tuas" ? cameraGroup("Woodlands Checkpoint", woodlands) : ""}
      ${filter !== "woodlands" ? cameraGroup("Tuas Checkpoint", tuas) : ""}
    </div>

    <div class="note">
      Source: ${checkpointData.source_name}. Last fetched: ${formatTimestamp(checkpointData.last_updated)}.
    </div>
  `;
}

function openImageModal(imageUrl, caption) {
  const modal = document.getElementById("imageModal");
  const image = document.getElementById("modalImage");
  const text = document.getElementById("modalCaption");

  if (!modal || !image || !text) return;

  image.src = imageUrl;
  text.textContent = caption;
  modal.classList.add("show");
}

function closeImageModal() {
  const modal = document.getElementById("imageModal");
  if (!modal) return;

  modal.classList.remove("show");
}

window.addEventListener("click", function(event) {
  const modal = document.getElementById("imageModal");

  if (event.target === modal) {
    closeImageModal();
  }
});

/* =========================
   GAMBLING HIDE / SHOW
   ========================= */

function applyGamblingVisibility() {
  const box = document.getElementById("sgpoolsResult");
  const btn = document.getElementById("toggleGamblingBtn");

  if (!box || !btn) return;

  if (hideGambling) {
    box.innerHTML = `
      <div class="gambling-hidden-box">
        Singapore Pools results are hidden on this browser.
      </div>
    `;
    btn.textContent = "Show";
  } else {
    renderSgPoolsResults();
    btn.textContent = "Hide";
  }
}

function toggleGamblingSection() {
  hideGambling = !hideGambling;
  localStorage.setItem("hideGambling", hideGambling ? "true" : "false");
  applyGamblingVisibility();
}

/* =========================
   SINGAPORE POOLS
   ========================= */

function renderSgPoolsResults() {
  const box = document.getElementById("sgpoolsResult");
  if (!box) return;

  const fourD = sgpoolsResults.four_d;
  const toto = sgpoolsResults.toto;

  box.innerHTML = `
    <div class="sgpools-layout">

      <div class="pool-panel pool-panel-main">
        <div class="pool-panel-title">
          <h3>4D Result</h3>
          <span>${fourD.draw_date} · Draw ${fourD.draw_no}</span>
        </div>

        <div class="pool-summary-strip">
          <span>Top prize: <strong>${fourD.first_prize}</strong></span>
          <span>Starter: <strong>${fourD.starter.length}</strong></span>
          <span>Consolation: <strong>${fourD.consolation.length}</strong></span>
        </div>

        <div class="sgpools-prizes">
          <div class="sgpools-prize first">
            <span>1st Prize</span>
            <strong>${fourD.first_prize}</strong>
          </div>
          <div class="sgpools-prize">
            <span>2nd Prize</span>
            <strong>${fourD.second_prize}</strong>
          </div>
          <div class="sgpools-prize">
            <span>3rd Prize</span>
            <strong>${fourD.third_prize}</strong>
          </div>
        </div>

        <div class="pool-number-section">
          <div>
            <h4>Starter Prizes</h4>
            <div class="number-grid">
              ${fourD.starter.map(num => `<span>${num}</span>`).join("")}
            </div>
          </div>

          <div>
            <h4>Consolation Prizes</h4>
            <div class="number-grid">
              ${fourD.consolation.map(num => `<span>${num}</span>`).join("")}
            </div>
          </div>
        </div>
      </div>

      <div class="pool-side-grid">
        <div class="pool-panel">
          <div class="pool-panel-title">
            <h3>TOTO Result</h3>
            <span>${toto.draw_date} · Draw ${toto.draw_no}</span>
          </div>

          <div class="toto-numbers">
            ${toto.winning_numbers.map(num => `<span>${num}</span>`).join("")}
          </div>

          <div class="toto-additional compact">
            <span>Additional Number</span>
            <strong>${toto.additional_number}</strong>
          </div>
        </div>

        <div class="pool-panel lucky-box modern-lucky">
          <h3>🎲 Lucky Pick</h3>

          <div class="lucky-actions">
            <button onclick="generateFourD()">Generate 4D</button>
            <button onclick="generateToto()">Generate TOTO</button>
          </div>

          <div id="luckyResult" class="lucky-result">
            Click to generate lucky numbers.
          </div>

          <small>For entertainment only.</small>
        </div>
      </div>

    </div>

    <div class="note">
      Source: ${sgpoolsResults.source_name}. Last fetched: ${formatTimestamp(sgpoolsResults.last_updated)}.
    </div>
  `;
}

function generateFourD() {
  const resultBox = document.getElementById("luckyResult");
  if (!resultBox) return;

  let counter = 0;

  const interval = setInterval(() => {
    const random = Math.floor(Math.random() * 10000)
      .toString()
      .padStart(4, "0");

    resultBox.innerHTML = `
      <div class="four-d-lucky rolling">
        ${random}
      </div>
    `;

    counter++;

    if (counter >= 20) {
      clearInterval(interval);

      const finalNumber = Math.floor(Math.random() * 10000)
        .toString()
        .padStart(4, "0");

      resultBox.innerHTML = `
        <div class="four-d-lucky final">
          ${finalNumber}
        </div>
      `;
    }
  }, 70);
}

function generateToto() {
  const resultBox = document.getElementById("luckyResult");
  if (!resultBox) return;

  let counter = 0;

  const interval = setInterval(() => {
    const numbers = [];

    while (numbers.length < 6) {
      const num = Math.floor(Math.random() * 49) + 1;

      if (!numbers.includes(num)) {
        numbers.push(num);
      }
    }

    numbers.sort((a, b) => a - b);

    resultBox.innerHTML = `
      <div class="toto-lucky">
        ${numbers.map(num => `<span>${num}</span>`).join("")}
      </div>
    `;

    counter++;

    if (counter >= 20) {
      clearInterval(interval);

      const finalNumbers = [];

      while (finalNumbers.length < 6) {
        const num = Math.floor(Math.random() * 49) + 1;

        if (!finalNumbers.includes(num)) {
          finalNumbers.push(num);
        }
      }

      finalNumbers.sort((a, b) => a - b);

      const additional = Math.floor(Math.random() * 49) + 1;

      resultBox.innerHTML = `
        <div class="toto-lucky final">
          ${finalNumbers.map(num => `<span>${num}</span>`).join("")}
        </div>

        <div class="lucky-additional">
          Additional: <strong>${additional}</strong>
        </div>
      `;
    }
  }, 90);
}

/* =========================
   COE
   ========================= */

function renderCoePrices() {
  const box = document.getElementById("coeResult");
  if (!box) return;

  const categoryNames = {
    "Category A": "Cat A - Cars up to 1600cc / 130bhp",
    "Category B": "Cat B - Cars above 1600cc / 130bhp",
    "Category C": "Cat C - Goods Vehicle & Bus",
    "Category D": "Cat D - Motorcycle",
    "Category E": "Cat E - Open Category"
  };

  box.innerHTML = `
    <div class="row">
      <span>Latest Bidding</span>
      <strong>${coePrices.latest_month} - ${coePrices.latest_bidding_label}</strong>
    </div>

    ${coePrices.latest.map(item => {
      const change = item.change || 0;
      const isUp = change > 0;
      const isDown = change < 0;
      const arrow = isUp ? "▲" : isDown ? "▼" : "—";
      const trendClass = isUp ? "up" : isDown ? "down" : "";

      return `
        <div class="row">
          <span>${categoryNames[item.category]}</span>
          <strong>
            ${money(item.premium)}<br>
            <small class="${trendClass}">
              ${arrow} ${money(Math.abs(change))}
              ${item.change_percent !== undefined ? `(${Math.abs(item.change_percent)}%)` : ""}
            </small>
          </strong>
        </div>
      `;
    }).join("")}

    <div class="note">
      Source: ${coePrices.source_name}. Last fetched: ${formatTimestamp(coePrices.last_updated)}.
    </div>
  `;
}

/* =========================
   BTO
   ========================= */

function renderBtoProjects() {
  const box = document.getElementById("btoResult");
  if (!box) return;

  const grouped = {};

  btoProjects.projects.forEach(item => {
    if (!grouped[item.town]) {
      grouped[item.town] = {
        town: item.town,
        stage: item.stage,
        flatTypes: new Set(),
        projects: 0
      };
    }

    grouped[item.town].projects += 1;

    item.flat_types.split(",").forEach(type => {
      grouped[item.town].flatTypes.add(type.trim());
    });
  });

  const towns = Object.values(grouped);

  box.innerHTML = `
    <div class="row">
      <span>Latest HDB Portal Data</span>
      <strong>${btoProjects.projects.length} upcoming project entries</strong>
    </div>

    <div class="bto-grid">
      ${towns.map(item => `
        <div class="bto-tile">
          <div>
            <span class="bto-town">${item.town}</span>
            <p>${[...item.flatTypes].join(", ")}</p>
            <small>${item.projects} project${item.projects > 1 ? "s" : ""} available</small>
          </div>

          <div class="bto-status">
            <strong>${item.stage}</strong>
          </div>
        </div>
      `).join("")}
    </div>

    <div class="note">
      Source: ${btoProjects.source_name}. Last fetched: ${formatTimestamp(btoProjects.last_updated)}. ${btoProjects.note}
    </div>
  `;
}

/* =========================
   PETROL
   ========================= */

function renderPetrolPrices() {
  const box = document.getElementById("petrolResult");
  if (!box) return;

  function priceNumber(value) {
    if (!value || value === "N/A") return null;
    const match = value.match(/(\d+\.\d+)/);
    return match ? Number(match[1]) : null;
  }

  const fuelKeys = ["ron92", "ron95", "ron98", "premium", "diesel"];
  const cheapest = {};

  fuelKeys.forEach(key => {
    const prices = petrolPrices.brands
      .map(item => priceNumber(item[key]))
      .filter(value => value !== null);

    cheapest[key] = prices.length ? Math.min(...prices) : null;
  });

  function petrolCell(item, key) {
    const value = item[key];

    if (value === "N/A") {
      return `<span class="na">N/A</span>`;
    }

    const current = priceNumber(value);
    const isCheapest = current !== null && current === cheapest[key];
    const changeInfo = item.changes ? item.changes[key] : null;

    let movementHtml = "";

    if (changeInfo && changeInfo.change !== 0) {
      const change = Number(changeInfo.change);
      const percent = Number(changeInfo.percent);
      const isUp = change > 0;
      const arrow = isUp ? "▲" : "▼";
      const className = isUp ? "petrol-up" : "petrol-down";
      const sign = isUp ? "+" : "-";

      movementHtml = `
        <small class="petrol-movement ${className}">
          ${arrow} ${sign}$${Math.abs(change).toFixed(2)} (${sign}${Math.abs(percent).toFixed(2)}%)
        </small>
      `;
    } else if (changeInfo && changeInfo.change === 0) {
      movementHtml = `
        <small class="petrol-movement petrol-flat">
          — No change
        </small>
      `;
    }

    return `
      <span class="${isCheapest ? "cheapest" : ""}">
        ${value}
        ${movementHtml}
        ${isCheapest ? "<small>Cheapest</small>" : ""}
      </span>
    `;
  }

  box.innerHTML = `
    <div class="petrol-table">
      <div class="petrol-header">
        <span>Brand</span>
        <span>92</span>
        <span>95</span>
        <span>98</span>
        <span>Premium</span>
        <span>Diesel</span>
      </div>

      ${petrolPrices.brands.map(item => `
        <div class="petrol-row">
          <div class="brand-cell">
            <img src="${item.logo}" alt="${item.brand} logo" />
            <strong>${item.brand}</strong>
          </div>

          ${petrolCell(item, "ron92")}
          ${petrolCell(item, "ron95")}
          ${petrolCell(item, "ron98")}
          ${petrolCell(item, "premium")}
          ${petrolCell(item, "diesel")}
        </div>
      `).join("")}
    </div>

    ${renderPetrolDiscounts()}

    <div class="note">
      Source: ${petrolPrices.source_name}. Last fetched: ${formatTimestamp(petrolPrices.last_updated)}. Listed pump prices in SGD per litre. Discounts and card promotions are not included.
    </div>
  `;
}

function renderPetrolDiscounts() {
  if (!petrolDiscounts.discounts || !petrolPrices.brands) return "";

  const fuelKey = selectedDiscountFuel || "ron95";

  const fuelLabels = {
    ron92: "RON92",
    ron95: "RON95",
    ron98: "RON98",
    premium: "Premium",
    diesel: "Diesel"
  };

  function priceNumber(value) {
    if (!value || value === "N/A") return null;
    const match = value.match(/(\d+\.\d+)/);
    return match ? Number(match[1]) : null;
  }

  const effectivePrices = petrolDiscounts.discounts
    .map(discount => {
      const brandPrice = petrolPrices.brands.find(
        item => item.brand === discount.brand
      );

      if (!brandPrice) return null;

      const pumpPrice = priceNumber(brandPrice[fuelKey]);
      if (pumpPrice === null) return null;

      let effectivePrice;
      let discountLabel;

      if (discount.effective_prices && discount.effective_prices[fuelKey]) {
        effectivePrice = Number(discount.effective_prices[fuelKey]);
        discountLabel = "Published member price";
      } else {
        effectivePrice = pumpPrice * (1 - discount.discount_percent / 100);
        discountLabel = `${discount.discount_percent}% off`;
      }

      return {
        ...discount,
        logo: brandPrice.logo,
        pumpPrice,
        effectivePrice,
        discountLabel
      };
    })
    .filter(Boolean)
    .sort((a, b) => a.effectivePrice - b.effectivePrice);

  return `
    <div class="petrol-extra-grid">

      <div class="petrol-discount-panel">
        <h3>💳 Best Petrol Discounts</h3>

        <div class="petrol-discount-cards">
          ${petrolDiscounts.discounts.map(item => {
            const brandPrice = petrolPrices.brands.find(
              brand => brand.brand === item.brand
            );

            return `
              <a class="petrol-discount-card"
                 href="${item.promo_url}"
                 target="_blank"
                 rel="noopener noreferrer">
                <img src="${brandPrice?.logo || ""}" alt="${item.brand} logo">
                <strong>${item.brand}</strong>
                <span>${item.discount_percent ? item.discount_percent + "%" : "Member"}</span>
                <small>${item.card}</small>
              </a>
            `;
          }).join("")}
        </div>
      </div>

      <div class="petrol-effective-panel full-width">
        <div class="effective-title-row">
          <h3>🏆 Effective Price After Discount</h3>

          <select
            class="fuel-selector"
            onchange="selectedDiscountFuel = this.value; renderPetrolPrices();"
          >
            <option value="ron92" ${fuelKey === "ron92" ? "selected" : ""}>RON92</option>
            <option value="ron95" ${fuelKey === "ron95" ? "selected" : ""}>RON95</option>
            <option value="ron98" ${fuelKey === "ron98" ? "selected" : ""}>RON98</option>
            <option value="premium" ${fuelKey === "premium" ? "selected" : ""}>Premium</option>
            <option value="diesel" ${fuelKey === "diesel" ? "selected" : ""}>Diesel</option>
          </select>
        </div>

        <div class="effective-fuel-note">
          Showing estimated effective price for <strong>${fuelLabels[fuelKey]}</strong>.
        </div>

        <div class="effective-table">
          <div class="effective-header">
            <span>Brand</span>
            <span>Pump</span>
            <span>Discount Used</span>
            <span>After Discount</span>
          </div>

          ${
            effectivePrices.length
              ? effectivePrices.map(item => `
                <div class="effective-table-row">
                  <div class="effective-brand">
                    <img src="${item.logo}" alt="${item.brand} logo">
                    <strong>${item.brand}</strong>
                  </div>

                  <span>$${item.pumpPrice.toFixed(2)}</span>

                  <span>
                    ${item.card}
                    <small>${item.discountLabel}</small>
                  </span>

                  <strong class="effective-price">
                    $${item.effectivePrice.toFixed(2)}/L
                  </strong>
                </div>
              `).join("")
              : `
                <div class="effective-empty">
                  No available pump price for ${fuelLabels[fuelKey]}.
                </div>
              `
          }
        </div>

        <div class="petrol-discount-note">
          Estimated only. Final savings may depend on card terms, caps, cashback,
          membership, and minimum spend.
        </div>
      </div>

    </div>
  `;
}
/* =========================
   QUICK INFO
   ========================= */

function renderQuickInfo() {
  const box = document.getElementById("quickInfo");
  if (!box) return;

  box.innerHTML = `
    <div class="quick-grid two-items">
      ${quickInfo.items.map(item => `
        <div class="quick-tile">
          <div>
            <span class="quick-label">${item.label}</span>
            <strong>${item.value}</strong>
            <p>${item.detail}</p>
          </div>

          <a href="${item.url}" target="_blank" rel="noopener noreferrer">
            Verify
          </a>
        </div>
      `).join("")}
    </div>

    <div class="note">
      Source: ${quickInfo.source_name}. Last fetched: ${formatTimestamp(quickInfo.last_updated)}.
    </div>
  `;
}

loadData();
