/* GridWise LLM frontend — plain JS, no build step.
 *
 * On load it shows a saved result for a public sample (instant, no network wait),
 * warms the live API in the background, and "Run live" sends the scenario to
 * POST /optimize-energy.
 */

// ---------- Config ----------
// Local backend while developing, the deployed API otherwise. Override with ?api=https://...
const API =
  new URLSearchParams(location.search).get("api") ||
  (["localhost", "127.0.0.1"].includes(location.hostname) && location.port !== "8000"
    ? "http://127.0.0.1:8000"
    : "https://gridwise-llm-api.vercel.app");

const HOURS = [...Array(24).keys()];

// ---------- State ----------
const state = {
  samples: [],     // [{id, label, input, output}] from samples.json
  input: null,     // scenario being edited (request body)
  result: null,    // { request, response, source: "saved" | "live", ms }
  stale: false,    // notes edited since the shown result
  rawTab: "res",
};

// ---------- Small helpers ----------
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n, d = 0) => Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const hourLabel = (h) => (h % 12 || 12) + (h < 12 ? " AM" : " PM");

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.add("on");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove("on"), 1800);
}

// Compress [12,13,14,18] into "12 PM–3 PM, 6 PM–7 PM" (end-exclusive, like the API).
function hourRanges(hours) {
  const out = [];
  [...hours].sort((a, b) => a - b).forEach((h) => {
    const last = out[out.length - 1];
    if (last && last[1] === h) last[1] = h + 1;
    else out.push([h, h + 1]);
  });
  return out.map(([a, b]) => `${hourLabel(a)}–${hourLabel(b % 24)}`).join(", ");
}

