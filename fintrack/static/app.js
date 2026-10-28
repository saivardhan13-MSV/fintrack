"use strict";

const API = "/api/v1";
const TOKEN_KEY = "fintrack.token";
const CATEGORY_COLORS = ["#2f6fde", "#12a37a", "#e8853d", "#9b5de5", "#e04f6b", "#2bb3c0",
                         "#c8a12b", "#7a8699"];

const $ = (id) => document.getElementById(id);
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const fmt = (amount) => money.format(Number(amount));
const charts = {};
let token = readToken();
let registering = false;

// --- helpers ---------------------------------------------------------------------------

function readToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

function saveToken(value) {
  token = value;
  try {
    if (value) localStorage.setItem(TOKEN_KEY, value); else localStorage.removeItem(TOKEN_KEY);
  } catch { /* storage unavailable: stay signed in for this page only */ }
}

/** Builds DOM nodes with textContent only, so user data can never inject HTML. */
function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "style") Object.assign(node.style, value);
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child != null) node.append(child instanceof Node ? child : String(child));
  }
  return node;
}

function errorText(data) {
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail.map((d) => `${d.loc[d.loc.length - 1]}: ${d.msg}`).join("; ");
  }
  return "Something went wrong";
}

async function api(path, { method = "GET", json, form } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let body = form;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  }
  const res = await fetch(API + path, { method, headers, body });
  if (res.status === 401 && token) {
    signOut();
    throw new Error("Your session expired. Please sign in again.");
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(errorText(data));
  return data;
}

function showError(message) {
  const banner = $("app-error");
  banner.textContent = message || "";
  banner.hidden = !message;
}

function selectedMonth() {
  return $("month").value;
}

function monthRange(ym) {
  const [y, m] = ym.split("-").map(Number);
  const last = new Date(y, m, 0).getDate();
  return { start: `${ym}-01`, end: `${ym}-${String(last).padStart(2, "0")}` };
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// --- auth ------------------------------------------------------------------------------

function setAuthMode(isRegister) {
  registering = isRegister;
  $("auth-subtitle").textContent = isRegister ? "Create your account" : "Sign in to your account";
  $("auth-submit").textContent = isRegister ? "Create account" : "Sign in";
  $("auth-toggle").textContent = isRegister
    ? "Already have an account? Sign in" : "New here? Create an account";
  $("auth-error").textContent = "";
}

async function onAuthSubmit(event) {
  event.preventDefault();
  const form = event.target;
  const email = form.email.value.trim();
  const password = form.password.value;
  const button = $("auth-submit");
  button.disabled = true;
  $("auth-error").textContent = "";
  try {
    if (registering) await api("/auth/register", { method: "POST", json: { email, password } });
    const login = new URLSearchParams({ username: email, password });
    const { access_token } = await api("/auth/token", { method: "POST", form: login });
    saveToken(access_token);
    form.reset();
    await showApp();
  } catch (err) {
    $("auth-error").textContent = err.message;
  } finally {
    button.disabled = false;
  }
}

function signOut() {
  saveToken(null);
  $("app-view").hidden = true;
  $("auth-view").hidden = false;
}

// --- rendering -------------------------------------------------------------------------

function renderKpis(d) {
  $("kpi-income").textContent = fmt(d.income);
  $("kpi-expenses").textContent = fmt(d.expenses);
  const balance = $("kpi-balance");
  balance.textContent = fmt(d.balance);
  balance.className = Number(d.balance) < 0 ? "neg" : "pos";
  $("kpi-savings").textContent = d.savings_rate == null ? "–" : `${d.savings_rate}%`;
  $("kpi-subs").textContent = fmt(d.subscriptions_monthly);
}

function renderCategories(categories) {
  const table = $("category-table");
  table.replaceChildren(...categories.map((c, i) => el("tr", {},
    el("td", {}, el("span", { class: "swatch",
      style: { background: CATEGORY_COLORS[i % CATEGORY_COLORS.length] } }), c.category),
    el("td", { class: "num" }, fmt(c.total)),
    el("td", { class: "num muted" }, `${c.percent}%`),
  )));
  if (!categories.length) {
    table.replaceChildren(el("tr", {}, el("td", { class: "muted" }, "No expenses this month.")));
  }
  drawChart("category", $("category-chart"), {
    type: "doughnut",
    data: {
      labels: categories.map((c) => c.category),
      datasets: [{
        data: categories.map((c) => Number(c.total)),
        backgroundColor: categories.map((_, i) => CATEGORY_COLORS[i % CATEGORY_COLORS.length]),
        borderColor: cssVar("--surface"),
        borderWidth: 2,
      }],
    },
    options: {
      maintainAspectRatio: false,
      cutout: "62%",
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => ` ${ctx.label}: ${fmt(ctx.raw)}` } },
      },
    },
  });
}

