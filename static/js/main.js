/* ============================================================
   Stock Backtester — main.js
   ============================================================ */

let strategiesData = [];
let chartRendered = false;

// Portfolio: [{symbol, name}, ...]
let portfolio = [];

// Persists user-entered param values per strategy: { strategyId: { paramId: value } }
let strategyParamCache = {};

// ---- Initialisation ----

document.addEventListener("DOMContentLoaded", () => {
  setDefaultDates();
  loadStrategies();

  const addBtn = document.getElementById("ticker-add-btn");
  const tickerInput = document.getElementById("ticker-input");

  addBtn.addEventListener("click", onAddTicker);
  tickerInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") onAddTicker();
  });

  document.getElementById("strategy-select").addEventListener("change", onStrategyChange);
  document.getElementById("run-btn").addEventListener("click", runBacktest);
  document.getElementById("compare-btn").addEventListener("click", runCompare);
});

function setDefaultDates() {
  const today = new Date();
  const threeYearsAgo = new Date(today);
  threeYearsAgo.setFullYear(today.getFullYear() - 3);
  document.getElementById("end-date").value = formatDate(today);
  document.getElementById("start-date").value = formatDate(threeYearsAgo);
}

function formatDate(d) {
  return d.toISOString().split("T")[0];
}

// ---- Load strategies ----

async function loadStrategies() {
  try {
    const res = await fetch("/api/strategies");
    const data = await res.json();
    strategiesData = data.strategies;

    const select = document.getElementById("strategy-select");
    select.innerHTML = "";
    strategiesData.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s.id;
      opt.textContent = s.name;
      select.appendChild(opt);
    });

    if (strategiesData.length > 0) onStrategyChange();
  } catch (e) {
    console.error("Failed to load strategies", e);
  }
}

function onStrategyChange() {
  const select = document.getElementById("strategy-select");
  const prevSid = select.dataset.prevStrategy;

  // Save current param values for the strategy we're leaving
  if (prevSid) {
    const saved = {};
    document.querySelectorAll("#strategy-params input").forEach((el) => {
      const ptype = el.dataset.paramType;
      if (ptype === "boolean") saved[el.dataset.paramId] = el.checked;
      else if (ptype === "integer") saved[el.dataset.paramId] = parseInt(el.value, 10);
      else if (ptype === "float") saved[el.dataset.paramId] = parseFloat(el.value);
      else saved[el.dataset.paramId] = el.value;
    });
    strategyParamCache[prevSid] = saved;
  }

  const sid = select.value;
  select.dataset.prevStrategy = sid;

  const strategy = strategiesData.find((s) => s.id === sid);
  if (!strategy) return;
  document.getElementById("strategy-description").textContent = strategy.description;
  renderParamFields(strategy.parameters, strategyParamCache[sid]);
}

function renderParamFields(params, savedValues) {
  const container = document.getElementById("strategy-params");
  container.innerHTML = "";

  params.forEach((p) => {
    const div = document.createElement("div");
    div.className = "mb-3";

    const label = document.createElement("label");
    label.className = "form-label small fw-semibold";
    label.textContent = p.label;
    label.setAttribute("for", `param-${p.id}`);

    const input = document.createElement("input");
    input.id = `param-${p.id}`;
    input.className = "form-control form-control-sm bg-dark text-light border-secondary";
    input.dataset.paramId = p.id;
    input.dataset.paramType = p.type;

    const restoredValue = savedValues && savedValues[p.id] !== undefined ? savedValues[p.id] : p.default;

    if (p.type === "integer" || p.type === "float") {
      input.type = "number";
      if (p.min !== undefined) input.min = p.min;
      if (p.max !== undefined) input.max = p.max;
      if (p.type === "integer") input.step = 1;
      input.value = restoredValue;
    } else if (p.type === "boolean") {
      input.type = "checkbox";
      input.checked = restoredValue;
      input.className = "form-check-input";
    } else {
      input.type = "text";
      input.value = restoredValue;
    }

    div.appendChild(label);
    div.appendChild(input);
    container.appendChild(div);
  });
}

function collectParams() {
  const params = {};
  document.querySelectorAll("#strategy-params input").forEach((el) => {
    const pid = el.dataset.paramId;
    const ptype = el.dataset.paramType;
    if (ptype === "boolean") params[pid] = el.checked;
    else if (ptype === "integer") params[pid] = parseInt(el.value, 10);
    else if (ptype === "float") params[pid] = parseFloat(el.value);
    else params[pid] = el.value;
  });
  return params;
}

// ---- Portfolio / Ticker management ----

