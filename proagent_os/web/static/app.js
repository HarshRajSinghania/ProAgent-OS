const $ = (id) => document.getElementById(id);

function getKey() {
  return localStorage.getItem("proagent_api_key") || "";
}
function saveKey() {
  localStorage.setItem("proagent_api_key", $("apiKey").value.trim());
  alert("API key saved locally.");
}
window.addEventListener("DOMContentLoaded", () => {
  $("apiKey").value = getKey();
});

async function api(path, opts = {}) {
  const headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  const key = getKey();
  if (key) headers["Authorization"] = `Bearer ${key}`;
  const res = await fetch(`/api/v1${path}`, { ...opts, headers });
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { data = { raw: text }; }
  if (!res.ok) throw new Error(data.detail || data.raw || res.statusText);
  return data;
}

function showTab(name) {
  document.querySelectorAll("[id^=tab-]").forEach((el) => el.classList.add("hidden"));
  $(`tab-${name}`).classList.remove("hidden");
  document.querySelectorAll("nav.sidebar button").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === name);
  });
}

function appendMsg(role, content) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = content;
  $("chatLog").appendChild(div);
  $("chatLog").scrollTop = $("chatLog").scrollHeight;
}

async function runTask() {
  const input = $("taskInput").value.trim();
  if (!input) return;
  $("taskStatus").textContent = "Running…";
  appendMsg("user", input);
  try {
    const data = await api("/tasks", { method: "POST", body: JSON.stringify({ input }) });
    appendMsg("assistant", data.result || "(empty)");
    $("taskTrace").textContent = JSON.stringify({ task_id: data.task_id, plan: data.plan, trace: data.trace }, null, 2);
    $("taskStatus").textContent = `Done (${data.task_id})`;
  } catch (e) {
    $("taskStatus").textContent = e.message;
  }
}

async function ingestUrl() {
  try {
    const data = await api("/kb/ingest/url", { method: "POST", body: JSON.stringify({ url: $("kbUrl").value }) });
    $("kbOut").textContent = JSON.stringify(data, null, 2);
  } catch (e) { $("kbOut").textContent = e.message; }
}

async function ingestFile() {
  const f = $("kbFile").files[0];
  if (!f) return alert("Choose a file");
  const fd = new FormData();
  fd.append("file", f);
  try {
    const res = await fetch("/api/v1/kb/ingest/file", {
      method: "POST",
      headers: { Authorization: `Bearer ${getKey()}` },
      body: fd,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "upload failed");
    $("kbOut").textContent = JSON.stringify(data, null, 2);
  } catch (e) { $("kbOut").textContent = e.message; }
}

async function searchKb() {
  try {
    const data = await api("/kb/search", { method: "POST", body: JSON.stringify({ query: $("kbQuery").value, top_k: 5 }) });
    $("kbOut").textContent = JSON.stringify(data, null, 2);
  } catch (e) { $("kbOut").textContent = e.message; }
}

async function listDocs() {
  try {
    const data = await api("/kb/documents");
    $("kbOut").textContent = JSON.stringify(data, null, 2);
  } catch (e) { $("kbOut").textContent = e.message; }
}

async function loadRecs() {
  try {
    const data = await api("/recommendations");
    const root = $("recList");
    root.innerHTML = "";
    if (!data.length) { root.innerHTML = '<div class="muted">No recommendations yet.</div>'; return; }
    data.forEach((r) => {
      const el = document.createElement("div");
      el.className = "card";
      const actions = [];
      if (r.status === "pending") {
        actions.push(`<button class="btn ok" onclick="decideRec('${r.id}','approved')">Approve</button>`);
        actions.push(`<button class="btn danger" onclick="decideRec('${r.id}','rejected')">Reject</button>`);
      } else if (r.status === "approved") {
        actions.push(`<button class="btn secondary" onclick="decideRec('${r.id}','executed')">Mark executed</button>`);
      }
      const actionRow = actions.length ? `<div class="row">${actions.join("")}</div>` : "";
      const hint = r.status === "approved"
        ? `<div class="muted">Approved. Execution has not completed.</div>`
        : "";
      el.innerHTML = `<div class="row" style="justify-content:space-between">
        <strong>${escapeHtml(r.title)}</strong>
        <span class="status ${r.status}">${r.status}</span>
      </div>
      <div class="muted" style="margin:.4rem 0">${escapeHtml(r.rationale || "")}</div>
      ${hint}
      ${actionRow}`;
      root.appendChild(el);
    });
  } catch (e) { $("recList").textContent = e.message; }
}

async function decideRec(id, status) {
  try {
    const data = await api(`/recommendations/${id}/decide`, { method: "POST", body: JSON.stringify({ status }) });
    if (data.execution && data.execution.ok === false) {
      alert(data.execution.error || "Execution failed");
    }
    loadRecs();
  } catch (e) { alert(e.message); }
}

async function loadSkills() {
  try {
    const data = await api("/skills");
    $("skillList").innerHTML = data.map((s) =>
      `<div class="card"><strong>${escapeHtml(s.name)}</strong> <span class="muted">(${escapeHtml(s.id)})</span>
       <div class="muted">${escapeHtml(s.description)}</div>
       <div class="muted">runner: ${s.has_runner}</div></div>`
    ).join("") || '<div class="muted">No skills loaded</div>';
  } catch (e) { $("skillList").textContent = e.message; }
}

async function createMonitor() {
  try {
    const config = JSON.parse($("monConfig").value || "{}");
    const data = await api("/monitors", {
      method: "POST",
      body: JSON.stringify({ name: $("monName").value, kind: $("monKind").value, config, interval_seconds: 60 }),
    });
    await api(`/monitors/${data.id}/run`, { method: "POST" });
    loadMonitors();
    alert("Monitor created and run once.");
  } catch (e) { alert(e.message); }
}

async function loadMonitors() {
  try {
    const data = await api("/monitors");
    $("monList").innerHTML = data.map((m) =>
      `<div class="card"><strong>${escapeHtml(m.name)}</strong> · ${escapeHtml(m.kind)}
       <div class="muted">id=${m.id} enabled=${m.enabled} last=${m.last_run_at || "never"}</div>
       <button class="btn secondary" onclick="runMon('${m.id}')">Run now</button></div>`
    ).join("") || '<div class="muted">No monitors</div>';
  } catch (e) { $("monList").textContent = e.message; }
}

async function runMon(id) {
  try { await api(`/monitors/${id}/run`, { method: "POST" }); loadMonitors(); loadRecs(); }
  catch (e) { alert(e.message); }
}

async function loadDash() {
  try {
    const data = await api("/dashboard");
    $("dashOut").textContent = JSON.stringify(data, null, 2);
  } catch (e) { $("dashOut").textContent = e.message; }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;" }[c]));
}