function renderBudgets(budgets) {
  const list = $("budget-list");
  if (!budgets.length) {
    list.replaceChildren(el("p", { class: "muted" }, "No budgets yet. Add one below."));
    return;
  }
  const labels = { ok: "On track", at_risk: "At risk", warning: "Almost used", exceeded: "Over" };
  list.replaceChildren(...budgets.map((b) => el("div", { class: "budget-row" },
    el("div", { class: "budget-top" },
      el("span", {}, el("strong", {}, b.category), " ",
        el("span", { class: `chip ${b.status}` }, labels[b.status])),
      el("span", { class: "muted" }, `${fmt(b.spent)} of ${fmt(b.limit)}`),
    ),
    el("div", { class: `bar ${b.status}`, role: "progressbar",
                "aria-valuenow": b.percent_used, "aria-valuemin": 0, "aria-valuemax": 100 },
      el("div", { style: { width: `${Math.min(b.percent_used, 100)}%` } })),
    el("span", { class: "muted", style: { fontSize: "0.8rem" } },
      Number(b.remaining) >= 0
        ? `${fmt(b.remaining)} left · projected ${fmt(b.projected)} by month end`
        : `${fmt(-Number(b.remaining))} over budget`),
  )));
}

function renderBills(upcoming) {
  $("bills-total").textContent = upcoming.renewals.length ? `${fmt(upcoming.total_due)} due` : "";
  const list = $("bills-list");
  if (!upcoming.renewals.length) {
    list.replaceChildren(el("li", { class: "muted" }, "No bills due in the next 30 days."));
    return;
  }
  list.replaceChildren(...upcoming.renewals.map((r) => el("li", {},
    el("span", {}, r.name, el("div", { class: "sub" },
      r.days_until === 0 ? "Today" : `${r.renews_on} · in ${r.days_until} days`)),
    el("strong", {}, fmt(r.amount)),
  )));
}

function renderTrend(points) {
  drawChart("trend", $("trend-chart"), {
    type: "bar",
    data: {
      labels: points.map((p) => p.month),
      datasets: [
        { label: "Income", data: points.map((p) => Number(p.income)),
          backgroundColor: cssVar("--income"), borderRadius: 4 },
        { label: "Expenses", data: points.map((p) => Number(p.expenses)),
          backgroundColor: cssVar("--expense"), borderRadius: 4 },
      ],
    },
    options: {
      maintainAspectRatio: false,
      scales: {
        x: { grid: { display: false }, ticks: { color: cssVar("--muted") } },
        y: { grid: { color: cssVar("--border") },
             ticks: { color: cssVar("--muted"), callback: (v) => fmt(v).replace(".00", "") } },
      },
      plugins: {
        legend: { labels: { color: cssVar("--text"), boxWidth: 12 } },
        tooltip: { callbacks: { label: (ctx) => ` ${ctx.dataset.label}: ${fmt(ctx.raw)}` } },
      },
    },
  });
}

function renderTransactions(page) {
  const rows = page.items.map((t) => el("tr", {},
    el("td", {}, t.occurred_on),
    el("td", {}, t.merchant),
    el("td", { class: "muted" }, t.category || "—"),
    el("td", { class: `num ${t.kind === "income" ? "pos" : ""}` },
      `${t.kind === "income" ? "+" : "−"}${fmt(t.amount)}`),
    el("td", { class: "num" }, el("button", {
      class: "icon-btn", title: "Delete", "aria-label": `Delete ${t.merchant}`,
      onclick: () => deleteTransaction(t.id),
    }, "✕")),
  ));
  const tbody = $("txn-table").querySelector("tbody");
  tbody.replaceChildren(...rows);
  if (!rows.length) {
    tbody.replaceChildren(el("tr", {}, el("td", { colspan: 5, class: "muted" },
      "No transactions this month. Add one above or import a CSV.")));
  }
  $("txn-count").textContent = page.total > page.items.length
    ? `Showing ${page.items.length} of ${page.total}` : "";
}

function drawChart(key, canvas, config) {
  if (typeof Chart === "undefined") return; // CDN unreachable: tables still show the data
  charts[key]?.destroy();
  charts[key] = new Chart(canvas, config);
}

// --- data loading ----------------------------------------------------------------------

