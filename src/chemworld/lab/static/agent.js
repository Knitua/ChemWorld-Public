const observer = { tasks: [], agents: [], run: null, selectedStep: null, poller: null, comparison: null, comparisonPoller: null };
const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
const fmt = (value, digits = 3) => value === null || value === undefined || Number.isNaN(Number(value)) ? "—" : Number(value).toFixed(digits);

document.addEventListener("DOMContentLoaded", boot);

async function boot() {
  wire();
  try {
    const [tasks, agents] = await Promise.all([api("/api/tasks"), api("/api/agents")]);
    observer.tasks = tasks.tasks;
    observer.agents = agents.agents;
    $("#agentTask").innerHTML = observer.tasks.map((task) => `<option value="${esc(task.task_id)}">${esc(task.title)}</option>`).join("");
    $("#agentTask").value = tasks.default_task;
    $("#agentSelect").innerHTML = observer.agents.map((agent) => `<option value="${esc(agent.agent_id)}">${esc(agent.title)}</option>`).join("");
    $("#agentSelect").value = agents.default_agent;
    $("#compareAgents").innerHTML = observer.agents.map((agent) => `<option value="${esc(agent.agent_id)}">${esc(agent.title)} · ${esc(agent.family)}</option>`).join("");
    [...$("#compareAgents").options].slice(0, 2).forEach((option) => option.selected = true);
    renderAgentCard();
    renderTaskPreview();
  } catch (error) {
    setStatus("failed", error.message);
  }
}

function wire() {
  $("#agentSelect").addEventListener("change", renderAgentCard);
  $("#agentTask").addEventListener("change", renderTaskPreview);
  $("#createRun").addEventListener("click", createRun);
  $("#stepRun").addEventListener("click", () => command("step"));
  $("#playRun").addEventListener("click", () => command("run"));
  $("#pauseRun").addEventListener("click", () => command("pause"));
  $("#downloadRun").addEventListener("click", downloadRun);
  $("#spectrumSelect").addEventListener("change", () => renderSpectrum(currentRecord()));
  $("#startComparison").addEventListener("click", startComparison);
}

function selectedAgent() { return observer.agents.find((agent) => agent.agent_id === $("#agentSelect").value); }
function currentRecord() { return observer.run?.records?.find((record) => record.step === observer.selectedStep) || observer.run?.records?.at(-1); }

function renderAgentCard() {
  const agent = selectedAgent();
  if (!agent) return;
  $("#agentCard").innerHTML = `<span>${esc(agent.family)}</span><strong>${esc(agent.title)}</strong><p>${esc(agent.summary)} · ${esc(agent.behavior)}</p>`;
}

function renderTaskPreview() {
  if (observer.run) return;
  const task = observer.tasks.find((item) => item.task_id === $("#agentTask").value);
  if (!task) return;
  $("#apparatusBadge").textContent = task.apparatus_label;
  $("#agentStage").dataset.apparatus = task.apparatus_family;
}

async function createRun() {
  clearInterval(observer.poller);
  try {
    observer.run = await api("/api/agent-runs", { method: "POST", body: { task_id: $("#agentTask").value, agent_id: $("#agentSelect").value, seed: Number($("#agentSeed").value || 0) } });
    observer.selectedStep = null;
    resetRecordView();
    renderRun();
    startPolling();
  } catch (error) { setStatus("failed", error.message); }
}

async function command(value) {
  if (!observer.run) return;
  try {
    observer.run = await api(`/api/agent-runs/${encodeURIComponent(observer.run.run_id)}/commands`, { method: "POST", body: { command: value } });
    observer.selectedStep = null;
    renderRun();
    startPolling();
  } catch (error) { setStatus("failed", error.message); }
}

function startPolling() {
  clearInterval(observer.poller);
  if (!observer.run || observer.run.status !== "running") return;
  observer.poller = window.setInterval(refreshRun, 240);
}

async function refreshRun() {
  if (!observer.run) return;
  try {
    const previousCount = observer.run.records?.length || 0;
    observer.run = await api(`/api/agent-runs/${encodeURIComponent(observer.run.run_id)}`);
    if (observer.selectedStep === null || observer.selectedStep === previousCount) observer.selectedStep = null;
    renderRun();
    if (observer.run.status !== "running") clearInterval(observer.poller);
  } catch (error) { clearInterval(observer.poller); setStatus("failed", error.message); }
}

function renderRun() {
  const run = observer.run;
  if (!run) return;
  setStatus(run.status, run.error);
  const terminal = ["completed", "failed", "cancelled"].includes(run.status);
  $("#stepRun").disabled = terminal || run.status === "running";
  $("#playRun").disabled = terminal || run.status === "running";
  $("#pauseRun").disabled = terminal || run.status !== "running";
  $("#downloadRun").disabled = !run.records.length;
  $("#runStep").textContent = `${run.step_count} / ${run.budget}`;
  $("#runScore").textContent = fmt(run.score);
  $("#runRisk").textContent = fmt(run.safety_risk);
  $("#runCost").textContent = fmt(run.cost);
  $("#runRuntime").textContent = `${fmt(run.runtime_s, 2)} s`;
  $("#apparatusBadge").textContent = run.apparatus.label;
  const stage = $("#agentStage");
  stage.dataset.apparatus = run.apparatus.family;
  stage.dataset.phaseActive = String(Boolean(run.apparatus.phase_active));
  stage.dataset.solidActive = String(Boolean(run.apparatus.solid_active));
  renderTimeline(run.records);
  const record = currentRecord();
  if (record) renderRecord(record);
}