// ---------- API ----------
async function checkHealth() {
  const pill = $("apiStatus");
  const set = (cls, text) => { pill.querySelector(".dot").className = "dot " + cls; pill.lastElementChild.textContent = text; };
  try {
    const t0 = performance.now();
    const r = await fetch(API + "/health", { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    set("ok", `API online · ${Math.round(performance.now() - t0)} ms`);
  } catch {
    set("bad", "API offline");
  }
}

async function runLive() {
  const btn = $("runBtn");
  const request = buildRequest();
  btn.disabled = true;
  btn.classList.add("busy");
  $("banner").hidden = true;
  setPipeline(0);
  const steps = [setTimeout(() => setPipeline(1), 450), setTimeout(() => setPipeline(2), 900)];
  const t0 = performance.now();
  try {
    const r = await fetch(API + "/optimize-energy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(errorText(r.status, body)), { failStep: failedStep(r.status, body) });
    state.result = { request, response: body, source: "live", ms: performance.now() - t0 };
    state.stale = false;
    setPipeline(5);
    renderResults();
  } catch (err) {
    setPipeline(err.failStep ?? 0, true);
    const banner = $("banner");
    banner.textContent = err.failStep === undefined ? "Could not reach the API. Check your connection and try again." : err.message;
    banner.hidden = false;
  } finally {
    steps.forEach(clearTimeout);
    btn.disabled = false;
    btn.classList.remove("busy");
  }
}

// 422 with a field list = request validation; 422 with text = LP found no valid schedule.
function failedStep(status, body) {
  if (status === 422) return Array.isArray(body.detail) ? 0 : 2;
  return 3;
}

function errorText(status, body) {
  if (Array.isArray(body.detail)) {
    return "Request rejected: " + body.detail.map((d) => `${d.loc.slice(1).join(".")} — ${d.msg}`).join("; ");
  }
  return `API error ${status}${body.detail ? ": " + body.detail : ""}`;
}

// Pipeline strip: steps before `active` are done; `failed` marks the active step red.
function setPipeline(active, failed = false) {
  document.querySelectorAll("#pipeline li").forEach((li, i) => {
    li.className = i < active ? "done" : i === active ? (failed ? "fail" : "active") : "";
  });
}

// ---------- Inputs panel ----------
function selectSample(id) {
  const sample = state.samples.find((s) => s.id === id) || state.samples[0];
  state.input = structuredClone(sample.input);
  state.result = { request: sample.input, response: sample.output, source: "saved" };
  state.stale = false;
  $("sampleSelect").value = sample.id;
  history.replaceState(null, "", "#" + sample.id);
  $("banner").hidden = true;
  setPipeline(5);
  renderInputs();
  renderResults();
}

function buildRequest() {
  return { ...state.input, operator_notes: state.input.operator_notes.map((n) => n.trim()).filter(Boolean) };
}

function renderInputs() {
  renderNotes();
  const b = state.input.battery;
  const stats = [
    ["Capacity", b.capacity_kwh], ["Starts at", b.initial_energy_kwh], ["Minimum", b.minimum_energy_kwh],
    ["Max charge / h", b.max_charge_kwh_per_hour], ["Max discharge / h", b.max_discharge_kwh_per_hour],
  ];
  $("battery").innerHTML = stats.map(([k, v]) => `<div><span>${k}</span><b>${fmt(v)} kWh</b></div>`).join("");
  drawProfile();
}

function renderNotes() {
  const notes = state.input.operator_notes;
  $("notes").innerHTML = notes.map((n, i) => `
    <div class="note">
      <span class="idx">#${i}</span>
      <textarea rows="1" data-i="${i}" aria-label="Operator note ${i}">${esc(n)}</textarea>
      ${notes.length > 1 ? `<button class="rm" data-i="${i}" aria-label="Remove note">×</button>` : ""}
    </div>`).join("");
  $("notes").querySelectorAll("textarea").forEach(grow);
  $("addNote").disabled = notes.length >= 3;
}

function grow(t) {
  t.style.height = "auto";
  t.style.height = t.scrollHeight + 2 + "px";
}

function markStale() {
  state.stale = true;
  renderSource();
}

// ---------- Results ----------
function renderResults() {
  renderSource();
  renderKpis();
  renderDirectives();
  drawMix();
  drawSoc();
  renderTable();
  renderRaw();
}

function renderSource() {
  const r = state.result;
  const tag = r.source === "live"
    ? `<span class="tag live">● Live result</span><span>${esc(r.response.scenario_id)} · answered in ${fmt(r.ms / 1000, 1)} s</span>`
    : `<span class="tag saved">Saved result</span><span>Pre-computed by the same API. Press <b>Run live</b> to call it now.</span>`;
  $("source").innerHTML = tag + (state.stale ? `<span class="tag stale">Notes edited — run to update</span>` : "");
}

// Solar actually available after any solar_reduction directives.
function effectiveSolar(request, directives) {
  const solar = request.hours.map((h) => h.solar_kwh);
  directives.filter((d) => d.applies && d.directive_type === "solar_reduction").forEach((d) => {
    d.structured_adjustment.hours.forEach((h) => (solar[h] *= d.structured_adjustment.factor));
  });
  return solar;
}

function renderKpis() {
  const { request, response } = state.result;
  const solar = effectiveSolar(request, response.directive_interpretation);
  // Baseline: no battery, use available solar, buy the rest from the grid.
  const baseline = request.hours.reduce((sum, h, i) => sum + Math.max(0, h.demand_kwh - solar[i]) * h.tariff_bdt_per_kwh, 0);
  const saved = baseline - response.total_cost_bdt;
  const kpis = [
    ["Grid cost", `${fmt(response.total_cost_bdt)} BDT`, "minimized by the LP", ""],
    ["Saved by battery", `${fmt(saved)} BDT`, `${fmt((saved / baseline) * 100, 1)}% vs. no battery`, "good"],
    ["Grid energy", `${fmt(response.total_grid_kwh)} kWh`, "over 24 hours", ""],
    ["Peak import", `${fmt(response.peak_grid_kwh)} kWh`, "highest single hour", ""],
  ];
  $("kpis").innerHTML = kpis.map(([k, v, s, cls]) => `<div class="kpi ${cls}"><span>${k}</span><b>${v}</b><small>${s}</small></div>`).join("");
}

const PARAM_LABELS = {
  factor: (v) => `solar × ${v} (${fmt((1 - v) * 100)}% cut)`,
  minimum_energy_kwh: (v) => `keep ≥ ${fmt(v)} kWh`,
  max_grid_kwh: (v) => `grid ≤ ${fmt(v)} kWh/h`,
};

function renderDirectives() {
  const { request, response } = state.result;
  $("directives").innerHTML = response.directive_interpretation.map((d) => {
    const adj = d.structured_adjustment || {};
    const hours = adj.hours || [];
    const params = Object.entries(adj).filter(([k]) => k !== "hours").map(([k, v]) => PARAM_LABELS[k]?.(v) ?? `${k}: ${v}`);
    if (hours.length) params.unshift(hourRanges(hours));
    const strip = hours.length
      ? `<div class="strip">${HOURS.map((h) => `<i class="${hours.includes(h) ? "on" : ""}" title="${hourLabel(h)}"></i>`).join("")}</div>
         <div class="strip-labels"><span>12 AM</span><span>6 AM</span><span>12 PM</span><span>6 PM</span><span>12 AM</span></div>`
      : "";
    return `
      <div class="dir ${d.applies ? "" : "noop"}">
        <div class="dir-top">
          <span class="muted small mono">#${d.note_index}</span>
          <span class="badge">${esc(d.directive_type)}</span>
          <span class="params">${esc(params.join(" · ") || "ignored — no effect on today's schedule")}</span>
        </div>
        <div class="dir-note">“${esc(request.operator_notes[d.note_index] ?? "")}”</div>
        ${strip}
        <div class="dir-why">${esc(d.explanation)}</div>
      </div>`;
  }).join("");
}

function renderTable() {
  const { request, response } = state.result;
  const head = "<tr><th>Hour</th><th>Demand</th><th>Solar used</th><th>Grid</th><th>Battery</th><th>kWh</th><th>Stored after</th><th>Tariff</th></tr>";
  const rows = response.hourly_plan.map((p) => {
    const h = request.hours[p.hour];
    return `<tr><td>${hourLabel(p.hour)}</td><td>${fmt(h.demand_kwh, 1)}</td><td>${fmt(p.solar_used_kwh, 1)}</td><td>${fmt(p.grid_kwh, 1)}</td>
      <td><span class="act ${p.battery_action}">${p.battery_action}</span></td><td>${fmt(p.battery_kwh, 1)}</td>
      <td>${fmt(p.battery_energy_after_kwh, 1)}</td><td>${fmt(h.tariff_bdt_per_kwh, 1)}</td></tr>`;
  }).join("");
  $("planTable").innerHTML = `<thead>${head}</thead><tbody>${rows}</tbody>`;
}

function rawText() {
  const { request, response } = state.result;
  if (state.rawTab === "req") return JSON.stringify(request, null, 2);
  if (state.rawTab === "curl") {
    return `curl -X POST ${API}/optimize-energy \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify(request).replace(/'/g, "'\\''")}'`;
  }
  return JSON.stringify(response, null, 2);
}

function renderRaw() {
  $("raw").textContent = rawText();
  document.querySelectorAll(".raw-tabs .tab").forEach((t) => t.classList.toggle("on", t.dataset.raw === state.rawTab));
}

// ---------- Charts (hand-rolled SVG) ----------
function niceMax(v) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find((k) => k * p >= v * 1.05) * p;
}

// Round a raw tick interval up to 1, 2, 2.5 or 5 × 10^n.
function niceStep(raw) {
  const p = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 2.5, 5, 10].find((k) => k * p >= raw) * p;
}

// Shared frame: gridlines, y labels (optional right axis), hour labels. Returns scale helpers.
function frame(el, height, top, bottom = 0, rightTop = null) {
  const W = Math.max(320, el.clientWidth);
  const m = { l: 44, r: rightTop ? 40 : 12, t: 10, b: 24 };
  const bw = (W - m.l - m.r) / 24;
  const step = niceStep((top - bottom) / 4);
  const yMin = Math.floor(bottom / step) * step;
  const ticks = Math.ceil((top * 1.02 - yMin) / step);
  const yMax = yMin + ticks * step;
  const rStep = rightTop ? niceStep(rightTop / ticks) : 0;
  const y = (v) => m.t + (1 - (v - yMin) / (yMax - yMin)) * (height - m.t - m.b);
  const y2 = rightTop ? (v) => m.t + (1 - v / (rStep * ticks)) * (height - m.t - m.b) : null;
  let svg = "";
  for (let i = 0; i <= ticks; i++) {
    const v = yMin + i * step;
    svg += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}" stroke="${css("--line-2")}"/>`;
    svg += `<text x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end" font-size="10.5" fill="${css("--ink-3")}">${fmt(v)}</text>`;
    if (rightTop) svg += `<text x="${W - m.r + 6}" y="${y2(i * rStep) + 4}" font-size="10.5" fill="${css("--tariff")}">${fmt(i * rStep)}</text>`;
  }
  const every = W < 560 ? 6 : 3;
  for (let h = 0; h < 24; h += every) {
    svg += `<text x="${m.l + h * bw + bw / 2}" y="${height - 6}" text-anchor="middle" font-size="10.5" fill="${css("--ink-3")}">${hourLabel(h).replace(" ", "")}</text>`;
  }
  return { W, m, bw, y, y2, svg, x: (h) => m.l + h * bw };
}

