const state = { data: null, currency: null, charts: {}, polling: null };
const money = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const integer = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });

document.querySelector("#run-form").addEventListener("submit", runSimulation);
document.querySelector("#currency").addEventListener("change", event => {
  state.currency = event.target.value;
  render();
});
document.querySelector("#time-grain").addEventListener("change", renderSalesChart);
initializeDashboard();

async function initializeDashboard() {
  await loadScenarios();
  const status = await loadStatus();
  if (status.status === "running") {
    setRunning(true);
    renderProgress(status);
    startPolling();
  }
  await loadDashboard();
}

async function runSimulation(event) {
  event.preventDefault();
  const status = document.querySelector("#run-status");
  setRunning(true);
  status.textContent = "Starting simulation…";
  try {
    const response = await fetch("/analytics/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario: document.querySelector("#scenario").value }),
    });
    if (!response.ok) throw new Error((await response.json()).detail || "Run failed");
    renderProgress(await response.json());
    status.textContent = "Running simulation and building analytical data…";
    startPolling();
  } catch (error) {
    status.textContent = error.message;
    setRunning(false);
  }
}

async function loadScenarios() {
  const response = await fetch("/analytics/scenarios");
  if (!response.ok) throw new Error("Unable to load scenarios");
  const scenarios = await response.json();
  const selector = document.querySelector("#scenario");
  selector.replaceChildren(...scenarios.map(value => option(value)));
}

async function loadStatus() {
  const response = await fetch("/analytics/status");
  if (!response.ok) throw new Error("Unable to load run status");
  return response.json();
}

function startPolling() {
  if (state.polling) clearInterval(state.polling);
  pollStatus();
  state.polling = setInterval(pollStatus, 10000);
}

async function pollStatus() {
  try {
    const current = await loadStatus();
    renderProgress(current);
    if (current.status === "completed") {
      stopPolling();
      setRunning(false);
      await loadDashboard();
    } else if (current.status === "failed") {
      stopPolling();
      setRunning(false);
      document.querySelector("#run-status").textContent = current.error || "Simulation failed";
    }
  } catch (error) {
    stopPolling();
    setRunning(false);
    document.querySelector("#run-status").textContent = error.message;
  }
}

function stopPolling() {
  if (state.polling) clearInterval(state.polling);
  state.polling = null;
}

function setRunning(running) {
  document.querySelector("#run-form button").disabled = running;
  document.querySelector("#scenario").disabled = running;
}

function renderProgress(current) {
  document.querySelector("#run-progress").classList.remove("hidden");
  const percent = Math.max(0, Math.min(100, Number(current.progress_percent || 0)));
  document.querySelector("#progress-bar").style.width = `${percent}%`;
  document.querySelector("#progress-percent").textContent = `${percent.toFixed(1)}%`;
  document.querySelector("#progress-ticks").textContent = `Tick ${integer.format(current.current_tick || 0)} / ${integer.format(current.total_ticks || 0)}`;
  document.querySelector("#progress-time").textContent = current.simulated_time || "";
}

async function loadDashboard() {
  const response = await fetch("/analytics/data");
  if (response.status === 404) return;
  if (!response.ok) throw new Error("Unable to load dashboard data");
  state.data = await response.json();
  const currencies = state.data.overview.map(row => row.currency);
  state.currency = currencies.includes(state.currency) ? state.currency : (currencies[0] || "");
  const selector = document.querySelector("#currency");
  selector.replaceChildren(...currencies.map(value => option(value)));
  selector.value = state.currency;
  document.querySelector("#dashboard").classList.remove("hidden");
  document.querySelector("#run-status").textContent = "Completed analytical run loaded.";
  render();
}

function render() {
  renderMetadata(); renderOverview(); renderSalesChart(); renderLocations();
  renderChannels(); renderProducts(); renderLostSales(); renderCustomers();
  renderInventory(); renderPromotions();
}

function renderMetadata() {
  const run = state.data.run;
  document.querySelector("#run-meta").replaceChildren(
    meta("Scenario", run.scenario), meta("Seed", run.seed),
    meta("Range", `${run.start} → ${run.end}`), meta("Tick", run.tick_unit),
    meta("Ticks", integer.format(run.ticks_processed)),
  );
}