async function loadDashboard() {
  const month = selectedMonth();
  const { start, end } = monthRange(month);
  try {
    const [dash, trend, txns] = await Promise.all([
      api(`/reports/dashboard?month=${month}`),
      api("/reports/monthly-trend?months=6"),
      api(`/transactions?start=${start}&end=${end}&limit=100`),
    ]);
    showError("");
    renderKpis(dash);
    renderCategories(dash.categories);
    renderBudgets(dash.budgets);
    renderBills(dash.upcoming_bills);
    renderTrend(trend);
    renderTransactions(txns);
  } catch (err) {
    showError(err.message);
  }
}

async function showApp() {
  $("auth-view").hidden = true;
  $("app-view").hidden = false;
  try {
    const me = await api("/auth/me");
    $("user-email").textContent = me.email;
  } catch (err) {
    showError(err.message);
    return;
  }
  await loadDashboard();
}

// --- actions ---------------------------------------------------------------------------

async function withButton(button, action) {
  button.disabled = true;
  try {
    await action();
  } catch (err) {
    showError(err.message);
  } finally {
    button.disabled = false;
  }
}

async function onAddTransaction(event) {
  event.preventDefault();
  const form = event.target;
  await withButton(form.querySelector("button"), async () => {
    await api("/transactions", { method: "POST", json: {
      occurred_on: form.occurred_on.value,
      description: form.description.value.trim(),
      amount: form.amount.value,
      kind: form.kind.value,
      category: form.category.value.trim() || null,
    } });
    const date = form.occurred_on.value;
    form.reset();
    form.occurred_on.value = date;
    await loadDashboard();
  });
}

async function deleteTransaction(id) {
  if (!confirm("Delete this transaction?")) return;
  try {
    await api(`/transactions/${id}`, { method: "DELETE" });
    await loadDashboard();
  } catch (err) {
    showError(err.message);
  }
}

async function onImportCsv(event) {
  const file = event.target.files[0];
  event.target.value = "";
  if (!file) return;
  const body = new FormData();
  body.append("file", file);
  try {
    const r = await api("/transactions/import", { method: "POST", form: body });
    const problems = r.errors.length ? `, ${r.errors.length} rows had errors` : "";
    $("import-result").textContent =
      `Imported ${r.imported}, skipped ${r.duplicates_skipped} duplicates${problems}.`;
    await loadDashboard();
  } catch (err) {
    showError(err.message);
  }
}

async function onSetBudget(event) {
  event.preventDefault();
  const form = event.target;
  await withButton(form.querySelector("button"), async () => {
    await api("/budgets", { method: "PUT", json: {
      category: form.category.value.trim(), monthly_limit: form.monthly_limit.value,
    } });
    form.reset();
    await loadDashboard();
  });
}

async function onDetect() {
  await withButton($("detect-btn"), async () => {
    const { detected } = await api("/subscriptions/detect", { method: "POST" });
    const list = $("detect-list");
    if (!detected.length) {
      list.replaceChildren(el("li", { class: "muted" }, "No recurring charges found yet."));
      return;
    }
    list.replaceChildren(...detected.map((d) => {
      const change = Number(d.price_change);
      const detail = `${d.billing_cycle} · ${Math.round(d.confidence * 100)}% confidence`
        + (change ? ` · price ${change > 0 ? "up" : "down"} ${fmt(Math.abs(change))}` : "");
      const action = d.already_tracked
        ? el("span", { class: "chip ok" }, "Tracked")
        : el("button", { class: "btn small", onclick: (e) => trackDetected(e.target, d) }, "Track");
      return el("li", {},
        el("span", {}, d.merchant, el("div", { class: "sub" }, detail)),
        el("span", {}, el("strong", {}, fmt(d.amount)), " ", action));
    }));
  });
}

async function trackDetected(button, d) {
  await withButton(button, async () => {
    const name = d.merchant.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
    await api("/subscriptions", { method: "POST", json: {
      name, merchant: d.merchant, amount: d.amount,
      billing_cycle: d.billing_cycle, next_renewal: d.next_renewal,
    } });
    button.replaceWith(el("span", { class: "chip ok" }, "Tracked"));
    await loadDashboard();
  });
}

// --- startup ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  const now = new Date();
  $("month").value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  $("txn-form").occurred_on.value = now.toLocaleDateString("en-CA"); // YYYY-MM-DD, local time

  $("auth-form").addEventListener("submit", onAuthSubmit);
  $("auth-toggle").addEventListener("click", () => setAuthMode(!registering));
  $("logout").addEventListener("click", signOut);
  $("month").addEventListener("change", () => { if (selectedMonth()) loadDashboard(); });
  $("txn-form").addEventListener("submit", onAddTransaction);
  $("budget-form").addEventListener("submit", onSetBudget);
  $("csv-input").addEventListener("change", onImportCsv);
  $("detect-btn").addEventListener("click", onDetect);

  if (token) showApp(); else signOut();
});
