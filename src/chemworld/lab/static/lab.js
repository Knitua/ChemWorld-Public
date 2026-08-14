const lab = { tasks: [], session: null, affordance: null, selectionPending: false };
const $ = (selector) => document.querySelector(selector);
const fmt = (value, digits = 3) => value === null || value === undefined ? "—" : Number(value).toFixed(digits);
const esc = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");

document.addEventListener("DOMContentLoaded", async () => {
  wire();
  try {
    const payload = await api("/api/tasks");
    lab.tasks = payload.tasks;
    $("#taskSelect").innerHTML = lab.tasks.map((task) => `<option value="${esc(task.task_id)}">${esc(task.title)}</option>`).join("");
    $("#taskSelect").value = payload.default_task;
    previewTask(currentTask());
    updateSelectionState();
  } catch (error) {
    showValidation(false, error.message);
  }
});

function wire() {
  $("#taskSelect").addEventListener("change", handleSelectionChange);
  $("#seedInput").addEventListener("input", handleSelectionChange);
  $("#createSession").addEventListener("click", createSession);
  $("#operationSelect").addEventListener("change", renderOperationFields);
  $("#submitAction").addEventListener("click", submitAction);
  $("#downloadLog").addEventListener("click", downloadLog);
}

function handleSelectionChange() {
  previewTask(currentTask());
  updateSelectionState();
}

function currentTask() {
  return lab.tasks.find((task) => task.task_id === $("#taskSelect").value) || lab.tasks[0];
}

function previewTask(task) {
  if (!task) return;
  $("#missionMaturity").textContent = task.physics_maturity;
  $("#missionTitle").textContent = task.title;
  $("#missionBackground").textContent = task.background;
  $("#missionGoal").textContent = task.student_goal;
  $("#missionMetrics").textContent = task.success_metrics.join(" · ");
  if (!lab.session || task.task_id !== lab.session.task_id || selectedSeed() !== lab.session.seed) {
    previewApparatus(task);
  }
}

function selectedSeed() { return Number($("#seedInput").value || 0); }

function previewApparatus(task) {
  if (!task) return;
  $("#twinStage").dataset.apparatus = task.apparatus_family || "batch";
  $("#apparatusLabel").textContent = task.apparatus_label || "批式反应器";
}

function updateSelectionState() {
  const task = currentTask();
  const pending = Boolean(lab.session) && (
    task?.task_id !== lab.session.task_id || selectedSeed() !== lab.session.seed
  );
  lab.selectionPending = pending;
  const state = $("#selectionState");
  const message = state.querySelector("span");
  const overlay = $("#sessionPending");
  const composer = document.querySelector(".composer-panel");
  state.dataset.state = pending ? "pending" : lab.session ? "active" : "ready";
  message.textContent = pending
    ? `已选择 ${task.title}，尚未应用`
    : lab.session
      ? `当前运行：${task.title} · seed ${selectedSeed()}`
      : "选择任务后开始实验";
  overlay.hidden = !pending;
  $("#pendingTaskTitle").textContent = task?.title || "—";
  composer.dataset.pending = pending ? "true" : "false";
  $("#createSession").textContent = pending ? "应用并开始" : lab.session ? "重置当前实验" : "开始实验";
  if (pending) {
    $("#operationSelect").disabled = true;
    $("#submitAction").disabled = true;
  }
}

async function createSession() {
  const button = $("#createSession");
  button.disabled = true;
  try {
    const session = await api("/api/sessions", {
      method: "POST",
      body: { task_id: $("#taskSelect").value, seed: selectedSeed() },
    });
    renderSession(session);
    showValidation(true, "实验已创建。以下字段与范围来自当前运行时的公开动作合同。");
  } catch (error) {
    showValidation(false, error.message);
  } finally {
    button.disabled = false;
  }
}

async function submitAction() {
  if (!lab.session) return;
  const button = $("#submitAction");
  button.disabled = true;
  try {
    const result = await api(`/api/sessions/${encodeURIComponent(lab.session.session_id)}/actions`, {
      method: "POST", body: { action: buildAction() },
    });
    if (result.accepted) {
      showValidation(true, "动作通过验证并已原子执行。公开状态与资源记录已更新。");
    } else {
      showValidation(false, `${result.feedback.message}\n${result.feedback.recovery_suggestion || ""}`);
    }
    renderSession(result.state);
  } catch (error) {
    showValidation(false, error.message);
  } finally {
    if (!lab.session?.done) button.disabled = false;
  }
}