function renderOverview() {
  const row = state.data.overview.find(item => item.currency === state.currency) || { net_revenue: 0, gross_revenue: 0, discount_amount: 0, completed_units: 0, lost_sales: 0, baskets: 0 };
  const values = [
    ["Net Revenue", cash(row.net_revenue)], ["Gross Revenue", cash(row.gross_revenue)],
    ["Discount Amount", cash(row.discount_amount)], ["Completed Units", integer.format(row.completed_units)],
    ["Lost Sales", cash(row.lost_sales)], ["Completed Baskets", integer.format(row.baskets)],
  ];
  document.querySelector("#kpis").replaceChildren(...values.map(([label, value]) => card(label, value)));
}

function renderSalesChart() {
  if (!state.data) return;
  const grain = document.querySelector("#time-grain").value;
  const rows = state.data.sales[grain].filter(row => row.currency === state.currency);
  const labels = rows.map(row => grain === "daily" ? row.date : `${row.year}-${String(row.month_number).padStart(2, "0")}`);
  chart("sales-chart", "line", labels, [
    dataset("Net sales", rows.map(row => number(row.net_sales)), "#42d3a4"),
    dataset("Lost sales", rows.map(row => number(row.lost_sales)), "#ff7d88"),
    dataset("Completed units", rows.map(row => row.completed_units), "#62a8ff", "y1"),
  ]);
}

function renderLocations() {
  const rows = state.data.locations.filter(row => row.currency === state.currency).slice(0, 12);
  chart("location-chart", "bar", rows.map(row => row.location_name), [
    dataset("Net sales", rows.map(row => number(row.net_sales)), "#42d3a4"),
    dataset("Lost sales", rows.map(row => number(row.lost_sales)), "#ff7d88"),
  ]);
  table("location-table", rows, [["location_name", "Location"], ["city_name", "City"], ["completed_units", "Units"], ["completed_baskets", "Baskets"], ["net_sales", "Net sales"], ["lost_sales", "Lost sales"]]);
}

function renderChannels() {
  const rows = state.data.channels.filter(row => row.currency === state.currency);
  chart("channel-chart", "bar", rows.map(row => row.channel), [
    dataset("Net sales", rows.map(row => number(row.net_sales)), "#62a8ff"),
    dataset("Lost sales", rows.map(row => number(row.lost_sales)), "#ff7d88"),
  ]);
  table("channel-table", rows, [["channel", "Channel"], ["baskets", "Baskets"], ["customers", "Customers"], ["completed_units", "Units"], ["net_sales", "Net sales"], ["lost_sales", "Lost sales"]]);
}

function renderProducts() {
  const products = state.data.products.filter(row => row.currency === state.currency).slice(0, 12);
  const categories = state.data.categories.filter(row => row.currency === state.currency);
  table("products-table", products, [["product_name", "Product"], ["completed_units", "Units"], ["net_sales", "Net sales"], ["rejected_units", "Rejected"], ["lost_sales", "Lost sales"]]);
  table("categories-table", categories, [["category_name", "Category"], ["completed_units", "Units"], ["net_sales", "Net sales"], ["rejected_units", "Rejected"], ["lost_sales", "Lost sales"]]);
}

function renderLostSales() {
  const data = state.data.lost_sales;
  table("lost-products", data.products.filter(byCurrency), [["product_name", "Product"], ["rejected_quantity", "Rejected"], ["lost_sales", "Lost sales"]]);
  table("lost-locations", data.locations.filter(byCurrency), [["location_name", "Location"], ["rejected_quantity", "Rejected"], ["lost_sales", "Lost sales"]]);
  table("lost-reasons", data.reasons.filter(byCurrency), [["rejection_reason", "Reason"], ["rejected_quantity", "Rejected"], ["lost_sales", "Lost sales"]]);
}

function renderCustomers() {
  const rows = state.data.customers.filter(byCurrency).slice(0, 15);
  table("customers-table", rows, [["customer_id", "Customer"], ["segment", "Segment"], ["purchase_frequency", "Configured frequency"], ["basket_count", "Baskets"], ["completed_units", "Units"], ["net_sales", "Net sales"]]);
}

