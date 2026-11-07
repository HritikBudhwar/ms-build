const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const PEOPLE = [
  ["Ravi Kumar", "AP Executive"],
  ["Meera Iyer", "Head of Procurement"],
  ["Arjun Rao", "Logistics Manager"],
  ["Kavya Menon", "Financial Controller"],
];
const ACTION_STYLE = {
  APPROVE: ["good", "✓ Approve"],
  APPROVE_PARTIAL: ["good", "◐ Approve partial"],
  REQUEST_VENDOR_CORRECTION: ["warn", "↩ Ask vendor to correct"],
  ROUTE_FOR_APPROVAL: ["warn", "↑ Escalate to senior"],
  HOLD: ["crit", "■ Hold"],
};
const ACTION_TO_DECISION = { APPROVE: "APPROVED", APPROVE_PARTIAL: "PARTIAL", REQUEST_VENDOR_CORRECTION: "REJECTED", ROUTE_FOR_APPROVAL: "ROUTED", HOLD: "HELD" };
const SEV = { critical: ["crit", "!"], warning: ["warn", "▲"], info: ["", "i"] };

let BOOK = null;
let current = null;

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return r.json();
}

function toast(html, ms = 5000) {
  const t = $("#toast");
  t.innerHTML = html;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), ms);
}

function modal(html) {
  $("#modal-body").innerHTML = html;
  $("#modal").hidden = false;
}
$("#modal-x").onclick = () => ($("#modal").hidden = true);
$("#modal").onclick = (e) => { if (e.target.id === "modal") $("#modal").hidden = true; };

function md(text) {
  const lines = esc(text).split("\n");
  let html = "", inList = false;
  for (const raw of lines) {
    const l = raw.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`(.+?)`/g, "<code>$1</code>");
    if (/^\s*[-*] /.test(l)) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += "<li>" + l.replace(/^\s*[-*] /, "") + "</li>";
      continue;
    }
    if (inList) { html += "</ul>"; inList = false; }
    if (/^#{1,3} /.test(l)) html += "<h3>" + l.replace(/^#+ /, "") + "</h3>";
    else if (l.trim()) html += "<p>" + l + "</p>";
  }
  return html + (inList ? "</ul>" : "");
}

// ---------- tabs ----------
document.querySelectorAll(".tab").forEach((b) => (b.onclick = () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === b));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + b.dataset.view));
  if (b.dataset.view === "curve") renderCurve();
}));

// ---------- health ----------
async function loadHealth() {
  const h = await api("/api/health");
  $("#health").innerHTML = `
    <span class="pill"><span class="dot ${h.hindsight_configured ? "ok" : "bad"}"></span>Hindsight · ${esc(h.bank_id)}</span>
    <span class="pill"><span class="dot ${h.llm_configured ? "ok" : "bad"}"></span>${esc(h.llm_model)}</span>`;
}

// ---------- queue ----------
async function loadBook() {
  BOOK = await api("/api/book");
  const sel = $("#explore-vendor");
  sel.innerHTML = '<option value="">All vendors</option>' + BOOK.vendors.map((v) => `<option value="${v.id}">${esc(v.name)}</option>`).join("");
  renderQueue();
}

function chipFor(code, hard) {
  const crit = hard && ["GSTIN_INVALID", "DUPLICATE_EXACT", "TAX_TYPE_MISMATCH"].includes(code);
  return `<span class="chip ${crit ? "crit" : "warn"}">${esc(code.replaceAll("_", " ").toLowerCase())}</span>`;
}

function renderQueue() {
  const live = BOOK.invoices.filter((i) => i.phase === "live");
  const hist = BOOK.invoices.filter((i) => i.phase === "history").reverse();
  const row = (i) => `
    <button class="qrow ${current === i.id ? "active" : ""}" data-id="${i.id}">
      <div class="qtop"><span>${esc(i.vendor)}</span><span>${inr(i.total)}</span></div>
      <div class="qmeta"><span class="mono">${esc(i.invoice_number)}</span><span>${i.received_date}</span></div>
      <div class="chips">
        ${i.codes.length ? i.codes.map((c) => chipFor(c, i.hard_stop)).join("") : '<span class="chip ok">clean</span>'}
        ${i.decision ? `<span class="chip">decided · ${esc(i.decision.decision.toLowerCase())}</span>` : ""}
      </div>
    </button>`;
  $("#queue").innerHTML = `<h4>November queue · ${live.length}</h4>${live.map(row).join("")}
    <h4>Decided history (Aug–Oct) · ${hist.length}</h4>${hist.map(row).join("")}`;
  document.querySelectorAll(".qrow").forEach((b) => (b.onclick = () => openInvoice(b.dataset.id)));
}