function setStatus(status, error = null) {
  const badge = $("#runStatus");
  badge.dataset.status = status;
  badge.textContent = error ? `${status}: ${error}` : status.toUpperCase();
}

function resetRecordView() {
  $("#stageEvent").textContent = "WAITING FOR RUN";
  $("#stageOperation").textContent = "idle";
  $("#stageTransaction").textContent = "No transaction yet";
  $("#agentStage").dataset.visual = "idle";
  $("#decisionStage").textContent = "NO CONTEXT";
  $("#availableOps").innerHTML = "<i>尚未开始</i>";
  $("#selectedAction").textContent = "—";
  $("#selectedPayload").textContent = "{}";
  $("#decisionEvidence").innerHTML = evidenceRows({});
  $("#reasoningSummary").textContent = "当前策略尚未产生公开理由记录。";
  $("#memoryNote").textContent = "";
  $("#outcomeStatus").textContent = "NO EVENT";
  $("#outcomeText").textContent = "单步运行后显示公开实验反馈。";
  $("#visibleMetrics").innerHTML = "";
  renderResources({});
  renderSpectrum(null);
}

function renderRecord(record) {
  const action = record.action || {};
  const context = record.decision_context || {};
  const audit = record.decision_audit || {};
  const trace = record.agent_trace || {};
  $("#stageEvent").textContent = String(record.event_type || "event").replaceAll("_", " ").toUpperCase();
  $("#stageOperation").textContent = action.operation || "idle";
  $("#stageTransaction").textContent = record.transaction_status || "unknown transaction";
  $("#agentStage").dataset.visual = visualFor(action.operation);
  $("#decisionStage").textContent = String(context.decision_stage || "no context").replaceAll("_", " ");
  $("#availableOps").innerHTML = (context.available_operations || []).map((operation) => `<b>${esc(operation)}</b>`).join("") || "<i>没有公开可用操作</i>";
  $("#selectedAction").textContent = action.operation || "—";
  $("#selectedPayload").textContent = JSON.stringify(action, null, 2);
  $("#decisionEvidence").innerHTML = evidenceRows(audit);
  $("#reasoningSummary").textContent = trace.reasoning_summary || (audit.status === "provided" ? audit.expected_effect : "该策略没有声明公开推理摘要；这不影响动作和结果审计。");
  $("#memoryNote").textContent = trace.memory_note ? `Memory: ${trace.memory_note}` : trace.hypothesis_note ? `Hypothesis: ${trace.hypothesis_note}` : "";
  $("#outcomeStatus").textContent = record.status || record.transaction_status || "EVENT";
  $("#outcomeText").textContent = record.report_text || "此步骤没有额外报告文本。";
  $("#visibleMetrics").innerHTML = Object.entries(record.visible_metrics || {}).filter(([, value]) => Number.isFinite(Number(value))).slice(0, 9).map(([key, value]) => `<div><span>${esc(key)}</span><strong>${fmt(value, 4)}</strong></div>`).join("");
  renderResources(record.method_resources || {});
  renderSpectrum(record);
}

function evidenceRows(audit) {
  const rows = [
    ["Expected effect", audit.expected_effect || "未声明"],
    ["Diagnostic target", audit.diagnostic_target || "未声明"],
    ["Information gain", fmt(audit.expected_information_gain)],
    ["Adaptation source", audit.adaptation_source || "none"],
    ["Uncertainty", fmt(audit.uncertainty)],
  ];
  return rows.map(([key, value]) => `<div><dt>${esc(key)}</dt><dd>${esc(value)}</dd></div>`).join("");
}

function renderResources(resources) {
  const usage = resources.agent_usage || {};
  $("#decisionTime").textContent = resources.decision_wall_time_s === undefined ? "—" : `${fmt(resources.decision_wall_time_s, 4)} s`;
  $("#modelCalls").textContent = usage.model_call_count ?? 0;
  $("#tokenCount").textContent = Number(usage.input_token_count || 0) + Number(usage.output_token_count || 0);
  $("#accountingState").textContent = resources.accounting_complete === true ? "complete" : resources.accounting_complete === false ? "incomplete" : "—";
}