function renderInventory() {
  const replenishment = state.data.inventory.replenishment[0] || {};
  const received = state.data.inventory.summary.reduce((sum, row) => sum + row.quantity_received_by_replenishment, 0);
  const removed = state.data.inventory.summary.reduce((sum, row) => sum + row.quantity_removed_by_sales, 0);
  document.querySelector("#inventory-summary").replaceChildren(
    mini("Units removed", integer.format(removed)), mini("Units received", integer.format(received)),
    mini("Requested", integer.format(replenishment.requested_count || 0)),
    mini("Completed", integer.format(replenishment.completed_count || 0)),
    mini("Pending", integer.format(replenishment.pending_count || 0)),
    mini("Completion rate", `${(number(replenishment.completion_rate || 0) * 100).toFixed(1)}%`.replace("0.0%", "0%")),
    mini("Avg lead", replenishment.avg_completion_lead_ticks == null ? "—" : `${number(replenishment.avg_completion_lead_ticks).toFixed(1)} ticks`),
  );
  table("inventory-table", state.data.inventory.products.slice(0, 15), [["product_name", "Product"], ["movement_type", "Movement"], ["movement_count", "Count"], ["quantity", "Quantity"]]);
}

function renderPromotions() {
  table("promotion-summary", state.data.promotions.summary.filter(byCurrency), [["associated_sales_lines", "Promoted lines"], ["distinct_baskets", "Promoted baskets"], ["completed_units", "Units"], ["associated_net_sales", "Associated net sales"]]);
  table("promotion-table", state.data.promotions.associations.filter(byCurrency), [["promotion_name", "Promotion"], ["associated_sales_lines", "Lines"], ["distinct_baskets", "Baskets"], ["associated_net_sales", "Associated net sales"]]);
}

function chart(id, type, labels, datasets) {
  if (!window.Chart) return;
  if (state.charts[id]) state.charts[id].destroy();
  state.charts[id] = new Chart(document.getElementById(id), {
    type, data: { labels, datasets },
    options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false }, scales: { x: { grid: { color: "#203a5244" } }, y: { beginAtZero: true, grid: { color: "#203a5244" } }, y1: { display: false, beginAtZero: true } }, plugins: { legend: { labels: { color: "#8ca5b8" } } } },
  });
}

function table(id, rows, columns) {
  const wrapper = document.createElement("div"); wrapper.className = "table-scroll";
  const element = document.createElement("table");
  const head = document.createElement("thead"); const header = document.createElement("tr");
  columns.forEach(([, label]) => { const th = document.createElement("th"); th.textContent = label; header.append(th); });
  head.append(header); element.append(head);
  const body = document.createElement("tbody");
  rows.forEach(row => { const tr = document.createElement("tr"); columns.forEach(([key]) => { const td = document.createElement("td"); const value = row[key]; td.textContent = formatValue(key, value); if (typeof value === "number" || /sales|amount|units|quantity|count|frequency/.test(key)) td.className = "number"; tr.append(td); }); body.append(tr); });
  element.append(body); wrapper.append(element); document.querySelector(`#${id}`).replaceChildren(wrapper);
}

function dataset(label, data, color, axis = "y") { return { label, data, borderColor: color, backgroundColor: `${color}88`, tension: .25, yAxisID: axis }; }
function byCurrency(row) { return row.currency === state.currency; }
function number(value) { return Number(value || 0); }
function cash(value) { return `${state.currency} ${money.format(number(value))}`; }
function formatValue(key, value) { if (value == null) return "—"; if (/sales|amount/.test(key)) return money.format(number(value)); if (typeof value === "number") return integer.format(value); return String(value); }
function option(value) { const node = document.createElement("option"); node.value = value; node.textContent = value; return node; }
function meta(label, value) { const node = document.createElement("span"); const strong = document.createElement("strong"); strong.textContent = `${label}: `; node.append(strong, String(value)); return node; }
function card(label, value) { const node = document.createElement("div"); node.className = "kpi"; const title = document.createElement("span"); title.textContent = label; const metric = document.createElement("strong"); metric.textContent = value; node.append(title, metric); return node; }
function mini(label, value) { const node = document.createElement("div"); const title = document.createElement("span"); title.textContent = label; const metric = document.createElement("strong"); metric.textContent = value; node.append(title, metric); return node; }