function renderSession(session) {
  lab.session = session;
  const task = lab.tasks.find((item) => item.task_id === session.task_id);
  const campaign = session.campaign_state;
  const history = session.history || [];
  const latest = history.at(-1);
  const visible = latest?.visible_metrics || session.lab_report?.visible_metrics || {};
  $("#taskSelect").value = session.task_id;
  $("#seedInput").value = session.seed;
  previewTask(task);
  lab.selectionPending = false;
  $("#sessionCode").textContent = session.session_id.slice(0, 8).toUpperCase();
  $("#sessionState").textContent = session.done ? "Episode completed" : `${task.title} · seed ${session.seed}`;
  $("#experimentBadge").textContent = `EXPERIMENT ${Number(campaign.experiment_index) + 1}`;
  $("#stepCount").textContent = `${campaign.operation_count} / ${campaign.budget}`;
  $("#remainingBudget").textContent = `${campaign.remaining_budget} remaining`;
  $("#progressBar").style.width = `${campaign.operation_count / Math.max(campaign.budget, 1) * 100}%`;
  $("#bestScore").textContent = fmt(campaign.best_score);
  $("#twinScore").textContent = fmt(campaign.best_score);
  $("#riskValue").textContent = fmt(visible.safety_risk);
  $("#costValue").textContent = fmt(visible.cost);
  $("#assayValue").textContent = campaign.final_assay_count ?? 0;
  $("#downloadLog").disabled = history.length === 0;
  renderTwin(latest, session.public_vessel, task);
  renderActions(session.available_actions, session.all_actions || session.available_actions, session.done);
  renderReport(session.lab_report, visible);
  renderHistory(history);
  updateSelectionState();
}

function renderTwin(latest, vessel, task) {
  const effect = latest?.state_effects || {};
  const operation = latest?.action?.operation || "idle";
  const stage = $("#twinStage");
  stage.dataset.visual = effect.visual || "idle";
  stage.dataset.apparatus = vessel?.apparatus_family || task?.apparatus_family || "batch";
  stage.dataset.phaseActive = String(Boolean(vessel?.phase_active));
  stage.dataset.solidActive = String(Boolean(vessel?.solid_active));
  stage.dataset.flowConfigured = String(Boolean(vessel?.flow_configured));
  stage.dataset.electrochemicalConfigured = String(Boolean(vessel?.electrochemical_configured));
  stage.dataset.distillationActive = String(Boolean(vessel?.distillation_active));
  $("#apparatusLabel").textContent = vessel?.apparatus_label || task?.apparatus_label || "批式反应器";
  $("#twinOperation").textContent = operation;
  $("#twinStatus").textContent = latest?.status || "Ready for setup";
  const netVolume = Number(vessel?.net_volume_delta_L || 0);
  const top = Math.max(20, Math.min(72, 64 - netVolume / 0.1 * 40));
  $("#liquid").style.inset = `${top}% 5px 5px`;
  $("#effectLabel").textContent = effect.label || "等待操作";
  $("#effectTitle").textContent = latest ? operation : "新鲜容器";
  $("#effectSummary").textContent = effect.summary || "执行公开动作后，状态变化会显示在这里。";
  $("#effectDeltas").innerHTML = latest ? [
    `Δt ${signed(effect.delta_time_s, "s", 0)}`,
    `ΔV ${signed(effect.delta_volume_L, "L", 4)}`,
    `Δrisk ${signed(effect.delta_risk, "", 3)}`,
  ].map((item) => `<span>${esc(item)}</span>`).join("") : "<span>Δt —</span><span>ΔV —</span><span>Δrisk —</span>";
}

function renderActions(actions, allActions, done) {
  const select = $("#operationSelect");
  select.innerHTML = actions.map((entry, index) => `<option value="${index}">${esc(entry.effect?.label || entry.operation)} · ${esc(entry.operation)}</option>`).join("");
  select.disabled = done || !actions.length;
  $("#submitAction").disabled = done || !actions.length;
  $("#validCount").textContent = `${actions.length} VALID`;
  lab.session.available_actions = actions;
  lab.session.all_actions = allActions;
  renderOperationRoadmap(allActions);
  renderOperationFields();
}

function renderOperationRoadmap(actions) {
  const roadmap = $("#operationRoadmap");
  roadmap.innerHTML = actions.map((entry) => {
    const available = entry.valid !== false;
    const reason = available
      ? (entry.effect?.summary || "当前状态可执行。")
      : [...new Set(entry.lock_reasons || ["等待前序实验条件满足。"])].join(" ");
    return `<button type="button" class="operation-step ${available ? "available" : "locked"}" data-roadmap-operation="${esc(entry.operation)}" ${available ? "" : "disabled"}><b>${available ? "✓" : "🔒"}</b><span><strong>${esc(entry.effect?.label || entry.operation)}</strong><code>${esc(entry.operation)}</code><small>${esc(reason)}</small></span></button>`;
  }).join("");
  roadmap.querySelectorAll("[data-roadmap-operation]:not(:disabled)").forEach((button) => {
    button.addEventListener("click", () => selectRoadmapOperation(button.dataset.roadmapOperation));
  });
}

function selectRoadmapOperation(operation) {
  const index = lab.session.available_actions.findIndex((entry) => entry.operation === operation);
  if (index < 0 || lab.selectionPending) return;
  $("#operationSelect").value = String(index);
  renderOperationFields();
  $("#operationSelect").focus();
}