function renderTimeline(records) {
  $("#timeline").innerHTML = records.length ? records.map((record) => `<button type="button" class="timeline-step ${record.step === (observer.selectedStep || records.at(-1)?.step) ? "active" : ""}" data-step="${record.step}"><b>STEP ${String(record.step).padStart(2, "0")}</b><strong>${esc(record.action.operation)}</strong><small>${esc(record.transaction_status)} · r ${fmt(record.reward, 3)}</small></button>`).join("") : "<p>Agent 运行后，每个决策都会出现在这里。</p>";
  $("#timeline").querySelectorAll("[data-step]").forEach((button) => button.addEventListener("click", () => { observer.selectedStep = Number(button.dataset.step); $("#replayState").textContent = `REPLAY STEP ${observer.selectedStep}`; renderRun(); }));
  if (observer.selectedStep === null) $("#replayState").textContent = "FOLLOWING LIVE";
}

function renderSpectrum(record) {
  const charts = record?.spectra || [];
  const select = $("#spectrumSelect");
  const requested = Number(select.value || 0);
  select.innerHTML = charts.map((chart, index) => `<option value="${index}">${esc(chart.instrument || chart.kind || `signal ${index + 1}`)}</option>`).join("");
  select.disabled = !charts.length;
  if (!charts.length) {
    $("#spectrumPath").setAttribute("d", ""); $("#spectrumEmpty").hidden = false; $("#spectrumKind").textContent = "NO SIGNAL"; $("#spectrumAxes").textContent = "—"; return;
  }
  select.value = String(Math.min(requested, charts.length - 1));
  const chart = charts[Number(select.value)];
  $("#spectrumEmpty").hidden = true;
  $("#spectrumKind").textContent = String(chart.kind || "public signal").toUpperCase();
  $("#spectrumAxes").textContent = `${chart.x_label} · ${chart.y_label}`;
  $("#spectrumPath").setAttribute("d", chartPath(chart.x, chart.y));
}

function chartPath(x, y) {
  if (!x?.length || !y?.length) return "";
  const xMin = Math.min(...x), xMax = Math.max(...x), yMin = Math.min(...y), yMax = Math.max(...y);
  return x.map((value, index) => { const px = 30 + (Number(value) - xMin) / Math.max(xMax - xMin, 1e-12) * 740; const py = 235 - (Number(y[index]) - yMin) / Math.max(yMax - yMin, 1e-12) * 205; return `${index ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`; }).join(" ");
}

function visualFor(operation) {
  if (["add_solvent", "add_reagent", "add_catalyst"].includes(operation)) return "feed";
  if (["heat", "evaporate", "distill"].includes(operation)) return "heat";
  if (["wait", "mix", "run_flow"].includes(operation)) return "mix";
  if (["measure", "sample"].includes(operation)) return "measure";
  if (["add_phase", "add_extractant"].includes(operation)) return "phase";
  if (["separate_phase", "wash"].includes(operation)) return "separate";
  if (["seed_crystals", "cool_crystallize", "filter_crystals"].includes(operation)) return "crystallize";
  return operation || "idle";
}

function downloadRun() {
  if (!observer.run) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(observer.run, null, 2)], {type: "application/json"}));
  const link = document.createElement("a"); link.href = url; link.download = `${observer.run.task_id}-${observer.run.agent_id}-${observer.run.seed}.json`; link.click(); URL.revokeObjectURL(url);
}

async function startComparison() {
  const agentIds = [...$("#compareAgents").selectedOptions].map((option) => option.value);
  if (agentIds.length < 2 || agentIds.length > 4) { $("#comparisonResults").innerHTML = "<p>请选择 2–4 个策略。</p>"; return; }
  try {
    observer.comparison = await api("/api/agent-comparisons", {method: "POST", body: {task_id: $("#agentTask").value, agent_ids: agentIds, seed: Number($("#agentSeed").value || 0)}});
    renderComparison();
    clearInterval(observer.comparisonPoller); observer.comparisonPoller = window.setInterval(refreshComparison, 450);
  } catch (error) { $("#comparisonResults").innerHTML = `<p>${esc(error.message)}</p>`; }
}

async function refreshComparison() {
  if (!observer.comparison) return;
  observer.comparison = await api(`/api/agent-comparisons/${encodeURIComponent(observer.comparison.comparison_id)}`);
  renderComparison();
  if (["completed", "failed"].includes(observer.comparison.status)) clearInterval(observer.comparisonPoller);
}

function renderComparison() {
  $("#comparisonResults").innerHTML = observer.comparison.runs.map((run) => { const agent = observer.agents.find((item) => item.agent_id === run.agent_id); return `<article class="comparison-card"><span>${esc(run.status.toUpperCase())}</span><strong>${esc(agent?.title || run.agent_id)}</strong><dl><dt>Steps</dt><dd>${run.step_count}/${run.budget}</dd><dt>Score</dt><dd>${fmt(run.score)}</dd><dt>Risk</dt><dd>${fmt(run.safety_risk)}</dd><dt>Cost</dt><dd>${fmt(run.cost)}</dd><dt>Runtime</dt><dd>${fmt(run.runtime_s, 2)} s</dd></dl></article>`; }).join("");
}

async function api(url, options = {}) {
  const response = await fetch(url, {method: options.method || "GET", headers: {"Content-Type": "application/json"}, body: options.body === undefined ? undefined : JSON.stringify(options.body)});
  const payload = await response.json(); if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`); return payload;
}