// Invisible per-hour columns that drive the tooltip.
function hoverColumns(f, height) {
  return HOURS.map((h) => `<rect class="hover-col" data-h="${h}" x="${f.x(h)}" y="${f.m.t}" width="${f.bw}" height="${height - f.m.t - f.m.b}"/>`).join("");
}

function attachTooltip(el, rowsFor) {
  const tip = $("tip");
  el.onmousemove = (e) => {
    const h = e.target.dataset?.h;
    if (h === undefined) return (tip.hidden = true);
    tip.innerHTML = `<b>${hourLabel(+h)}</b>` + rowsFor(+h).map(([k, v]) => `<div><span>${k}</span><span>${v}</span></div>`).join("");
    tip.hidden = false;
    const x = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8);
    tip.style.left = x + "px";
    tip.style.top = e.clientY + 14 + "px";
  };
  el.onmouseleave = () => (tip.hidden = true);
}

function stepPath(values, x, y, bw) {
  return values.map((v, h) => `${h ? "L" : "M"}${x(h)},${y(v)} L${x(h) + bw},${y(v)}`).join(" ");
}

function drawProfile() {
  const el = $("profile");
  const hours = state.input.hours;
  const W = Math.max(280, el.clientWidth), H = 90, bw = W / 24;
  const max = niceMax(Math.max(...hours.map((h) => Math.max(h.demand_kwh, h.solar_kwh))));
  const tMax = Math.max(...hours.map((h) => h.tariff_bdt_per_kwh)) * 1.15;
  const y = (v) => H - 4 - (v / max) * (H - 10);
  const yt = (v) => H - 4 - (v / tMax) * (H - 10);
  let svg = "";
  hours.forEach((h, i) => {
    svg += `<rect x="${i * bw + 1}" y="${y(h.demand_kwh)}" width="${bw - 2}" height="${H - 4 - y(h.demand_kwh)}" rx="2" fill="${css("--demand")}" opacity=".14"/>`;
    svg += `<rect x="${i * bw + bw * 0.2}" y="${y(h.solar_kwh)}" width="${bw * 0.6}" height="${H - 4 - y(h.solar_kwh)}" rx="2" fill="${css("--solar")}"/>`;
  });
  svg += `<path d="${stepPath(hours.map((h) => h.tariff_bdt_per_kwh), (i) => i * bw, yt, bw)}" fill="none" stroke="${css("--tariff")}" stroke-width="1.6"/>`;
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${svg}</svg>`;
}

function drawMix() {
  const el = $("mixChart");
  const { request, response } = state.result;
  const plan = response.hourly_plan;
  const charge = plan.map((p) => (p.battery_action === "charge" ? p.battery_kwh : 0));
  const dis = plan.map((p) => (p.battery_action === "discharge" ? p.battery_kwh : 0));
  const top = Math.max(...plan.map((p, h) => p.solar_used_kwh + dis[h] + p.grid_kwh), ...request.hours.map((h) => h.demand_kwh));
  const bottom = -Math.max(...charge);
  const H = 260;
  const f = frame(el, H, top, bottom);
  let svg = f.svg + `<line x1="${f.m.l}" x2="${f.W - f.m.r}" y1="${f.y(0)}" y2="${f.y(0)}" stroke="${css("--ink-3")}" stroke-width=".8"/>`;
  plan.forEach((p, h) => {
    let base = 0;
    [[p.solar_used_kwh, "--solar"], [dis[h], "--dis"], [p.grid_kwh, "--grid"]].forEach(([v, c]) => {
      if (v <= 0) return;
      svg += `<rect x="${f.x(h) + f.bw * 0.14}" y="${f.y(base + v)}" width="${f.bw * 0.72}" height="${f.y(base) - f.y(base + v)}" fill="${css(c)}"/>`;
      base += v;
    });
    if (charge[h] > 0) svg += `<rect x="${f.x(h) + f.bw * 0.14}" y="${f.y(0)}" width="${f.bw * 0.72}" height="${f.y(-charge[h]) - f.y(0)}" fill="${css("--chg")}"/>`;
  });
  svg += `<path d="${stepPath(request.hours.map((h) => h.demand_kwh), f.x, f.y, f.bw)}" fill="none" stroke="${css("--demand")}" stroke-width="2" stroke-dasharray="5 3"/>`;
  svg += hoverColumns(f, H);
  el.innerHTML = `<svg viewBox="0 0 ${f.W} ${H}" role="img" aria-label="Stacked hourly supply by source with demand line">${svg}</svg>`;
  attachTooltip(el, (h) => [
    ["Demand", fmt(request.hours[h].demand_kwh, 1) + " kWh"],
    ["Solar used", fmt(plan[h].solar_used_kwh, 1) + " kWh"],
    ["Battery out", fmt(dis[h], 1) + " kWh"],
    ["Grid", fmt(plan[h].grid_kwh, 1) + " kWh"],
    ["Charging", fmt(charge[h], 1) + " kWh"],
  ]);
}

function drawSoc() {
  const el = $("socChart");
  const { request, response } = state.result;
  const b = request.battery;
  const soc = response.hourly_plan.map((p) => p.battery_energy_after_kwh);
  const tariffs = request.hours.map((h) => h.tariff_bdt_per_kwh);
  const H = 220;
  const f = frame(el, H, b.capacity_kwh, 0, Math.max(...tariffs));
  let svg = "";
  // Shade hours touched by any applied directive.
  const windowHours = new Set(response.directive_interpretation.filter((d) => d.applies).flatMap((d) => d.structured_adjustment.hours));
  windowHours.forEach((h) => {
    svg += `<rect x="${f.x(h)}" y="${f.m.t}" width="${f.bw}" height="${H - f.m.t - f.m.b}" fill="${css("--accent")}" opacity=".09"/>`;
  });
  svg += f.svg;
  // Battery energy: line from the initial level through each hour's end state.
  const pts = [[f.x(0), f.y(b.initial_energy_kwh)], ...soc.map((v, h) => [f.x(h) + f.bw, f.y(v)])];
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x},${y}`).join(" ");
  svg += `<path d="${line} L${pts.at(-1)[0]},${f.y(0)} L${pts[0][0]},${f.y(0)} Z" fill="${css("--dis")}" opacity=".15"/>`;
  svg += `<path d="${line}" fill="none" stroke="${css("--dis")}" stroke-width="2.2"/>`;
  svg += `<line x1="${f.m.l}" x2="${f.W - f.m.r}" y1="${f.y(b.capacity_kwh)}" y2="${f.y(b.capacity_kwh)}" stroke="${css("--ink-3")}" stroke-dasharray="3 3"/>`;
  svg += `<path d="${stepPath(tariffs, f.x, f.y2, f.bw)}" fill="none" stroke="${css("--tariff")}" stroke-width="1.8"/>`;
  svg += hoverColumns(f, H);
  el.innerHTML = `<svg viewBox="0 0 ${f.W} ${H}" role="img" aria-label="Battery stored energy and grid tariff by hour">${svg}</svg>`;
  attachTooltip(el, (h) => [
    ["Stored after", fmt(soc[h], 1) + " kWh"],
    ["Action", `${response.hourly_plan[h].battery_action} ${fmt(response.hourly_plan[h].battery_kwh, 1)}`],
    ["Tariff", fmt(tariffs[h], 1) + " BDT/kWh"],
  ]);
}