async function onAddTicker() {
  const input = document.getElementById("ticker-input");
  const symbol = input.value.trim().toUpperCase();
  if (!symbol) return;

  if (portfolio.find((p) => p.symbol === symbol)) {
    setFeedback(`${symbol} is already in the pool.`, "warning");
    return;
  }

  setAddLoading(true);
  setFeedback("Validating...", "secondary");

  try {
    const res = await fetch(`/api/tickers/validate?symbol=${encodeURIComponent(symbol)}`);
    const data = await res.json();

    if (data.valid) {
      portfolio.push({ symbol: data.symbol, name: data.name });
      renderChips();
      input.value = "";
      setFeedback(``, "");
      updateRunButton();
    } else {
      setFeedback(data.error, "danger");
    }
  } catch (e) {
    setFeedback("Validation failed.", "danger");
  } finally {
    setAddLoading(false);
  }
}

function removeTicker(symbol) {
  portfolio = portfolio.filter((p) => p.symbol !== symbol);
  renderChips();
  updateRunButton();
}

function renderChips() {
  const container = document.getElementById("ticker-chips");
  container.innerHTML = "";
  portfolio.forEach(({ symbol, name }) => {
    const chip = document.createElement("div");
    chip.className = "ticker-chip";
    chip.innerHTML = `
      <span class="fw-semibold">${symbol}</span>
      <span class="chip-name">${shortenName(name)}</span>
      <button class="chip-remove" title="Remove" onclick="removeTicker('${symbol}')">&#x2715;</button>
    `;
    container.appendChild(chip);
  });
}

function shortenName(name) {
  return name.length > 18 ? name.slice(0, 16) + "…" : name;
}

function updateRunButton() {
  const disabled = portfolio.length === 0;
  document.getElementById("run-btn").disabled = disabled;
  document.getElementById("compare-btn").disabled = disabled;
}

function setFeedback(msg, type) {
  const el = document.getElementById("ticker-feedback");
  if (!msg) { el.innerHTML = ""; return; }
  const colors = { danger: "text-danger", warning: "text-warning", secondary: "text-secondary", success: "text-success" };
  el.innerHTML = `<span class="${colors[type] || ""}">${msg}</span>`;
}

function setAddLoading(loading) {
  document.getElementById("ticker-add-spinner").classList.toggle("d-none", !loading);
  document.getElementById("ticker-add-label").classList.toggle("d-none", loading);
  document.getElementById("ticker-add-btn").disabled = loading;
}

// ---- Run backtest ----

async function runBacktest() {
  if (portfolio.length === 0) return;

  const startDate = document.getElementById("start-date").value;
  const endDate = document.getElementById("end-date").value;
  const strategyId = document.getElementById("strategy-select").value;
  const capital = parseFloat(document.getElementById("initial-capital").value);
  const parameters = collectParams();

  if (!startDate || !endDate) { showError("Please select start and end dates."); return; }
  if (new Date(endDate) <= new Date(startDate)) { showError("End date must be after start date."); return; }

  setLoading(true);
  hideError();

  try {
    const res = await fetch("/api/backtest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbols: portfolio.map((p) => p.symbol),
        start_date: startDate,
        end_date: endDate,
        strategy_id: strategyId,
        parameters,
        initial_capital: capital,
      }),
    });

    const data = await res.json();
    if (data.status === "error") {
      showError(data.error);
    } else {
      renderResults(data);
    }
  } catch (e) {
    showError("Request failed. Is the server running?");
  } finally {
    setLoading(false);
  }
}

// ---- Render results ----

function renderResults(data) {
  document.getElementById("placeholder").classList.add("d-none");
  document.getElementById("results").classList.remove("d-none");
  document.getElementById("compare-results").classList.add("d-none");

  const { metadata, metrics, equity_curve, per_stock, trades } = data;

  // Header
  const symbolList = metadata.symbols.join(", ");
  document.getElementById("result-title").textContent = `Portfolio: ${symbolList}`;
  document.getElementById("result-subtitle").textContent =
    `${metadata.start_date} → ${metadata.end_date}  ·  ${metadata.strategy_name}  ·  ` +
    `$${metadata.per_stock_capital.toLocaleString()} per stock  ·  ${metadata.n_stocks} stock${metadata.n_stocks > 1 ? "s" : ""}`;

  // Metrics
  setMetric("m-total-return", metrics.total_return_pct, "%", true);
  setMetric("m-ann-return", metrics.annualized_return_pct, "%", true);
  document.getElementById("m-sharpe").textContent = metrics.sharpe_ratio.toFixed(2);
  document.getElementById("m-max-dd").textContent = metrics.max_drawdown_pct.toFixed(2) + "%";
  document.getElementById("m-rebalances").textContent = metrics.total_rebalances;
  setMetric("m-bh-return", metrics.buy_and_hold_return_pct, "%", true);

  document.getElementById("m-trades").textContent = metrics.total_trades;
  document.getElementById("m-final-value").textContent =
    metrics.final_portfolio_value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  // Chart
  renderChart(equity_curve, per_stock, metadata);

  // Trade table
  renderTradeTable(trades);
}

