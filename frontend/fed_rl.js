(function () {
  const payload = (typeof FED_RL_PAYLOAD !== "undefined" && FED_RL_PAYLOAD) ? FED_RL_PAYLOAD : null;

  const actionPalette = {
    Allow: "#1f9d55",
    Block: "#c62828",
    Challenge: "#d4a017"
  };

  const state = {
    live: true,
    intervalId: null,
    trendFrameId: null,
    currentData: null,
    previousData: null,
    lastFeedTopTranId: null,
    trendMeta: null
  };

  function text(value) {
    return value === null || value === undefined || value === "" ? "-" : String(value);
  }

  function formatInt(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return "-";
    return num.toLocaleString("en-US", { maximumFractionDigits: 0 });
  }

  function formatFloat(value, digits) {
    const num = Number(value);
    if (!Number.isFinite(num)) return "-";
    return num.toLocaleString("en-US", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits
    });
  }

  function formatPct(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return "-";
    return `${formatFloat(num, 2)}%`;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function randomInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
  }

  function randomFloat(min, max) {
    return Math.random() * (max - min) + min;
  }

  function maybe(probability) {
    return Math.random() < probability;
  }

  function deepClone(obj) {
    return JSON.parse(JSON.stringify(obj || {}));
  }

  function nowLabel() {
    return new Date().toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false
    });
  }

  function randomTranId() {
    const letters = "ABCDEFGHJKLMNPQRSTUVWXYZ";
    let suffix = "";
    for (let i = 0; i < 4; i += 1) {
      suffix += letters.charAt(randomInt(0, letters.length - 1));
    }
    return `TX-${randomInt(100000, 999999)}-${suffix}`;
  }

  function setBanner(message) {
    const banner = document.getElementById("rlStateBanner");
    if (!banner) return;
    if (!message) {
      banner.classList.add("rl-hidden");
      banner.textContent = "";
      return;
    }
    banner.classList.remove("rl-hidden");
    banner.textContent = message;
  }

  function updateLastUpdated(timestampText) {
    const ts = document.getElementById("rlLastUpdated");
    if (!ts) return;
    ts.textContent = `Last updated: ${text(timestampText)}`;
  }

  function flashClass(el, className) {
    if (!el) return;
    el.classList.remove(className);
    void el.offsetWidth;
    el.classList.add(className);
    setTimeout(() => {
      el.classList.remove(className);
    }, 900);
  }

  function ensureKpiCards(root, cards) {
    if (!root) return [];
    let renderedCards = Array.from(root.querySelectorAll(".rl-kpi-card"));
    if (renderedCards.length !== cards.length) {
      root.innerHTML = cards.map((item) => `
        <article class="rl-kpi-card" data-kpi-key="${item.key}">
          <div class="rl-kpi-label">${item.label}</div>
          <div class="rl-kpi-value">-</div>
          <div class="rl-kpi-sub">${item.sub}</div>
        </article>
      `).join("");
      renderedCards = Array.from(root.querySelectorAll(".rl-kpi-card"));
    }
    return renderedCards;
  }

  function renderKpis(kpis, previousKpis) {
    const root = document.getElementById("rlKpiGrid");
    if (!root) return;

    const cards = [
      {
        key: "transactions_scanned",
        label: "Transactions Scanned",
        value: formatInt(kpis.transactions_scanned),
        raw: Number(kpis.transactions_scanned),
        sub: "Current lookback window"
      },
      {
        key: "high_risk_rate_pct",
        label: "High Risk Rate",
        value: formatPct(kpis.high_risk_rate_pct),
        raw: Number(kpis.high_risk_rate_pct),
        sub: `Threshold >= ${formatFloat(kpis.risk_threshold || 0.7, 2)}`
      },
      {
        key: "avg_model_score",
        label: "Average Score",
        value: formatFloat(kpis.avg_model_score, 3),
        raw: Number(kpis.avg_model_score),
        sub: "Model confidence average"
      },
      {
        key: "p95_latency_ms",
        label: "P95 Inference Latency",
        value: `${formatFloat(kpis.p95_latency_ms, 1)} ms`,
        raw: Number(kpis.p95_latency_ms),
        sub: "95th percentile"
      },
      {
        key: "false_positive_proxy_pct",
        label: "False Positive Proxy",
        value: formatPct(kpis.false_positive_proxy_pct),
        raw: Number(kpis.false_positive_proxy_pct),
        sub: "Challenge + Block ratio"
      },
      {
        key: "model_error_count",
        label: "Model Error Count",
        value: formatInt(kpis.model_error_count),
        raw: Number(kpis.model_error_count),
        sub: "Rows with model/runtime anomalies"
      }
    ];

    const renderedCards = ensureKpiCards(root, cards);

    renderedCards.forEach((cardEl, idx) => {
      const card = cards[idx];
      const valueEl = cardEl.querySelector(".rl-kpi-value");
      const subEl = cardEl.querySelector(".rl-kpi-sub");
      if (!valueEl || !subEl) return;

      valueEl.textContent = card.value;
      subEl.textContent = card.sub;

      if (previousKpis && Number.isFinite(card.raw)) {
        const prev = Number(previousKpis[card.key]);
        if (Number.isFinite(prev) && card.raw > prev) {
          flashClass(valueEl, "rl-kpi-up");
        }
      }
    });
  }

  function drawTrend(series, scannedValues, flaggedValues) {
    const canvas = document.getElementById("rlTrendCanvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    const dpr = window.devicePixelRatio || 1;
    const cssWidth = canvas.clientWidth || 900;
    const cssHeight = canvas.clientHeight || 260;
    canvas.width = Math.floor(cssWidth * dpr);
    canvas.height = Math.floor(cssHeight * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    ctx.clearRect(0, 0, cssWidth, cssHeight);

    if (!series || !Array.isArray(series.timestamps) || series.timestamps.length === 0) {
      ctx.fillStyle = "#666";
      ctx.font = "12px Segoe UI";
      ctx.fillText("No trend data available", 12, 24);
      return;
    }

    const padding = { top: 16, right: 14, bottom: 24, left: 42 };
    const w = cssWidth - padding.left - padding.right;
    const h = cssHeight - padding.top - padding.bottom;

    const scanned = scannedValues || series.scanned || [];
    const flagged = flaggedValues || series.flagged || [];
    const maxY = Math.max(1, ...scanned, ...flagged);

    state.trendMeta = {
      padding,
      w,
      h,
      cssWidth,
      cssHeight,
      points: scanned.length
    };

    ctx.strokeStyle = "#d5d5d5";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i += 1) {
      const y = padding.top + (h * i) / 4;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(padding.left + w, y);
      ctx.stroke();

      const label = Math.round(maxY - (maxY * i) / 4);
      ctx.fillStyle = "#7a7a7a";
      ctx.font = "10px Segoe UI";
      ctx.fillText(String(label), 8, y + 3);
    }

    function drawArea(values, lineColor, fillColor) {
      if (!values || values.length === 0) return;

      ctx.fillStyle = fillColor;
      ctx.beginPath();
      values.forEach((value, idx) => {
        const x = padding.left + (w * idx) / Math.max(1, values.length - 1);
        const y = padding.top + h - (h * value) / maxY;
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.lineTo(padding.left + w, padding.top + h);
      ctx.lineTo(padding.left, padding.top + h);
      ctx.closePath();
      ctx.fill();

      ctx.strokeStyle = lineColor;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      values.forEach((value, idx) => {
        const x = padding.left + (w * idx) / Math.max(1, values.length - 1);
        const y = padding.top + h - (h * value) / maxY;
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    function drawLine(values, color) {
      if (!values || values.length === 0) return;
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      values.forEach((value, idx) => {
        const x = padding.left + (w * idx) / Math.max(1, values.length - 1);
        const y = padding.top + h - (h * value) / maxY;
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    drawArea(scanned, "#6b7280", "rgba(31, 157, 85, 0.18)");
    drawLine(flagged, "#c62828");

    const lastIndex = series.timestamps.length - 1;
    const firstLabel = text(series.timestamps[0]);
    const lastLabel = text(series.timestamps[lastIndex]);

    ctx.fillStyle = "#767676";
    ctx.font = "10px Segoe UI";
    ctx.fillText(firstLabel, padding.left, cssHeight - 7);
    const lastWidth = ctx.measureText(lastLabel).width;
    ctx.fillText(lastLabel, padding.left + w - lastWidth, cssHeight - 7);

    ctx.fillStyle = "rgba(31, 157, 85, 0.18)";
    ctx.fillRect(cssWidth - 240, 10, 16, 8);
    ctx.strokeStyle = "#6b7280";
    ctx.lineWidth = 1;
    ctx.strokeRect(cssWidth - 240, 10, 16, 8);

    ctx.strokeStyle = "#c62828";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cssWidth - 140, 14);
    ctx.lineTo(cssWidth - 124, 14);
    ctx.stroke();
    ctx.fillStyle = "#646464";
    ctx.font = "11px Segoe UI";
    ctx.fillText("Scanned (Area)", cssWidth - 218, 18);
    ctx.fillText("Flagged (Line)", cssWidth - 118, 18);
  }

  function ensureTrendTooltip() {
    let tooltip = document.getElementById("rlTrendTooltip");
    if (tooltip) return tooltip;

    tooltip = document.createElement("div");
    tooltip.id = "rlTrendTooltip";
    tooltip.className = "rl-trend-tooltip rl-hidden";
    document.body.appendChild(tooltip);
    return tooltip;
  }

  function hideTrendTooltip() {
    const tooltip = document.getElementById("rlTrendTooltip");
    if (!tooltip) return;
    tooltip.classList.add("rl-hidden");
  }

  function showTrendTooltip(event) {
    const canvas = document.getElementById("rlTrendCanvas");
    if (!canvas || !state.currentData || !state.currentData.trend || !state.trendMeta) return;

    const trend = state.currentData.trend;
    const timestamps = Array.isArray(trend.timestamps) ? trend.timestamps : [];
    const scanned = Array.isArray(trend.scanned) ? trend.scanned : [];
    const flagged = Array.isArray(trend.flagged) ? trend.flagged : [];
    if (timestamps.length === 0 || scanned.length === 0 || flagged.length === 0) {
      hideTrendTooltip();
      return;
    }

    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const { padding, w, h } = state.trendMeta;

    if (x < padding.left || x > padding.left + w || y < padding.top || y > padding.top + h) {
      hideTrendTooltip();
      return;
    }

    const ratio = (x - padding.left) / Math.max(1, w);
    const idx = clamp(Math.round(ratio * (timestamps.length - 1)), 0, timestamps.length - 1);
    const tooltip = ensureTrendTooltip();

    tooltip.innerHTML = `
      <div class="rl-tooltip-time">${text(timestamps[idx])}</div>
      <div class="rl-tooltip-row"><span class="rl-tooltip-dot rl-tooltip-dot-scanned"></span>Scanned: ${formatInt(scanned[idx])}</div>
      <div class="rl-tooltip-row"><span class="rl-tooltip-dot rl-tooltip-dot-flagged"></span>Flagged: ${formatInt(flagged[idx])}</div>
    `;
    tooltip.classList.remove("rl-hidden");
    tooltip.style.left = `${event.clientX + 12}px`;
    tooltip.style.top = `${event.clientY - 18}px`;
  }

  function animatedShiftValues(prevArr, nextArr, progress) {
    const prev = Array.isArray(prevArr) ? prevArr : [];
    const next = Array.isArray(nextArr) ? nextArr : [];
    if (prev.length === 0 || next.length === 0 || prev.length !== next.length) return next;

    const shifted = prev.slice(1).concat(next[next.length - 1]);
    return prev.map((value, idx) => value + (shifted[idx] - value) * progress);
  }

  function renderTrendAnimated(previousTrend, nextTrend) {
    if (!previousTrend || !Array.isArray(previousTrend.scanned) || !Array.isArray(previousTrend.flagged)) {
      drawTrend(nextTrend, nextTrend.scanned, nextTrend.flagged);
      return;
    }

    if (state.trendFrameId) {
      cancelAnimationFrame(state.trendFrameId);
      state.trendFrameId = null;
    }

    const durationMs = 500;
    const start = performance.now();

    function tick(ts) {
      const elapsed = ts - start;
      const t = clamp(elapsed / durationMs, 0, 1);
      const eased = 1 - Math.pow(1 - t, 3);

      const scanFrame = animatedShiftValues(previousTrend.scanned, nextTrend.scanned, eased);
      const flaggedFrame = animatedShiftValues(previousTrend.flagged, nextTrend.flagged, eased);
      drawTrend(nextTrend, scanFrame, flaggedFrame);

      if (t < 1) {
        state.trendFrameId = requestAnimationFrame(tick);
      } else {
        state.trendFrameId = null;
      }
    }

    state.trendFrameId = requestAnimationFrame(tick);
  }

  function ensureHistogram(root, items) {
    if (!root) return [];
    let wraps = Array.from(root.querySelectorAll(".rl-bar-wrap"));
    if (wraps.length !== items.length) {
      root.innerHTML = items.map((item) => `
        <div class="rl-bar-wrap" title="${text(item.bucket_label)}">
          <div class="rl-bar-value">0</div>
          <div class="rl-bar"></div>
          <div class="rl-bar-label">${text(item.bucket_label)}</div>
        </div>
      `).join("");
      wraps = Array.from(root.querySelectorAll(".rl-bar-wrap"));
    }
    return wraps;
  }

  function renderHistogram(items, previousItems) {
    const root = document.getElementById("rlHistogram");
    if (!root) return;

    if (!Array.isArray(items) || items.length === 0) {
      root.innerHTML = "<p>No histogram data available</p>";
      return;
    }

    const wraps = ensureHistogram(root, items);
    const maxCount = Math.max(1, ...items.map((item) => Number(item.count) || 0));
    const amberThreshold = maxCount * 0.68;
    const redThreshold = maxCount * 0.84;

    wraps.forEach((wrap, idx) => {
      const item = items[idx] || {};
      const previous = (previousItems && previousItems[idx]) ? Number(previousItems[idx].count) || 0 : 0;
      const count = Number(item.count) || 0;
      const heightPct = Math.max(4, (count / maxCount) * 100);

      const valueEl = wrap.querySelector(".rl-bar-value");
      const barEl = wrap.querySelector(".rl-bar");
      const labelEl = wrap.querySelector(".rl-bar-label");
      if (!valueEl || !barEl || !labelEl) return;

      valueEl.textContent = formatInt(count);
      labelEl.textContent = text(item.bucket_label);
      wrap.title = `${text(item.bucket_label)}: ${formatInt(count)}`;
      barEl.style.height = `${heightPct}%`;

      const bucketMid = (() => {
        const label = text(item.bucket_label);
        const parts = label.split("-");
        if (parts.length !== 2) return 0;
        const left = Number(parts[0]);
        const right = Number(parts[1]);
        if (!Number.isFinite(left) || !Number.isFinite(right)) return 0;
        return (left + right) / 2;
      })();

      barEl.classList.remove("rl-bar-low", "rl-bar-mid", "rl-bar-high");
      if (bucketMid >= 0.7) barEl.classList.add("rl-bar-high");
      else if (bucketMid >= 0.4) barEl.classList.add("rl-bar-mid");
      else barEl.classList.add("rl-bar-low");

      const hitAmber = previous < amberThreshold && count >= amberThreshold && count < redThreshold;
      const hitRed = previous < redThreshold && count >= redThreshold;
      if (hitRed) flashClass(barEl, "rl-spike-red");
      else if (hitAmber) flashClass(barEl, "rl-spike-amber");
    });
  }

  function ensureDecisionRows(root, items) {
    if (!root) return [];
    let rows = Array.from(root.querySelectorAll(".rl-mix-row"));
    if (rows.length !== items.length) {
      root.innerHTML = items.map((item) => `
        <div class="rl-mix-row" data-action="${text(item.action)}">
          <div class="rl-mix-label">${text(item.action)}</div>
          <div class="rl-mix-track">
            <div class="rl-mix-fill"></div>
          </div>
          <div class="rl-mix-value">-</div>
        </div>
      `).join("");
      rows = Array.from(root.querySelectorAll(".rl-mix-row"));
    }
    return rows;
  }

  function renderDecisionMix(items) {
    const root = document.getElementById("rlDecisionMix");
    if (!root) return;

    if (!Array.isArray(items) || items.length === 0) {
      root.innerHTML = "<p>No decision data available</p>";
      return;
    }

    const rows = ensureDecisionRows(root, items);
    const total = items.reduce((acc, item) => acc + (Number(item.count) || 0), 0);

    rows.forEach((row, idx) => {
      const item = items[idx] || {};
      const count = Number(item.count) || 0;
      const pct = total > 0 ? (count / total) * 100 : 0;
      const action = text(item.action);
      const fill = row.querySelector(".rl-mix-fill");
      const valueEl = row.querySelector(".rl-mix-value");
      const labelEl = row.querySelector(".rl-mix-label");
      if (!fill || !valueEl || !labelEl) return;

      const baseColor = actionPalette[action] || "#505050";
      fill.style.width = `${pct}%`;
      fill.style.background = baseColor;
      fill.classList.remove("rl-mix-warn", "rl-mix-danger");

      if (action === "Block" || action === "Challenge") {
        if (pct >= 30) fill.classList.add("rl-mix-danger");
        else if (pct >= 22) fill.classList.add("rl-mix-warn");
      }

      labelEl.textContent = action;
      valueEl.textContent = `${formatInt(count)} (${formatPct(pct)})`;
    });
  }

  function renderTable(tableId, columns, rows, formatters) {
    const table = document.getElementById(tableId);
    if (!table) return;

    if (!Array.isArray(rows) || rows.length === 0) {
      table.innerHTML = "<thead><tr><th>No data</th></tr></thead><tbody></tbody>";
      return;
    }

    const thead = `<thead><tr>${columns.map((col) => `<th>${col.label}</th>`).join("")}</tr></thead>`;
    const tbodyRows = rows.map((row) => {
      const tds = columns.map((col) => {
        const raw = row[col.key];
        const formatter = formatters && formatters[col.key];
        const rendered = formatter ? formatter(raw, row) : text(raw);
        return `<td>${rendered}</td>`;
      }).join("");
      return `<tr>${tds}</tr>`;
    }).join("");

    table.innerHTML = `${thead}<tbody>${tbodyRows}</tbody>`;
  }

  function actionClass(action) {
    if (action === "Allow") return "rl-action-allow";
    if (action === "Challenge") return "rl-action-challenge";
    if (action === "Block") return "rl-action-block";
    return "";
  }

  function riskClass(pct) {
    const value = Number(pct) || 0;
    if (value >= 24) return "rl-risk-high";
    if (value >= 14) return "rl-risk-medium";
    return "rl-risk-low";
  }

  function renderChannelMatrix(rows, previousRows) {
    const table = document.getElementById("rlChannelMatrix");
    if (!table) return;

    if (!Array.isArray(rows) || rows.length === 0) {
      table.innerHTML = "<thead><tr><th>No data</th></tr></thead><tbody></tbody>";
      return;
    }

    const prevMap = new Map(
      (Array.isArray(previousRows) ? previousRows : []).map((r) => [text(r.channel), r])
    );

    const thead = "<thead><tr><th>Channel</th><th>Allow</th><th>Block</th><th>Challenge</th><th>Total</th></tr></thead>";
    const tbody = rows.map((row) => {
      const channel = text(row.channel);
      const prev = prevMap.get(channel) || {};
      const allow = Number(row.Allow) || 0;
      const block = Number(row.Block) || 0;
      const challenge = Number(row.Challenge) || 0;
      const total = Number(row.total) || 0;

      const changedAllow = allow > (Number(prev.Allow) || 0);
      const changedBlock = block > (Number(prev.Block) || 0);
      const changedChallenge = challenge > (Number(prev.Challenge) || 0);
      const changedTotal = total > (Number(prev.total) || 0);

      return `
        <tr>
          <td>${channel}</td>
          <td class="rl-num-col"><span class="rl-channel-val rl-channel-allow ${changedAllow ? "rl-cell-bump" : ""}">${formatInt(allow)}</span></td>
          <td class="rl-num-col"><span class="rl-channel-val rl-channel-block ${changedBlock ? "rl-cell-bump" : ""}">${formatInt(block)}</span></td>
          <td class="rl-num-col"><span class="rl-channel-val rl-channel-challenge ${changedChallenge ? "rl-cell-bump" : ""}">${formatInt(challenge)}</span></td>
          <td class="rl-num-col"><span class="rl-channel-val rl-channel-total ${changedTotal ? "rl-cell-bump" : ""}">${formatInt(total)}</span></td>
        </tr>
      `;
    }).join("");

    table.innerHTML = `${thead}<tbody>${tbody}</tbody>`;
  }

  function renderTopMerchants(rows, previousRows) {
    const table = document.getElementById("rlTopMerchants");
    if (!table) return;

    if (!Array.isArray(rows) || rows.length === 0) {
      table.innerHTML = "<thead><tr><th>No data</th></tr></thead><tbody></tbody>";
      return;
    }

    const prevMap = new Map(
      (Array.isArray(previousRows) ? previousRows : []).map((r) => [text(r.merchant), r])
    );

    const thead = "<thead><tr><th>Merchant</th><th>Flagged</th><th>Avg Score</th><th>High Risk %</th></tr></thead>";
    const tbody = rows.map((row) => {
      const merchant = text(row.merchant);
      const prev = prevMap.get(merchant) || {};
      const flagged = Number(row.flagged_count) || 0;
      const avgScore = Number(row.avg_score) || 0;
      const riskPct = Number(row.high_risk_rate_pct) || 0;

      const changedFlagged = flagged > (Number(prev.flagged_count) || 0);
      const changedRisk = riskPct > (Number(prev.high_risk_rate_pct) || 0);

      return `
        <tr>
          <td>${merchant}</td>
          <td><span class="rl-cell-pill rl-total-pill ${changedFlagged ? "rl-cell-bump" : ""}">${formatInt(flagged)}</span></td>
          <td>${formatFloat(avgScore, 3)}</td>
          <td><span class="rl-risk-tag ${riskClass(riskPct)} ${changedRisk ? "rl-cell-bump" : ""}">${formatPct(riskPct)}</span></td>
        </tr>
      `;
    }).join("");

    table.innerHTML = `${thead}<tbody>${tbody}</tbody>`;
  }

  function renderRecentFlagged(rows, riskThreshold, highlightTranId) {
    const table = document.getElementById("rlRecentFlagged");
    if (!table) return;

    if (!Array.isArray(rows) || rows.length === 0) {
      table.innerHTML = "<thead><tr><th>No data</th></tr></thead><tbody></tbody>";
      return;
    }

    const columns = [
      { key: "event_time", label: "Event Time" },
      { key: "tranID", label: "Tran ID" },
      { key: "merchant", label: "Merchant" },
      { key: "channel", label: "Channel" },
      { key: "action", label: "Action" },
      { key: "score", label: "Score" },
      { key: "latency_ms", label: "Latency (ms)" }
    ];

    const thead = `<thead><tr>${columns.map((col) => `<th>${col.label}</th>`).join("")}</tr></thead>`;
    const tbodyRows = rows.map((row) => {
      const score = Number(row.score);
      const scoreClass = Number.isFinite(score) && score >= riskThreshold ? "rl-risk-cell-high" : "rl-risk-cell-medium";
      const isNew = highlightTranId && row.tranID === highlightTranId;

      return `
        <tr class="${isNew ? "rl-feed-row-new" : ""}">
          <td>${text(row.event_time)}</td>
          <td>${text(row.tranID)}</td>
          <td>${text(row.merchant)}</td>
          <td>${text(row.channel)}</td>
          <td><span class="rl-cell-pill ${actionClass(text(row.action))}">${text(row.action)}</span></td>
          <td><span class="${scoreClass}">${formatFloat(score, 3)}</span></td>
          <td>${formatFloat(row.latency_ms, 1)}</td>
        </tr>
      `;
    }).join("");

    table.innerHTML = `${thead}<tbody>${tbodyRows}</tbody>`;
  }

  function normalizePayload(inputPayload) {
    const data = deepClone(inputPayload || {});

    data.kpis = data.kpis || {};
    data.trend = data.trend || {};
    data.trend.timestamps = Array.isArray(data.trend.timestamps) ? data.trend.timestamps : [];
    data.trend.scanned = Array.isArray(data.trend.scanned) ? data.trend.scanned : [];
    data.trend.flagged = Array.isArray(data.trend.flagged) ? data.trend.flagged : [];

    data.score_distribution = Array.isArray(data.score_distribution) ? data.score_distribution : [];
    data.decision_mix = Array.isArray(data.decision_mix) ? data.decision_mix : [];
    data.channel_matrix = Array.isArray(data.channel_matrix) ? data.channel_matrix : [];
    data.top_risky_merchants = Array.isArray(data.top_risky_merchants) ? data.top_risky_merchants : [];
    data.recent_flagged_transactions = Array.isArray(data.recent_flagged_transactions)
      ? data.recent_flagged_transactions
      : [];

    return data;
  }

  function simulateNextData(previousData) {
    const next = deepClone(previousData);
    const kpis = next.kpis || {};

    const scanJump = randomInt(3, 14);
    kpis.transactions_scanned = Math.max(0, (Number(kpis.transactions_scanned) || 0) + scanJump);
    kpis.high_risk_rate_pct = clamp((Number(kpis.high_risk_rate_pct) || 12) + randomFloat(-0.75, 0.95), 4.5, 34);
    kpis.avg_model_score = clamp((Number(kpis.avg_model_score) || 0.39) + randomFloat(-0.02, 0.028), 0.12, 0.95);
    kpis.p95_latency_ms = clamp((Number(kpis.p95_latency_ms) || 124) + randomFloat(-11, 15), 64, 260);
    kpis.false_positive_proxy_pct = clamp((Number(kpis.false_positive_proxy_pct) || 14.5) + randomFloat(-1.2, 1.3), 2.2, 38);
    kpis.model_error_count = Math.max(0, (Number(kpis.model_error_count) || 0) + randomInt(-1, 2));

    const trend = next.trend || {};
    const timestamps = Array.isArray(trend.timestamps) ? trend.timestamps.slice() : [];
    const scanned = Array.isArray(trend.scanned) ? trend.scanned.slice() : [];
    const flagged = Array.isArray(trend.flagged) ? trend.flagged.slice() : [];

    if (timestamps.length > 1) timestamps.shift();
    timestamps.push(nowLabel());

    if (scanned.length > 1) scanned.shift();
    if (flagged.length > 1) flagged.shift();

    const lastScanned = scanned.length > 0 ? Number(scanned[scanned.length - 1]) || 20 : 20;
    const nextScanned = Math.max(6, Math.round(lastScanned + randomFloat(-2.4, 2.8)));
    const riskRate = clamp((Number(kpis.high_risk_rate_pct) || 10) / 100, 0.05, 0.45);
    const nextFlagged = Math.max(1, Math.round(nextScanned * riskRate + randomFloat(-2.2, 2.5)));

    scanned.push(nextScanned);
    flagged.push(nextFlagged);

    trend.timestamps = timestamps;
    trend.scanned = scanned;
    trend.flagged = flagged;

    const scoreDistribution = (next.score_distribution || []).map((item) => {
      const current = Number(item.count) || 0;
      const spike = maybe(0.12) ? randomInt(4, 10) : 0;
      const updated = Math.max(0, current + randomInt(-3, 5) + spike);
      return {
        bucket_label: text(item.bucket_label),
        count: updated
      };
    });
    next.score_distribution = scoreDistribution;

    const decisionMix = (next.decision_mix || []).map((item) => {
      const action = text(item.action);
      const current = Number(item.count) || 0;
      let drift = randomInt(-2, 3);
      if (action === "Block" && maybe(0.2)) drift += randomInt(2, 5);
      if (action === "Challenge" && maybe(0.18)) drift += randomInt(1, 4);
      return {
        action,
        count: Math.max(0, current + drift)
      };
    });
    next.decision_mix = decisionMix;

    const channelMatrix = (next.channel_matrix || []).map((row) => {
      const allow = Math.max(0, (Number(row.Allow) || 0) + randomInt(-2, 4));
      const block = Math.max(0, (Number(row.Block) || 0) + randomInt(-1, 2));
      const challenge = Math.max(0, (Number(row.Challenge) || 0) + randomInt(-1, 2));
      return {
        channel: text(row.channel),
        Allow: allow,
        Block: block,
        Challenge: challenge,
        total: allow + block + challenge
      };
    });
    next.channel_matrix = channelMatrix;

    const merchants = (next.top_risky_merchants || []).map((row) => {
      const flaggedCount = Math.max(0, (Number(row.flagged_count) || 0) + randomInt(-1, 4));
      const avgScore = clamp((Number(row.avg_score) || 0.3) + randomFloat(-0.02, 0.03), 0.05, 0.98);
      const riskPct = clamp((Number(row.high_risk_rate_pct) || 10) + randomFloat(-1.1, 1.6), 1, 92);
      return {
        merchant: text(row.merchant),
        flagged_count: flaggedCount,
        avg_score: avgScore,
        high_risk_rate_pct: riskPct
      };
    }).sort((a, b) => (Number(b.flagged_count) || 0) - (Number(a.flagged_count) || 0));
    next.top_risky_merchants = merchants;

    const feed = Array.isArray(next.recent_flagged_transactions)
      ? next.recent_flagged_transactions.slice()
      : [];

    const channels = ["CNP", "CP", "FPX", "OBW"];
    const actions = ["Allow", "Block", "Challenge"];
    const action = actions[randomInt(0, actions.length - 1)];
    const scoreBase = action === "Allow" ? randomFloat(0.22, 0.62) : randomFloat(0.62, 0.99);
    const riskThreshold = Number(kpis.risk_threshold) || 0.7;
    const score = action === "Allow" ? Math.min(scoreBase, riskThreshold - 0.01) : scoreBase;

    const newEvent = {
      event_time: nowLabel(),
      tranID: randomTranId(),
      merchant: merchants.length > 0 ? merchants[randomInt(0, merchants.length - 1)].merchant : `MRC_${randomInt(1000, 9999)}`,
      channel: channels[randomInt(0, channels.length - 1)],
      action,
      score,
      latency_ms: clamp((Number(kpis.p95_latency_ms) || 124) + randomFloat(-45, 50), 20, 420)
    };

    feed.unshift(newEvent);
    next.recent_flagged_transactions = feed.slice(0, 24);
    next.refreshed_at_local = new Date().toLocaleString("en-US", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false
    });

    return next;
  }

  function renderAll(currentData, previousData) {
    const kpis = currentData.kpis || {};

    renderKpis(kpis, previousData ? previousData.kpis : null);
    renderTrendAnimated(previousData ? previousData.trend : null, currentData.trend || {});
    renderHistogram(currentData.score_distribution || [], previousData ? previousData.score_distribution : null);
    renderDecisionMix(currentData.decision_mix || []);

    renderChannelMatrix(currentData.channel_matrix || [], previousData ? previousData.channel_matrix : null);

    renderTopMerchants(currentData.top_risky_merchants || [], previousData ? previousData.top_risky_merchants : null);

    const latestTranId = (currentData.recent_flagged_transactions && currentData.recent_flagged_transactions[0])
      ? currentData.recent_flagged_transactions[0].tranID
      : null;
    const shouldHighlight = latestTranId && latestTranId !== state.lastFeedTopTranId;
    state.lastFeedTopTranId = latestTranId;

    renderRecentFlagged(
      currentData.recent_flagged_transactions || [],
      Number(kpis.risk_threshold) || 0.7,
      shouldHighlight ? latestTranId : null
    );

    updateLastUpdated(currentData.refreshed_at_local);
  }

  function stopLiveLoop() {
    if (state.intervalId) {
      clearInterval(state.intervalId);
      state.intervalId = null;
    }
  }

  function runTick() {
    if (!state.currentData) return;
    const previous = deepClone(state.currentData);
    const next = simulateNextData(previous);
    state.previousData = previous;
    state.currentData = next;
    renderAll(next, previous);
  }

  function startLiveLoop() {
    stopLiveLoop();
    state.intervalId = setInterval(runTick, 1700);
  }

  function setLiveMode(isLive) {
    state.live = Boolean(isLive);

    const shell = document.querySelector(".rl-shell");
    const toggleBtn = document.getElementById("rlModeToggle");
    const liveLabel = document.getElementById("rlLiveLabel");

    if (shell) shell.classList.toggle("rl-static", !state.live);
    if (toggleBtn) toggleBtn.textContent = state.live ? "Pause Live" : "Resume Live";
    if (liveLabel) liveLabel.textContent = state.live ? "Live" : "Static";

    if (state.live) {
      startLiveLoop();
    } else {
      stopLiveLoop();
    }
  }

  function bindEvents() {
    const toggleBtn = document.getElementById("rlModeToggle");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        setLiveMode(!state.live);
      });
    }

    window.addEventListener("resize", () => {
      if (!state.currentData) return;
      drawTrend(state.currentData.trend || {}, state.currentData.trend.scanned, state.currentData.trend.flagged);
    });

    const canvas = document.getElementById("rlTrendCanvas");
    if (canvas) {
      canvas.addEventListener("mousemove", showTrendTooltip);
      canvas.addEventListener("mouseleave", hideTrendTooltip);
    }
  }

  function initialize() {
    if (!payload) {
      setBanner("Dashboard payload is unavailable.");
      return;
    }

    if (payload.status !== "ok") {
      const err = text(payload.error_message || "Data fetch failed");
      setBanner(`Data warning: ${err}. Rendering fallback view.`);
    } else if (payload.state_note) {
      setBanner(payload.state_note);
    }

    state.currentData = normalizePayload(payload);
    renderAll(state.currentData, null);
    bindEvents();
    setLiveMode(true);
  }

  initialize();
})();