// ---------- invoice detail ----------
async function openInvoice(id) {
  current = id;
  history.replaceState(null, "", "#" + id);
  renderQueue();
  const d = await api(`/api/invoices/${id}`);
  const { invoice: inv, vendor: v, po, grn } = d;
  const poRate = Object.fromEntries((po?.lines || []).map((l) => [l.sku, l.rate]));
  const grnQty = Object.fromEntries((grn?.lines || []).map((l) => [l.sku, l.qty_received]));
  const tax = inv.taxes.igst ? `IGST ${inr(inv.taxes.igst)}` : `CGST ${inr(inv.taxes.cgst)} · SGST ${inr(inv.taxes.sgst)}`;

  $("#detail").innerHTML = `
    <div class="card">
      <div class="inv-head">
        <div>
          <h2>${esc(v.name)}</h2>
          <div class="sub">${esc(v.city)} · GSTIN <span class="mono">${esc(inv.vendor_gstin)}</span> · ${esc(v.category)}
            ${v.msme ? ` · <b>MSME ${esc(v.msme.category)}</b>` : ""}</div>
          <div class="sub">Invoice <span class="mono">${esc(inv.invoice_number)}</span> dated ${inv.invoice_date} · received ${inv.received_date} · PO <span class="mono">${esc(inv.po_number)}</span></div>
        </div>
        <div>
          <div class="amount">${inr(inv.total)}</div>
          <div class="sub" style="text-align:right">Taxable ${inr(inv.taxable_value)} · ${tax}</div>
          <div class="row" style="justify-content:flex-end;margin-top:8px">
            <button class="btn" id="brief-btn">Vendor brief (reflect)</button>
            <button class="btn mem" id="run-btn">Run Munshi</button>
          </div>
        </div>
      </div>
      <table class="lines" style="margin-top:14px">
        <thead><tr><th>Item</th><th>HSN/SAC</th><th class="num">Billed qty</th><th class="num">GRN qty</th><th class="num">PO rate</th><th class="num">Billed rate</th><th class="num">GST</th></tr></thead>
        <tbody>
          ${inv.lines.map((l) => `<tr>
            <td>${esc(l.desc)}</td><td class="mono">${l.hsn}</td>
            <td class="num ${l.qty > (grnQty[l.sku] ?? l.qty) ? "bad-num" : ""}">${l.qty}</td>
            <td class="num">${grnQty[l.sku] ?? "-"}</td>
            <td class="num">${inr(poRate[l.sku])}</td>
            <td class="num ${l.rate > (poRate[l.sku] || 0) * 1.01 ? "bad-num" : ""}">${inr(l.rate)}</td>
            <td class="num">${l.gst_rate}%</td></tr>`).join("")}
          ${inv.extra_charges.map((c) => `<tr><td>${esc(c.desc)} <span class="chip warn">not on PO</span></td><td></td><td></td><td></td><td></td><td class="num bad-num">${inr(c.amount)}</td><td class="num">${c.gst_rate}%</td></tr>`).join("")}
        </tbody>
      </table>
      ${inv.tds_section_on_invoice ? `<div class="sub" style="margin-top:8px">Invoice states TDS section <b>${esc(inv.tds_section_on_invoice)}</b> · vendor master: <b>${esc(v.tds_section || "not set")}</b></div>` : ""}
    </div>

    <div class="section-title">Deterministic AP controls</div>
    <div class="findings">${renderFindings(d.findings)}</div>

    <div id="analysis"></div>`;

  $("#run-btn").onclick = () => run(id);
  $("#brief-btn").onclick = () => brief(v);
  if (d.analyses?.on) renderAnalysis(d.analyses, d.decision);
}

function renderFindings(findings) {
  if (!findings.length) return `<div class="finding"><span class="ic">✓</span><div><b>All controls passed</b></div></div>`;
  return findings.map((f) => `
    <div class="finding ${f.severity}">
      <span class="ic">${SEV[f.severity][1]}</span>
      <div><b>${esc(f.title)}${f.hard ? '<span class="hard">HARD CONTROL · memory cannot override</span>' : ""}</b>
      <span class="sub">${esc(f.detail)}</span></div>
    </div>`).join("");
}