function setMetric(id, value, suffix, colorize) {
  const el = document.getElementById(id);
  const sign = value >= 0 ? "+" : "";
  el.textContent = sign + value.toFixed(2) + suffix;
  if (colorize) {
    el.className = "fs-5 fw-bold " + (value >= 0 ? "text-pos" : "text-neg");
  }
}

function renderChart(equityCurve, perStock, metadata) {
  const traces = [];

  // Per-stock traces (dashed, lighter)
  if (perStock.length > 1) {
    perStock.forEach((stock) => {
      traces.push({
        x: stock.equity_curve.map((p) => p.date),
        y: stock.equity_curve.map((p) => p.portfolio_value),
        type: "scatter",
        mode: "lines",
        name: stock.symbol,
        line: { color: stock.color, width: 1.2, dash: "dot" },
        hovertemplate: `${stock.symbol}<br>%{x}<br>$%{y:,.2f}<extra></extra>`,
        opacity: 0.7,
      });
    });
  }

  // Total portfolio
  traces.push({
    x: equityCurve.map((p) => p.date),
    y: equityCurve.map((p) => p.portfolio_value),
    type: "scatter",
    mode: "lines",
    name: metadata.strategy_name + " (Total)",
    line: { color: "#ffffff", width: 2.5 },
    hovertemplate: "Total<br>%{x}<br>$%{y:,.2f}<extra></extra>",
  });

  // Benchmark (B&H)
  traces.push({
    x: equityCurve.map((p) => p.date),
    y: equityCurve.map((p) => p.benchmark_value),
    type: "scatter",
    mode: "lines",
    name: "Buy & Hold (Equal Weight)",
    line: { color: "#9ca3af", width: 1.5, dash: "dash" },
    hovertemplate: "B&H<br>%{x}<br>$%{y:,.2f}<extra></extra>",
  });

  const layout = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#9ca3af", size: 11 },
    xaxis: { gridcolor: "#374151", linecolor: "#374151", showgrid: true },
    yaxis: { gridcolor: "#374151", linecolor: "#374151", tickprefix: "$", tickformat: ",.0f", showgrid: true },
    legend: { bgcolor: "rgba(0,0,0,0)", orientation: "h", y: 1.12 },
    margin: { t: 10, b: 40, l: 70, r: 20 },
    hovermode: "x unified",
  };

  const config = { responsive: true, displayModeBar: true, displaylogo: false };

  if (!chartRendered) {
    Plotly.newPlot("equity-chart", traces, layout, config);
    chartRendered = true;
  } else {
    Plotly.react("equity-chart", traces, layout, config);
  }
}

