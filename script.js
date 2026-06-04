let coePrices = {};
let btoProjects = {};
let petrolPrices = {};
let quickInfo = {};
let sgpoolsResults = {};
let newsResults = {};
let isRolling = false;

async function loadData() {
  try {
    coePrices = await fetch("./data/coe-prices.json").then(r => r.json());

    btoProjects = await fetch("./data/bto-projects.json").then(r => r.json());

    petrolPrices = await fetch("./data/petrol-prices.json").then(r => r.json());

    quickInfo = await fetch("./data/quick-info.json").then(r => r.json());

    newsResults = await fetch("./data/news.json").then(r => r.json());

    try {
      sgpoolsResults = await fetch("./data/sgpools-results.json")
        .then(r => r.json());

      renderSgPoolsResults();
    } catch (e) {
      console.error("4D results failed:", e);
    }

    renderNews();
    renderSourceLinks();
    renderCoePrices();
    renderBtoProjects();
    renderPetrolPrices();
    renderQuickInfo();
    makeHuatDraggable();

  } catch (err) {
    console.error("Dashboard load failed:", err);
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
  document.getElementById("coeSourceLink").href = coePrices.source_url;
  document.getElementById("btoSourceLink").href = btoProjects.source_url;
  document.getElementById("petrolSourceLink").href = petrolPrices.source_url;
  document.getElementById("quickSourceLink").href = quickInfo.source_url;
  document.getElementById("sgpoolsSourceLink").href = sgpoolsResults.source_url;
}

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
      <span>Last updated: ${newsResults.last_updated}</span>

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

function renderSgPoolsResults() {
  const box = document.getElementById("sgpoolsResult");

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

function renderCoePrices() {
  const box = document.getElementById("coeResult");

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

function renderBtoProjects() {
  const box = document.getElementById("btoResult");
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

function renderPetrolPrices() {
  const box = document.getElementById("petrolResult");

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

    return `
      <span class="${isCheapest ? "cheapest" : ""}">
        ${value}
        ${isCheapest ? "<br><small>Cheapest</small>" : ""}
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
        
    <div class="note">
      Source: ${petrolPrices.source_name}. Last fetched: ${formatTimestamp(petrolPrices.last_updated)}. Listed pump prices in SGD per litre. Discounts and card promotions are not included.
    </div>
  `;
}

function renderQuickInfo() {
  const box = document.getElementById("quickInfo");

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

function generateHuat() {
  if (isRolling) return;

  isRolling = true;

  const finalNumber = Math.floor(Math.random() * 10000)
    .toString()
    .padStart(4, "0");

  const display = document.getElementById("huatNumber");
  display.textContent = "----";

  const digits = ["-", "-", "-", "-"];
  let currentDigit = 0;

  function rollDigit() {
    let rollCount = 0;
    const targetDigit = finalNumber[currentDigit];

    const rolling = setInterval(() => {
      digits[currentDigit] = Math.floor(Math.random() * 10);
      display.textContent = digits.join("");
      rollCount++;

      if (rollCount >= 15) {
        clearInterval(rolling);
        digits[currentDigit] = targetDigit;
        display.textContent = digits.join("");

        currentDigit++;

        if (currentDigit < 4) {
          setTimeout(rollDigit, 250);
        } else {
          isRolling = false;
        }
      }
    }, 50);
  }

  rollDigit();
}

function hideHuat() {
  document.getElementById("huatBox").style.display = "none";
}

function makeHuatDraggable() {
  const box = document.getElementById("huatBox");
  const handle = document.getElementById("huatDragHandle");

  let dragging = false;
  let offsetX = 0;
  let offsetY = 0;

  handle.addEventListener("mousedown", startDrag);
  handle.addEventListener("touchstart", startDrag, { passive: false });

  document.addEventListener("mousemove", drag);
  document.addEventListener("touchmove", drag, { passive: false });

  document.addEventListener("mouseup", stopDrag);
  document.addEventListener("touchend", stopDrag);

  function getPoint(event) {
    if (event.touches && event.touches.length > 0) {
      return event.touches[0];
    }
    return event;
  }

  function startDrag(event) {
    event.preventDefault();
    const point = getPoint(event);
    const rect = box.getBoundingClientRect();

    dragging = true;
    offsetX = point.clientX - rect.left;
    offsetY = point.clientY - rect.top;

    box.style.right = "auto";
    box.style.bottom = "auto";
  }

  function drag(event) {
    if (!dragging) return;

    event.preventDefault();
    const point = getPoint(event);

    let left = point.clientX - offsetX;
    let top = point.clientY - offsetY;

    left = Math.max(0, Math.min(left, window.innerWidth - box.offsetWidth));
    top = Math.max(0, Math.min(top, window.innerHeight - box.offsetHeight));

    box.style.left = `${left}px`;
    box.style.top = `${top}px`;
  }

  function stopDrag() {
    dragging = false;
  }
}

loadData();