(function () {
  const payload = (typeof FED_RL_PAYLOAD !== "undefined" && FED_RL_PAYLOAD) ? FED_RL_PAYLOAD : null;
  const prevPayload = (typeof FED_RL_PREV_PAYLOAD !== "undefined" && FED_RL_PREV_PAYLOAD) ? FED_RL_PREV_PAYLOAD : null;

  const actionPalette = {
    "Allow": "#10b981",    // Neon green
    "Block": "#f43f5e",    // Neon red
    "Challenge": "#f59e0b" // Neon amber
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

  function diffClass(newVal, oldVal) {
    if (oldVal === undefined || oldVal === null) return "";
    const n = Number(newVal);
    const o = Number(oldVal);
    if (!Number.isNaN(n) && !Number.isNaN(o)) {
      if (n > o) return " rl-pulse-up";
      if (n < o) return " rl-pulse-down";
    }
    return "";
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

  function renderKpis(kpis, prev) {
    const root = document.getElementById("rlKpiGrid");
    if (!root) return;
    prev = prev || {};

    const cards = [
      { key: "transactions_scanned", label: "Transactions Scanned", value: formatInt(kpis.transactions_scanned), raw: kpis.transactions_scanned, sub: "Current lookback window" },
      { key: "high_risk_rate_pct", label: "High Risk Rate", value: formatPct(kpis.high_risk_rate_pct), raw: kpis.high_risk_rate_pct, sub: `Threshold >= ${formatFloat(kpis.risk_threshold || 0.7, 2)}` },
      { key: "avg_model_score", label: "Average Score", value: formatFloat(kpis.avg_model_score, 3), raw: kpis.avg_model_score, sub: "Model confidence average" },
      { key: "p95_latency_ms", label: "P95 Inference Latency", value: `${formatFloat(kpis.p95_latency_ms, 1)} ms`, raw: kpis.p95_latency_ms, sub: "95th percentile" },
      { key: "false_positive_proxy_pct", label: "False Positive Proxy", value: formatPct(kpis.false_positive_proxy_pct), raw: kpis.false_positive_proxy_pct, sub: "Challenge + Block ratio" },
      { key: "model_error_count", label: "Model Error Count", value: formatInt(kpis.model_error_count), raw: kpis.model_error_count, sub: "Rows with model/runtime anomalies" }
    ];

    root.innerHTML = cards.map((item) => {
      const pClass = diffClass(item.raw, prev[item.key]);
      return `
      <article class="rl-kpi-card">
        <div class="rl-kpi-label">${item.label}</div>
        <div class="rl-kpi-value${pClass}">${item.value}</div>
        <div class="rl-kpi-sub">${item.sub}</div>
      </article>
    `}).join("");
  }

  function renderTrend(series) {
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
      ctx.fillStyle = "#a1a1aa";
      ctx.font = "12px 'Space Grotesk', sans-serif";
      ctx.fillText("No trend data available", 16, 28);
      return;
    }

    const padding = { top: 20, right: 14, bottom: 28, left: 48 };
    const w = cssWidth - padding.left - padding.right;
    const h = cssHeight - padding.top - padding.bottom;

    const scanned = series.scanned || [];
    const flagged = series.flagged || [];
    const maxY = Math.max(1, ...scanned, ...flagged);

    ctx.strokeStyle = "rgba(255,255,255,0.06)";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i += 1) {
      const y = padding.top + (h * i) / 4;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(padding.left + w, y);
      ctx.stroke();

      const label = Math.round(maxY - (maxY * i) / 4);
      ctx.fillStyle = "#71717a";
      ctx.font = "11px 'Space Grotesk', sans-serif";
      ctx.fillText(String(label), 8, y + 4);
    }

    function drawLine(values, color) {
      if (!values || values.length === 0) return;
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      if (values.length === 1) {
        const x = padding.left + w / 2;
        const y = padding.top + h - (h * values[0]) / maxY;
        ctx.arc(x, y, 4, 0, 2 * Math.PI);
        ctx.fill();
      } else {
        values.forEach((value, idx) => {
          const x = padding.left + (w * idx) / Math.max(1, values.length - 1);
          const y = padding.top + h - (h * value) / maxY;
          if (idx === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.stroke();
      }
    }

    drawLine(scanned, "#3b82f6");
    drawLine(flagged, "#f43f5e");

    const timestamps = series.timestamps;
    const lastIndex = timestamps.length - 1;

    ctx.fillStyle = "#a1a1aa";
    ctx.font = "11px 'Space Grotesk', sans-serif";

    if (timestamps.length === 1) {
      const label = text(timestamps[0]);
      ctx.fillText(label, padding.left + w / 2 - ctx.measureText(label).width / 2, cssHeight - 8);
    } else {
      const firstLabel = text(timestamps[0]);
      const lastLabel = text(timestamps[lastIndex]);
      ctx.fillText(firstLabel, padding.left, cssHeight - 8);
      const lastWidth = ctx.measureText(lastLabel).width;
      ctx.fillText(lastLabel, padding.left + w - lastWidth, cssHeight - 8);
    }

    ctx.fillStyle = "#3b82f6";
    ctx.fillRect(cssWidth - 166, 12, 10, 10);
    ctx.fillStyle = "#f43f5e";
    ctx.fillRect(cssWidth - 88, 12, 10, 10);
    ctx.fillStyle = "#e4e4e7";
    ctx.font = "12px 'Space Grotesk', sans-serif";
    ctx.fillText("Scanned", cssWidth - 150, 21);
    ctx.fillText("Flagged", cssWidth - 72, 21);
  }

  function renderHistogram(items, prevItems) {
    const root = document.getElementById("rlHistogram");
    if (!root) return;

    if (!Array.isArray(items) || items.length === 0) {
      root.innerHTML = "<p>No histogram data available</p>";
      return;
    }

    const prevMap = (prevItems || []).reduce((acc, curr) => {
      acc[curr.bucket_label] = curr.count;
      return acc;
    }, {});

    const maxCount = Math.max(1, ...items.map((item) => Number(item.count) || 0));
    root.innerHTML = items.map((item) => {
      const count = Number(item.count) || 0;
      const heightPct = Math.max(4, (count / maxCount) * 100);
      const prevCount = prevMap[item.bucket_label];
      const changed = count !== prevCount && prevCount !== undefined;
      const barClass = changed ? " rl-pulse-bar" : "";
      const valClass = diffClass(count, prevCount);

      return `
        <div class="rl-bar-wrap" title="${text(item.bucket_label)}: ${formatInt(count)}">
          <div class="rl-bar-value${valClass}">${formatInt(count)}</div>
          <div class="rl-bar${barClass}" style="height:${heightPct}%;"></div>
          <div class="rl-bar-label">${text(item.bucket_label)}</div>
        </div>
      `;
    }).join("");
  }

  function renderDecisionMix(items, prevItems) {
    const root = document.getElementById("rlDecisionMix");
    if (!root) return;

    if (!Array.isArray(items) || items.length === 0) {
      root.innerHTML = "<p>No decision data available</p>";
      return;
    }

    const prevMap = (prevItems || []).reduce((acc, curr) => {
      acc[curr.action] = curr.count;
      return acc;
    }, {});

    const total = items.reduce((acc, item) => acc + (Number(item.count) || 0), 0);
    root.innerHTML = items.map((item) => {
      const count = Number(item.count) || 0;
      const pct = total > 0 ? (count / total) * 100 : 0;
      const action = text(item.action);
      const color = actionPalette[action] || "#505050";
      const valClass = diffClass(count, prevMap[action]);

      return `
        <div class="rl-mix-row">
          <div class="rl-mix-label">${action}</div>
          <div class="rl-mix-track">
            <div class="rl-mix-fill" style="width:${pct}%;background:${color};"></div>
          </div>
          <div class="rl-mix-value${valClass}">${formatInt(count)} (${formatPct(pct)})</div>
        </div>
      `;
    }).join("");
  }

  function renderTable(tableId, columns, rows, formatters, prevRows, primaryKey) {
    const table = document.getElementById(tableId);
    if (!table) return;

    if (!Array.isArray(rows) || rows.length === 0) {
      table.innerHTML = "<thead><tr><th>No data</th></tr></thead><tbody></tbody>";
      return;
    }

    const prevMap = (prevRows || []).reduce((acc, curr) => {
      if (primaryKey && curr[primaryKey]) {
        acc[curr[primaryKey]] = curr;
      }
      return acc;
    }, {});

    const thead = `<thead><tr>${columns.map((col) => `<th>${col.label}</th>`).join("")}</tr></thead>`;
    const tbodyRows = rows.map((row) => {
      const prevRow = prevMap[row[primaryKey]] || {};

      const tds = columns.map((col) => {
        const raw = row[col.key];
        const prevRaw = prevRow[col.key];
        const formatter = formatters && formatters[col.key];
        
        let rendered = formatter ? formatter(raw, row, prevRow) : text(raw);
        if (!formatter && prevRaw !== undefined && raw !== prevRaw && typeof raw === 'number') {
           const pClass = diffClass(raw, prevRaw);
           rendered = `<span class="${pClass.trim()}">${rendered}</span>`;
        }

        return `<td>${rendered}</td>`;
      }).join("");
      return `<tr>${tds}</tr>`;
    }).join("");

    table.innerHTML = `${thead}<tbody>${tbodyRows}</tbody>`;
  }

  function initialize() {
    if (!payload) {
      setBanner("Dashboard payload is unavailable.");
      return;
    }

    const ts = document.getElementById("rlLastUpdated");
    if (ts) ts.textContent = `Last updated: ${text(payload.refreshed_at_local)}`;

    if (payload.status !== "ok") {
      const err = text(payload.error_message || "Data fetch failed");
      setBanner(`Data warning: ${err}. Rendering fallback view.`);
    } else if (payload.state_note) {
      setBanner(payload.state_note);
    }

    const prev = prevPayload || {};

    renderKpis(payload.kpis || {}, prev.kpis);
    renderTrend(payload.trend || {});
    renderHistogram(payload.score_distribution || [], prev.score_distribution);
    renderDecisionMix(payload.decision_mix || [], prev.decision_mix);

    renderTable(
      "rlChannelMatrix",
      [
        { key: "channel", label: "Channel" },
        { key: "Allow", label: "Allow" },
        { key: "Block", label: "Block" },
        { key: "Challenge", label: "Challenge" },
        { key: "total", label: "Total" }
      ],
      payload.channel_matrix || [],
      {
        Allow: (v, r, p) => `<span class="${diffClass(v, p.Allow).trim()}">${formatInt(v)}</span>`,
        Block: (v, r, p) => `<span class="${diffClass(v, p.Block).trim()}">${formatInt(v)}</span>`,
        Challenge: (v, r, p) => `<span class="${diffClass(v, p.Challenge).trim()}">${formatInt(v)}</span>`,
        total: (v, r, p) => `<span class="${diffClass(v, p.total).trim()}">${formatInt(v)}</span>`
      },
      prev.channel_matrix,
      "channel"
    );

    renderTable(
      "rlTopMerchants",
      [
        { key: "merchant", label: "Merchant" },
        { key: "flagged_count", label: "Flagged" },
        { key: "avg_score", label: "Avg Score" },
        { key: "high_risk_rate_pct", label: "High Risk %" }
      ],
      payload.top_risky_merchants || [],
      {
        flagged_count: (v, r, p) => `<span class="${diffClass(v, p.flagged_count).trim()}">${formatInt(v)}</span>`,
        avg_score: (v, r, p) => `<span class="${diffClass(v, p.avg_score).trim()}">${formatFloat(v, 3)}</span>`,
        high_risk_rate_pct: (v, r, p) => {
           let inner = formatPct(v);
           const pClass = diffClass(v, p.high_risk_rate_pct);
           if (pClass) inner = `<span class="${pClass.trim()}">${inner}</span>`;
           return `<span class="rl-risk-cell-medium">${inner}</span>`;
        }
      },
      prev.top_risky_merchants,
      "merchant"
    );

    renderTable(
      "rlRecentFlagged",
      [
        { key: "event_time", label: "Event Time" },
        { key: "tranID", label: "Tran ID" },
        { key: "merchant", label: "Merchant" },
        { key: "channel", label: "Channel" },
        { key: "action", label: "Action" },
        { key: "score", label: "Score" },
        { key: "latency_ms", label: "Latency (ms)" }
      ],
      payload.recent_flagged_transactions || [],
      {
        score: (v, r, p) => {
          const num = Number(v);
          if (!Number.isFinite(num)) return "-";
          const className = num >= (payload.kpis ? payload.kpis.risk_threshold : 0.7) ? "rl-risk-cell-high" : "rl-risk-cell-medium";
          
          let inner = formatFloat(num, 3);
          if (p && p.score !== undefined) {
             const pClass = diffClass(num, p.score);
             if (pClass) inner = `<span class="${pClass.trim()}">${inner}</span>`;
          }
          return `<span class="${className}">${inner}</span>`;
        },
        latency_ms: (v) => formatFloat(v, 1)
      },
      prev.recent_flagged_transactions,
      "tranID"
    );
  }

  initialize();
})();