async function run(id) {
  const btn = $("#run-btn");
  btn.disabled = true;
  $("#analysis").innerHTML = `<div class="section-title">Munshi is working</div>
    <div class="card steps">
      <div>✓ 9 AP controls run (3-way match, GSTIN checksum, GSTR-2B, tax type, duplicates, TDS, MSME 43B(h))</div>
      <div><span class="spinner"></span> Recalling from Hindsight: vendor memory + exception-pattern memory</div>
      <div><span class="spinner"></span> Deciding twice, with and without memory, so you can compare</div>
    </div>`;
  try {
    const res = await api(`/api/invoices/${id}/analyse`, { method: "POST", body: JSON.stringify({ compare: true }) });
    renderAnalysis(res, null);
    loadBook();
  } catch (e) {
    $("#analysis").innerHTML = `<div class="guard">Analysis failed: ${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
  }
}

function sideHtml(a, label) {
  const d = a.decision;
  const [cls, text] = ACTION_STYLE[d.action] || ["warn", d.action];
  const cites = (ids) => (ids || []).map((m) => `<button class="cite" data-mem="${esc(m)}">${esc(m)}</button>`).join("");
  return `
    <div class="side ${a.memory_on ? "on" : ""}">
      <div class="side-label"><span>${label}</span><span>${a.memory_on ? `${a.memories.length} memories recalled` : "stateless"}</span></div>
      <span class="action ${cls}">${text}</span>
      <div class="headline">${esc(d.headline)}</div>
      <div class="money"><span>Pay now <b>${inr(a.payable)}</b></span><span>Held <b>${inr(a.held)}</b></span>
        <span>Confidence <b>${Math.round(d.confidence * 100)}%</b></span></div>
      ${d.route_to ? `<div class="route">Routed to <b>${esc(d.route_to.name)}</b> · ${esc(d.route_to.role)}</div>` : ""}
      ${d.learned_rule_applied ? `<div class="rule"><b>Learned rule applied:</b> ${esc(d.learned_rule_applied)}</div>` : ""}
      ${d.guardrail ? `<div class="guard">${esc(d.guardrail)}</div>` : ""}
      <ol class="reasons">${(d.reasoning || []).map((r) => `<li>${esc(r.point)}${cites(r.memory_ids)}</li>`).join("")}</ol>
      ${d.vendor_email ? `<details class="email"><summary>Draft email to vendor: ${esc(d.vendor_email.subject)}</summary>\n${esc(d.vendor_email.body)}</details>` : ""}
      ${d.degraded ? `<div class="note-small">Reasoning model unavailable; safe fallback used.</div>` : ""}
      ${d.dropped_citations ? `<div class="note-small">${d.dropped_citations} citation(s) to non-recalled memories removed.</div>` : ""}
      ${a.memory_error ? `<div class="guard">Hindsight recall failed: ${esc(a.memory_error)}</div>` : ""}
      <div class="note-small">${a.timings.recall_ms != null ? `recall ${a.timings.recall_ms} ms · ` : ""}${a.timings.llm_ms != null ? `reasoning ${a.timings.llm_ms} ms · ` : ""}total ${a.timings.total_ms} ms</div>
    </div>`;
}

function renderAnalysis(res, decided) {
  const on = res.on;
  const mems = on.memories || [];
  $("#analysis").innerHTML = `
    <div class="section-title">Decision · same invoice, same model, same prompt</div>
    <div class="compare">
      ${res.off ? sideHtml(res.off, "Without memory") : ""}
      ${sideHtml(on, "With Hindsight memory")}
    </div>

    <div class="section-title">Recalled from Hindsight</div>
    <div class="mem-list">${mems.length ? mems.map(memCard).join("") : '<div class="sub">Nothing relevant in memory yet. This is how every invoice looks on day one.</div>'}</div>

    <div class="section-title">Your decision teaches Munshi</div>
    <div class="card" id="decide-box">${decided ? decidedHtml(decided) : decideForm(on)}</div>`;

  document.querySelectorAll(".cite").forEach((b) => (b.onclick = () => {
    const el = document.querySelector(`.mem[data-id="${b.dataset.mem}"]`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("flash");
    setTimeout(() => el.classList.remove("flash"), 1600);
  }));
  if (!decided) wireDecide(on);
}

function memCard(m) {
  return `<div class="mem" data-id="${esc(m.id)}">
    <div class="mem-top"><span class="mem-id">${esc(m.id)}</span><span>${esc(m.date)}</span>
      ${m.scope ? `<span class="scope">${m.scope === "vendor" ? "this vendor" : "similar exception"}</span>` : ""}
      <span class="scope">${esc(m.type || "")}</span></div>
    ${esc(m.text)}</div>`;
}

function decideForm(a) {
  const d = a.decision;
  const who = d.route_to ? PEOPLE.find((p) => p[0] === d.route_to.name) || PEOPLE[0] : PEOPLE[0];
  return `
    <div class="decide">
      <div class="row">
        <button class="btn primary" id="accept-btn">Accept Munshi's recommendation</button>
        <span class="sub">or record your own decision below. Either way it is retained to Hindsight.</span>
      </div>
      <div class="decide-grid">
        <select id="d-decision">
          ${["APPROVED", "PARTIAL", "REJECTED", "HELD", "ROUTED"].map((x) => `<option ${ACTION_TO_DECISION[d.action] === x ? "selected" : ""}>${x}</option>`).join("")}
        </select>
        <select id="d-by">${PEOPLE.map((p) => `<option value="${p[0]}|${p[1]}" ${p[0] === who[0] ? "selected" : ""}>${p[0]} · ${p[1]}</option>`).join("")}</select>
      </div>
      <textarea id="d-note" placeholder="Why? State the rule for next time, e.g. 'Accept up to 2.5% under clause 7.2; above that route to me.'"></textarea>
      <div><button class="btn mem" id="override-btn">Record decision & teach Munshi</button></div>
    </div>`;
}

function decidedHtml(dec) {
  return `<div class="decided"><b>${esc(dec.decision)}</b> by ${esc(dec.by)} (${esc(dec.role)}) on ${esc(dec.date)}
    ${dec.accepted_agent ? " · accepted Munshi's recommendation" : ""}<br>${esc(dec.note)}</div>`;
}

function wireDecide(a) {
  const submit = async (body) => {
    $("#decide-box").innerHTML = `<span class="spinner"></span> Retaining to Hindsight…`;
    try {
      const res = await api(`/api/invoices/${current}/decide`, { method: "POST", body: JSON.stringify(body) });
      $("#decide-box").innerHTML = decidedHtml(res.decision) +
        (res.retained ? `<div class="section-title">Retained memory</div><div class="mem"><div class="mem-top">${res.retained.tags.map((t) => `<span class="scope">${esc(t)}</span>`).join("")}</div><pre class="mono" style="white-space:pre-wrap;margin:0">${esc(res.retained.content)}</pre></div>` : "");
      toast(`Retained to Hindsight · ${res.retained ? res.retained.tags.length : 0} tags. The next invoice from this vendor will recall it.`);
      loadBook();
    } catch (e) {
      $("#decide-box").innerHTML = `<div class="guard">${esc(e.message)}</div>`;
    }
  };
  $("#accept-btn").onclick = () => {
    const [by, role] = $("#d-by").value.split("|");
    const d = a.decision;
    submit({ decision: ACTION_TO_DECISION[d.action], by, role, accepted_agent: true,
      note: [d.headline, d.learned_rule_applied && `Rule applied: ${d.learned_rule_applied}`].filter(Boolean).join(" ") });
  };
  $("#override-btn").onclick = () => {
    const note = $("#d-note").value.trim();
    if (!note) { $("#d-note").focus(); toast("Add a note. It is what Munshi learns from."); return; }
    const [by, role] = $("#d-by").value.split("|");
    submit({ decision: $("#d-decision").value, by, role, note, accepted_agent: false });
  };
}

async function brief(v) {
  modal(`<h3>${esc(v.name)}</h3><p class="sub"><span class="spinner"></span> Hindsight reflect is reading this vendor's history…</p>`);
  try {
    const r = await api(`/api/vendors/${v.id}/brief`);
    modal(`<h3>Vendor brief · ${esc(v.name)}</h3><p class="note-small">Generated by Hindsight <code>reflect</code> over memories tagged <code>vendor:${v.id}</code></p><div class="md">${md(r.text)}</div>`);
  } catch (e) {
    modal(`<h3>${esc(v.name)}</h3><div class="guard">${esc(e.message)}</div>`);
  }
}

// ---------- learning curve ----------
async function renderCurve() {
  const m = await api("/api/metrics");
  const pts = m.points.filter((p) => p.had_exception);
  const kpi = (label, value, delta) => `<div class="card kpi"><div class="label">${label}</div><div class="value">${value}</div><div class="delta">${delta}</div></div>`;
  const pct = (v) => (v == null ? "-" : v + "%");
  let html = `<h2 style="margin-bottom:4px">Exceptions resolved without a senior approver</h2>
    <p class="sub" style="margin-top:0">Each point is one invoice that failed a control, in the order it arrived. The line is the running share Munshi resolved on its own (approve, partial pay, or vendor correction) without escalating.</p>
    <div class="kpis">
      ${kpi("Aug–Oct (memory filling up)", pct(m.history_resolved_without_senior_pct), "of exceptions handled without escalation")}
      ${kpi("November (with memory)", pct(m.live_resolved_without_senior_pct), "of exceptions handled without escalation")}
      ${kpi("Exceptions processed", m.exceptions_total, "across 7 vendors")}
      ${kpi("Recommendations accepted", pct(m.accepted_pct), "by the reviewer as-is")}
    </div>`;
  if (!pts.length) {
    $("#curve").innerHTML = html + `<div class="card sub">No decided exceptions yet. Run <code>python scripts/replay_history.py</code>, then decide a few November invoices.</div>`;
    return;
  }
  const W = 960, H = 280, L = 44, R = 16, T = 16, B = 40;
  const x = (i) => L + (pts.length === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (pts.length - 1));
  const y = (v) => T + (1 - v / 100) * (H - T - B);
  let ok = 0;
  const run = pts.map((p, i) => { if (!p.needs_senior) ok++; return Math.round((100 * ok) / (i + 1)); });
  const firstLive = pts.findIndex((p) => p.phase === "live");
  let svg = `<svg class="strip" viewBox="0 0 ${W} ${H}" role="img" aria-label="Running share of exceptions resolved without senior approval">`;
  for (const g of [0, 50, 100]) svg += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(g)}" y2="${y(g)}"/><text x="${L - 8}" y="${y(g) + 4}" text-anchor="end">${g}%</text>`;
  if (firstLive > 0) {
    const xd = (x(firstLive - 1) + x(firstLive)) / 2;
    svg += `<line class="divider" x1="${xd}" x2="${xd}" y1="${T}" y2="${H - B}"/><text x="${xd + 6}" y="${T + 12}">November</text><text x="${xd - 6}" y="${T + 12}" text-anchor="end">Aug–Oct</text>`;
  }
  svg += `<polyline class="line" points="${run.map((v, i) => `${x(i)},${y(v)}`).join(" ")}"/>`;
  pts.forEach((p, i) => {
    svg += `<circle class="pt" cx="${x(i)}" cy="${y(run[i])}" r="5"/>
      <rect x="${x(i) - 14}" y="${T}" width="28" height="${H - T - B}" fill="transparent" data-i="${i}"/>
      <text x="${x(i)}" y="${H - B + 16}" text-anchor="middle">${p.date.slice(5)}</text>`;
  });
  svg += `<text x="${run.length ? x(run.length - 1) : 0}" y="${y(run[run.length - 1]) - 12}" text-anchor="end">${run[run.length - 1]}%</text></svg>`;
  html += `<div class="card">${svg}</div>
    <details style="margin-top:12px"><summary class="sub">Table view</summary>
    <table class="data"><thead><tr><th>Date</th><th>Invoice</th><th>Phase</th><th>Needed senior?</th><th>Memory-backed reasons</th><th>Running %</th></tr></thead>
    <tbody>${pts.map((p, i) => `<tr><td>${p.date}</td><td class="mono">${p.invoice_id}</td><td>${p.phase}</td><td>${p.needs_senior ? "yes" : "no"}</td><td>${p.memories_used}</td><td>${run[i]}%</td></tr>`).join("")}</tbody></table></details>`;
  $("#curve").innerHTML = html;

  const tip = document.createElement("div");
  tip.className = "tooltip"; tip.hidden = true; document.body.appendChild(tip);
  document.querySelectorAll(".strip rect[data-i]").forEach((r) => {
    r.onmouseenter = () => {
      const p = pts[+r.dataset.i];
      tip.innerHTML = `<b>${p.invoice_id}</b> · ${p.date}<br>${p.needs_senior ? "Escalated to senior" : "Resolved by Munshi"}<br>${p.memories_used} memory-backed reasons · running ${run[+r.dataset.i]}%`;
      tip.hidden = false;
    };
    r.onmousemove = (e) => { tip.style.left = e.clientX + 12 + "px"; tip.style.top = e.clientY + 12 + "px"; };
    r.onmouseleave = () => (tip.hidden = true);
  });
}

// ---------- explorer ----------
$("#explore-form").onsubmit = async (e) => {
  e.preventDefault();
  const q = $("#explore-q").value, v = $("#explore-vendor").value;
  $("#explore-results").innerHTML = `<span class="spinner"></span> Recalling…`;
  try {
    const r = await api(`/api/memory?q=${encodeURIComponent(q)}${v ? `&vendor_id=${v}` : ""}`);
    $("#explore-results").innerHTML = r.results.length ? r.results.map(memCard).join("") : '<div class="sub">No memories matched.</div>';
  } catch (err) {
    $("#explore-results").innerHTML = `<div class="guard">${esc(err.message)}</div>`;
  }
};

loadHealth();
loadBook().then(() => { if (location.hash.startsWith("#INV-")) openInvoice(location.hash.slice(1)); });