function renderOperationFields() {
  if (!lab.session) return;
  lab.affordance = lab.session.available_actions[Number($("#operationSelect").value || 0)];
  const effect = lab.affordance?.effect;
  $("#composeEffectLabel").textContent = effect?.label || "操作效果";
  $("#composeEffectTitle").textContent = lab.affordance ? `${effect?.label || "操作"} · ${lab.affordance.operation}` : "暂无合法操作";
  $("#composeEffectSummary").textContent = effect?.summary || "当前状态没有可公开执行的动作。";
  $("#operationFields").innerHTML = (lab.affordance?.fields || []).map(fieldControl).join("");
  document.querySelectorAll("[data-action-field]").forEach((input) => input.addEventListener("input", updatePreview));
  updatePreview();
}

function fieldControl(field) {
  const choices = field.choices || field.allowed_values;
  const title = `${esc(field.field)}${field.required ? " *" : ""}`;
  if (Array.isArray(choices)) {
    const labels = field.choice_labels || {};
    return `<label>${title}<select data-action-field="${esc(field.field)}">${choices.map((choice) => `<option value="${esc(choice)}">${esc(labels[String(choice)] || choice)}</option>`).join("")}</select></label>`;
  }
  const bounds = field.recommended_range || field.bounds || {};
  const low = bounds.low ?? "", high = bounds.high ?? "";
  let initial = low !== "" && high !== "" ? (Number(low) + Number(high)) / 2 : "";
  if (low === 0 && field.lower_bound_inclusive === false && high !== "") initial = Number(high) / 2;
  return `<label>${title} ${esc(field.unit || "")}<input data-action-field="${esc(field.field)}" data-numeric="true" type="number" min="${esc(low)}" max="${esc(high)}" step="any" value="${esc(initial)}" ${field.required ? "required" : ""}></label>`;
}

function buildAction() {
  if (!lab.affordance) return {};
  const action = { operation: lab.affordance.operation };
  document.querySelectorAll("[data-action-field]").forEach((input) => {
    if (input.value === "") return;
    action[input.dataset.actionField] = input.dataset.numeric === "true" ? Number(input.value) : parseChoice(input.value);
  });
  return action;
}

function parseChoice(value) { return /^-?\d+(\.\d+)?$/.test(value) ? Number(value) : value; }
function updatePreview() { $("#actionPreview").textContent = JSON.stringify(buildAction(), null, 2); }

function showValidation(success, message) {
  const box = $("#validationBox");
  box.className = `validation ${success ? "success" : "error"}`;
  box.innerHTML = `<b>${success ? "✓" : "!"}</b><p>${esc(message).replaceAll("\n", "<br>")}</p>`;
}

function renderReport(report, visible) {
  $("#labFeedback").textContent = report?.text || "执行操作后，公开观测与恢复建议会显示在这里。";
  $("#reportInstrument").textContent = report?.instrument_summary?.instrument || "NO INSTRUMENT";
  const metrics = Object.entries(visible || {}).filter(([, value]) => Number.isFinite(Number(value))).slice(0, 9);
  $("#metricGrid").innerHTML = metrics.map(([key, value]) => `<article><span>${esc(key)}</span><strong>${fmt(value, 4)}</strong></article>`).join("");
}

function renderHistory(history) {
  $("#historyBody").innerHTML = history.length ? history.map((item) => {
    const effect = item.state_effects || {};
    const delta = `Δt ${signed(effect.delta_time_s, "s", 0)} · ΔV ${signed(effect.delta_volume_L, "L", 4)}`;
    const metrics = Object.entries(item.visible_metrics || {}).slice(0, 5).map(([key, value]) => `${key}=${fmt(value)}`).join(" · ");
    return `<tr><td>${item.step}</td><td><code>${esc(item.action.operation)}</code></td><td>${esc(effect.label || item.status)}<small>${esc(delta)}</small></td><td>${fmt(item.reward, 4)}</td><td>${esc(metrics)}</td></tr>`;
  }).join("") : '<tr><td colspan="5" class="empty">尚未开始实验</td></tr>';
}

function signed(value, unit = "", digits = 3) {
  const number = Number(value || 0), sign = number > 0 ? "+" : number < 0 ? "−" : "";
  return `${sign}${Math.abs(number).toFixed(digits)}${unit ? ` ${unit}` : ""}`;
}

function downloadLog() {
  if (!lab.session) return;
  const payload = { task_id: lab.session.task_id, seed: lab.session.seed, history: lab.session.history };
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url; link.download = `${lab.session.task_id}-student-lab.json`; link.click(); URL.revokeObjectURL(url);
}

async function api(url, options = {}) {
  const response = await fetch(url, { method: options.method || "GET", headers: { "Content-Type": "application/json" }, body: options.body === undefined ? undefined : JSON.stringify(options.body) });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}