function renderTradeTable(trades) {
  const tbody = document.getElementById("trade-tbody");
  const noTrades = document.getElementById("no-trades");
  const tradeCount = document.getElementById("trade-count");

  tbody.innerHTML = "";

  tradeCount.textContent = `${trades.length} trade${trades.length !== 1 ? "s" : ""}`;

  if (trades.length === 0) {
    noTrades.classList.remove("d-none");
    return;
  }
  noTrades.classList.add("d-none");

  trades.forEach((t) => {
    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td class="text-secondary">${t.trade_num}</td>
      <td class="fw-semibold">${t.symbol || ""}</td>
      <td><span class="${t.type === "BUY" ? "badge-buy" : "badge-sell"}">${t.type}</span></td>
      <td>${t.date}</td>
      <td>$${t.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</td>
      <td>${t.shares}</td>
      <td>$${t.portfolio_value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
    `;
    tbody.appendChild(tr);
  });
}

// ---- Compare All Strategies ----

async function runCompare() {
  if (portfolio.length === 0) return;

  const startDate = document.getElementById("start-date").value;
  const endDate = document.getElementById("end-date").value;
  const capital = parseFloat(document.getElementById("initial-capital").value);

  if (!startDate || !endDate) { showError("Please select start and end dates."); return; }
  if (new Date(endDate) <= new Date(startDate)) { showError("End date must be after start date."); return; }

  setCompareLoading(true);
  hideError();

  try {
    const res = await fetch("/api/backtest/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbols: portfolio.map((p) => p.symbol),
        start_date: startDate,
        end_date: endDate,
        initial_capital: capital,
      }),
    });

    const data = await res.json();
    if (data.status === "error") {
      showError(data.error);
    } else {
      renderCompareResults(data);
    }
  } catch (e) {
    showError("Request failed. Is the server running?");
  } finally {
    setCompareLoading(false);
  }
}

function renderCompareResults(data) {
  document.getElementById("placeholder").classList.add("d-none");
  document.getElementById("results").classList.add("d-none");
  document.getElementById("compare-results").classList.remove("d-none");

  const { metadata, strategies, benchmark } = data;

  // Header
  document.getElementById("compare-title").textContent =
    `Strategy Comparison: ${metadata.symbols.join(", ")}`;
  document.getElementById("compare-subtitle").textContent =
    `${metadata.start_date} → ${metadata.end_date}  ·  $${metadata.initial_capital.toLocaleString()} initial  ·  ${metadata.n_stocks} stock${metadata.n_stocks > 1 ? "s" : ""}`;

  // Build chart traces
  const traces = [];

  strategies.forEach((s) => {
    traces.push({
      x: s.equity_curve.map((p) => p.date),
      y: s.equity_curve.map((p) => p.portfolio_value),
      type: "scatter",
      mode: "lines",
      name: s.name,
      line: { color: s.color, width: 2 },
      hovertemplate: `${s.name}<br>%{x}<br>$%{y:,.2f}<extra></extra>`,
    });
  });

  // Benchmark
  traces.push({
    x: benchmark.map((p) => p.date),
    y: benchmark.map((p) => p.portfolio_value),
    type: "scatter",
    mode: "lines",
    name: "Buy & Hold",
    line: { color: "#9ca3af", width: 2, dash: "dash" },
    hovertemplate: "Buy & Hold<br>%{x}<br>$%{y:,.2f}<extra></extra>",
  });

  const layout = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#9ca3af", size: 11 },
    xaxis: { gridcolor: "#374151", linecolor: "#374151", showgrid: true },
    yaxis: { gridcolor: "#374151", linecolor: "#374151", tickprefix: "$", tickformat: ",.0f", showgrid: true },
    legend: { bgcolor: "rgba(0,0,0,0)", orientation: "h", y: 1.15 },
    margin: { t: 10, b: 40, l: 70, r: 20 },
    hovermode: "x unified",
  };

  const config = { responsive: true, displayModeBar: true, displaylogo: false };
  Plotly.newPlot("compare-chart", traces, layout, config);

  // Metrics table
  const tbody = document.getElementById("compare-tbody");
  tbody.innerHTML = "";

  strategies.forEach((s) => {
    const m = s.metrics;
    const tr = document.createElement("tr");
    const retClass = m.total_return_pct >= 0 ? "text-pos" : "text-neg";
    const annClass = m.annualized_return_pct >= 0 ? "text-pos" : "text-neg";

    tr.innerHTML = `
      <td class="fw-semibold" style="color:${s.color}">${s.name}</td>
      <td class="${retClass}">${m.total_return_pct >= 0 ? "+" : ""}${m.total_return_pct.toFixed(2)}%</td>
      <td class="${annClass}">${m.annualized_return_pct >= 0 ? "+" : ""}${m.annualized_return_pct.toFixed(2)}%</td>
      <td>${m.sharpe_ratio.toFixed(2)}</td>
      <td class="text-danger">${m.max_drawdown_pct.toFixed(2)}%</td>
      <td>$${m.final_portfolio_value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
    `;
    tbody.appendChild(tr);
  });

  // Add benchmark row
  const bhFirst = benchmark[0].portfolio_value;
  const bhLast = benchmark[benchmark.length - 1].portfolio_value;
  const bhReturn = ((bhLast - bhFirst) / bhFirst * 100);
  const bhRetClass = bhReturn >= 0 ? "text-pos" : "text-neg";
  const bhTr = document.createElement("tr");
  bhTr.innerHTML = `
    <td class="fw-semibold text-secondary">Buy & Hold</td>
    <td class="${bhRetClass}">${bhReturn >= 0 ? "+" : ""}${bhReturn.toFixed(2)}%</td>
    <td class="text-secondary">—</td>
    <td class="text-secondary">—</td>
    <td class="text-secondary">—</td>
    <td>$${bhLast.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
  `;
  tbody.appendChild(bhTr);
}

function setCompareLoading(loading) {
  document.getElementById("compare-spinner").classList.toggle("d-none", !loading);
  document.getElementById("compare-icon").classList.toggle("d-none", loading);
  document.getElementById("compare-btn").disabled = loading || portfolio.length === 0;
  document.getElementById("run-btn").disabled = loading || portfolio.length === 0;
}

// ---- Helpers ----

function setLoading(loading) {
  document.getElementById("run-spinner").classList.toggle("d-none", !loading);
  document.getElementById("run-icon").classList.toggle("d-none", loading);
  document.getElementById("run-btn").disabled = loading || portfolio.length === 0;
}

function showError(msg) {
  document.getElementById("error-msg").textContent = msg;
  document.getElementById("error-alert").classList.remove("d-none");
}

function hideError() {
  document.getElementById("error-alert").classList.add("d-none");
}