// ---------- Events ----------
function bindEvents() {
  $("sampleSelect").onchange = (e) => selectSample(e.target.value);
  $("runBtn").onclick = runLive;
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !$("runBtn").disabled) runLive();
  });

  $("notes").addEventListener("input", (e) => {
    if (!e.target.matches("textarea")) return;
    state.input.operator_notes[+e.target.dataset.i] = e.target.value;
    grow(e.target);
    markStale();
  });
  $("notes").addEventListener("click", (e) => {
    if (!e.target.matches(".rm")) return;
    state.input.operator_notes.splice(+e.target.dataset.i, 1);
    renderNotes();
    markStale();
  });
  $("addNote").onclick = () => {
    state.input.operator_notes.push("");
    renderNotes();
    $("notes").querySelector(".note:last-child textarea").focus();
  };

  document.querySelector(".raw-tabs").addEventListener("click", (e) => {
    if (!e.target.dataset.raw) return;
    state.rawTab = e.target.dataset.raw;
    renderRaw();
  });
  $("copyRaw").onclick = () => navigator.clipboard.writeText(rawText()).then(() => toast("Copied"));

  $("themeBtn").onclick = () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("gw.theme", document.documentElement.dataset.theme); } catch {}
    drawProfile();
    renderResults();
  };

  let resizeTimer;
  addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { drawProfile(); drawMix(); drawSoc(); }, 120);
  });
}

// ---------- Boot ----------
async function init() {
  try { const t = localStorage.getItem("gw.theme"); if (t) document.documentElement.dataset.theme = t; } catch {}
  $("docsLink").href = API + "/docs";
  checkHealth(); // warms the serverless function while the user reads
  bindEvents();
  state.samples = await fetch("samples.json").then((r) => r.json());
  $("sampleSelect").innerHTML = state.samples
    .map((s) => `<option value="${s.id}">${s.id.replace("SAMPLE-", "#")} · ${esc(s.label)}</option>`)
    .join("");
  selectSample(location.hash.slice(1));
}

init();
