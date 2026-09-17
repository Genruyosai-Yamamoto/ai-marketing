const state = { user: null };
let wasAuthed = false;

function $(id) {
  return document.getElementById(id);
}

function showView(name) {
  for (const view of document.querySelectorAll("section[data-view]")) {
    view.classList.add("hidden");
  }
  $("view-" + name).classList.remove("hidden");
}

function setNavForAuth(authed) {
  const nav = $("nav-auth");
  if (authed) {
    nav.classList.remove("hidden");
    nav.classList.add("flex");
  } else {
    nav.classList.add("hidden");
    nav.classList.remove("flex");
  }
}

function showToast(message, type = "error") {
  const colors = type === "success"
    ? "bg-emerald-600 text-white"
    : "bg-red-600 text-white";
  const el = document.createElement("div");
  el.className = "rounded-lg px-4 py-3 text-sm shadow-lg " + colors;
  el.textContent = message;
  $("toast-container").appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function showInline(el, message) {
  el.textContent = message;
  el.classList.remove("hidden");
}

function hideInline(el) {
  el.classList.add("hidden");
  el.textContent = "";
}

async function bootstrap() {
  try {
    const body = await apiFetch("/api/auth/me");
    state.user = body.user;
    wasAuthed = true;
    setNavForAuth(true);
    location.hash = "#dashboard";
    showView("dashboard");
  } catch (err) {
    setNavForAuth(false);
    location.hash = "#login";
    showView("login");
  }
}

async function handleLogin(event) {
  event.preventDefault();
  const submit = $("login-submit");
  const email = $("login-email").value.trim().toLowerCase();
  const password = $("login-password").value;
  hideInline($("login-error"));
  submit.disabled = true;
  submit.textContent = "Signing in…";

  try {
    const body = await apiFetch("/api/auth/login", {
      method: "POST",
      body: { email, password },
    });
    state.user = { id: body.user_id, email: body.email, role: body.role };
    wasAuthed = true;
    setNavForAuth(true);
    $("login-password").value = "";
    location.hash = "#dashboard";
    showView("dashboard");
    try {
      await loadBusinesses();
    } catch (loadErr) {
      showToast(loadErr.message || "Unable to load businesses.");
    }
  } catch (err) {
    // 401 on login is a plain credential error (AUTH_ROUTES suppress session-expired).
    showInline($("login-error"), err.message || "Unable to sign in.");
  } finally {
    submit.disabled = false;
    submit.textContent = "Sign in";
  }
}

async function handleRegister(event) {
  event.preventDefault();
  const submit = $("register-submit");
  const username = $("register-username").value.trim();
  const email = $("register-email").value.trim().toLowerCase();
  const password = $("register-password").value;
  const confirm = $("register-confirm").value;
  hideInline($("register-error"));

  if (password.length < 8) {
    showInline($("register-error"), "Password must be at least 8 characters.");
    return;
  }
  if (password !== confirm) {
    showInline($("register-error"), "Passwords do not match.");
    return;
  }
  submit.disabled = true;
  submit.textContent = "Creating account…";

  try {
    await apiFetch("/api/auth/register", {
      method: "POST",
      body: { username, email, password },
    });
    showToast("Account created. Please sign in.", "success");
    goToLogin(email);
  } catch (err) {
    showInline($("register-error"), err.message || "Unable to create account.");
  } finally {
    submit.disabled = false;
    submit.textContent = "Create account";
  }
}

async function handleLogout() {
  try {
    await apiFetch("/api/auth/logout", { method: "POST" });
  } catch (err) {
    // Even if the request fails, clear the client state and return to login.
  }
  state.user = null;
  wasAuthed = false;
  setNavForAuth(false);
  location.hash = "#login";
  showView("login");
}

function goToLogin(prefillEmail) {
  if (prefillEmail) {
    $("login-email").value = prefillEmail;
  }
  hideInline($("login-error"));
  location.hash = "#login";
  showView("login");
}

function goToRegister() {
  hideInline($("register-error"));
  location.hash = "#register";
  showView("register");
}

$("login-form").addEventListener("submit", handleLogin);
$("login-btn-register").addEventListener("click", goToRegister);
$("register-form").addEventListener("submit", handleRegister);
$("register-btn-login").addEventListener("click", () => goToLogin(null));
$("logout-btn").addEventListener("click", handleLogout);

document.addEventListener("session-expired", () => {
  if (wasAuthed) {
    showToast("Your session has expired. Please log in again.");
  }
  state.user = null;
  wasAuthed = false;
  setNavForAuth(false);
  location.hash = "#login";
  showView("login");
});

// ── Theme toggle ─────────────────────────────────────────────
const themeKey = "blom-theme";

function initTheme() {
  const saved = localStorage.getItem(themeKey);
  const prefersDark =
    window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const dark = saved ? saved === "dark" : prefersDark;
  document.documentElement.classList.toggle("dark", dark);
}

function toggleTheme() {
  const dark = document.documentElement.classList.toggle("dark");
  localStorage.setItem(themeKey, dark ? "dark" : "light");
}

initTheme();
$("theme-toggle").addEventListener("click", toggleTheme);

// ── Dashboard ──────────────────────────────────────────────

let editingBusinessId = null;
let deletingBusinessId = null;

function openModal(id) {
  $(id).classList.remove("hidden");
}

function closeModal(id) {
  $(id).classList.add("hidden");
}

function renderBusinessCards(businesses) {
  const grid = $("business-grid");
  const empty = $("dashboard-empty");
  grid.innerHTML = "";

  if (!businesses.length) {
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");

  for (const biz of businesses) {
    const card = document.createElement("div");
    card.className = "bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-5 cursor-pointer hover:border-indigo-400 dark:hover:border-indigo-500 transition-colors";
    card.addEventListener("click", () => {
      // openBusinessDetail is defined in Task 5; guard so this commit is safe standalone.
      if (typeof openBusinessDetail === "function") {
        openBusinessDetail(biz.id);
      }
    });

    const title = document.createElement("div");
    title.className = "flex items-start justify-between gap-2";

    const name = document.createElement("h3");
    name.className = "text-lg font-semibold";
    name.textContent = biz.name || "Untitled business";

    const industry = document.createElement("span");
    if (biz.industry) {
      industry.className = "text-xs font-medium rounded-full bg-indigo-50 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300 px-2 py-0.5";
      industry.textContent = biz.industry;
    } else {
      industry.hidden = true;
    }
    title.appendChild(name);
    title.appendChild(industry);

    const website = document.createElement("p");
    if (biz.website_url) {
      website.className = "text-sm text-indigo-600 dark:text-indigo-400 mt-1";
      website.textContent = biz.website_url;
    }

    const desc = document.createElement("p");
    if (biz.description) {
      desc.className = "text-sm text-gray-600 dark:text-gray-300 mt-2 line-clamp-2";
      desc.textContent = biz.description;
    }

    card.appendChild(title);
    if (biz.website_url) card.appendChild(website);
    if (biz.description) card.appendChild(desc);
    grid.appendChild(card);
  }
}

async function loadBusinesses() {
  const body = await apiFetch("/api/business");
  renderBusinessCards(body.businesses || []);
}

function openBusinessModal(business = null) {
  editingBusinessId = business ? business.id : null;
  $("business-modal-title").textContent = business ? "Edit business" : "New business";
  $("business-id").value = business ? business.id : "";
  $("business-field-name").value = business ? business.name || "" : "";
  $("business-field-website").value = business ? business.website_url || "" : "";
  $("business-field-industry").value = business ? business.industry || "" : "";
  $("business-field-description").value = business ? business.description || "" : "";
  hideInline($("business-form-error"));
  openModal("business-modal");
  $("business-field-name").focus();
}

async function handleBusinessSubmit(event) {
  event.preventDefault();
  const submit = $("business-submit");
  hideInline($("business-form-error"));

  const payload = {
    name: $("business-field-name").value.trim(),
    website_url: $("business-field-website").value.trim(),
    industry: $("business-field-industry").value.trim(),
    description: $("business-field-description").value.trim(),
  };

  if (!payload.name) {
    showInline($("business-form-error"), "Business name is required.");
    return;
  }

  submit.disabled = true;
  submit.textContent = "Saving…";

  try {
    if (editingBusinessId) {
      await apiFetch("/api/business/" + editingBusinessId, {
        method: "PATCH",
        body: payload,
      });
      showToast("Business updated.", "success");
    } else {
      await apiFetch("/api/business", {
        method: "POST",
        body: payload,
      });
      showToast("Business created.", "success");
    }
    closeModal("business-modal");
    await loadBusinesses();
  } catch (err) {
    showInline($("business-form-error"), err.message || "Unable to save business.");
  } finally {
    submit.disabled = false;
    submit.textContent = "Save";
  }
}

function openDeleteModal(businessId, name) {
  deletingBusinessId = businessId;
  $("delete-biz-name").textContent = name || "This business";
  openModal("delete-modal");
}

async function handleDeleteConfirm() {
  const confirm = $("delete-confirm");
  confirm.disabled = true;
  confirm.textContent = "Deleting…";

  try {
    await apiFetch("/api/business/" + deletingBusinessId, {
      method: "DELETE",
    });
    showToast("Business deleted.", "success");
    closeModal("delete-modal");
    await loadBusinesses();
  } catch (err) {
    showToast(err.message || "Unable to delete business.");
    closeModal("delete-modal");
  } finally {
    confirm.disabled = false;
    confirm.textContent = "Delete";
    deletingBusinessId = null;
  }
}

$("create-business-btn").addEventListener("click", () => openBusinessModal(null));
$("business-form").addEventListener("submit", handleBusinessSubmit);
$("delete-confirm").addEventListener("click", handleDeleteConfirm);

for (const el of document.querySelectorAll("[data-close]")) {
  el.addEventListener("click", () => closeModal(el.dataset.close));
}

// ── Business detail ─────────────────────────────────────────

let runPollTimer = null;
let currentBusiness = null;

function renderRunStatus(status, error) {
  const el = $("run-status");
  el.innerHTML = "";
  const pill = document.createElement("span");
  const label = status || "queued";
  const map = {
    "queued": "bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300",
    "running": "bg-blue-100 dark:bg-blue-950 text-blue-800 dark:text-blue-300",
    "completed": "bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300",
    "failed": "bg-red-100 dark:bg-red-950 text-red-800 dark:text-red-300",
  };
  pill.className = "inline-block text-sm font-medium rounded-full px-3 py-1 " + (map[label] || map.queued);
  pill.textContent = label;
  el.appendChild(pill);
  if (error) {
    const msg = document.createElement("p");
    msg.className = "mt-2 text-sm text-red-700 dark:text-red-400";
    msg.textContent = error;
    el.appendChild(msg);
  }
}

function renderOpportunities(list) {
  const container = $("opportunities-list");
  const empty = $("opportunities-empty");
  container.innerHTML = "";
  if (!list.length) {
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");
  for (const opp of list) {
    const box = document.createElement("div");
    box.className = "rounded-lg border border-gray-200 dark:border-gray-800 p-4";
    const title = document.createElement("h3");
    title.className = "font-semibold";
    title.textContent = opp.title || opp.headline || "Opportunity";
    const summary = document.createElement("p");
    summary.className = "text-sm text-gray-600 dark:text-gray-300 mt-1";
    summary.textContent = opp.summary || opp.description || "";
    box.appendChild(title);
    if (summary.textContent) box.appendChild(summary);
    container.appendChild(box);
  }
}

async function loadOpportunities() {
  const body = await apiFetch("/api/business/" + state.businessId + "/opportunities");
  renderOpportunities(body.opportunities || []);
}

function renderActions(list) {
  const container = $("actions-list");
  const empty = $("actions-empty");
  container.innerHTML = "";
  if (!list.length) {
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");
  for (const action of list) {
    const row = document.createElement("div");
    row.className = "rounded-lg border border-gray-200 dark:border-gray-800 p-4";

    const head = document.createElement("div");
    head.className = "flex flex-wrap items-center justify-between gap-2";

    const title = document.createElement("h3");
    title.className = "font-semibold";
    title.textContent = action.title || "Action";

    const pill = document.createElement("span");
    const statusMap = {
      "pending_approval": "bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300",
      "approved": "bg-blue-100 dark:bg-blue-950 text-blue-800 dark:text-blue-300",
      "rejected": "bg-gray-200 dark:bg-gray-800 text-gray-700 dark:text-gray-300",
      "executed": "bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300",
    };
    pill.className = "text-xs font-medium rounded-full px-2 py-0.5 " + (statusMap[action.status] || "bg-gray-200 dark:bg-gray-800 text-gray-700 dark:text-gray-300");
    pill.textContent = action.status || "unknown";

    head.appendChild(title);
    head.appendChild(pill);

    const desc = document.createElement("p");
    if (action.description) {
      desc.className = "text-sm text-gray-600 dark:text-gray-300 mt-1";
      desc.textContent = action.description;
    }

    const buttons = document.createElement("div");
    buttons.className = "flex gap-2 mt-3";
    if (action.status === "pending_approval") {
      const approve = document.createElement("button");
      approve.type = "button";
      approve.className = "rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold px-3 py-1.5 disabled:opacity-60";
      approve.textContent = "Approve";
      approve.addEventListener("click", () => approveAction(action.id));

      const reject = document.createElement("button");
      reject.type = "button";
      reject.className = "rounded-lg border border-gray-300 dark:border-gray-700 text-xs px-3 py-1.5 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-60";
      reject.textContent = "Reject";
      reject.addEventListener("click", () => rejectAction(action.id));

      buttons.appendChild(approve);
      buttons.appendChild(reject);
    }

    row.appendChild(head);
    if (action.description) row.appendChild(desc);
    if (buttons.children.length) row.appendChild(buttons);
    container.appendChild(row);
  }
}

async function loadActions() {
  const body = await apiFetch("/api/business/" + state.businessId + "/actions");
  renderActions(body.actions || []);
}

async function approveAction(actionId) {
  await apiFetch("/api/business/" + state.businessId + "/actions/" + actionId + "/approve", {
    method: "POST",
  });
  showToast("Action approved.", "success");
  await loadActions();
}

async function rejectAction(actionId) {
  await apiFetch("/api/business/" + state.businessId + "/actions/" + actionId + "/reject", {
    method: "POST",
  });
  showToast("Action rejected.", "success");
  await loadActions();
}

async function startAnalysis() {
  const btn = $("analyze-btn");
  btn.disabled = true;
  btn.textContent = "Analyzing…";
  try {
    await apiFetch("/api/business/" + state.businessId + "/analyze", {
      method: "POST",
    });
    showToast("Analysis started.", "success");
    pollRunStatus(true);
  } catch (err) {
    showToast(err.message || "Unable to start analysis.");
    btn.disabled = false;
    btn.textContent = "Analyze website";
  }
}

async function pollRunStatus(immediate) {
  if (!state.businessId) return;
  const run = async () => {
    try {
      const body = await apiFetch("/api/business/" + state.businessId + "/runs/latest");
      const run = body.run;
      if (!run) {
        renderRunStatus("queued", null);
        return;
      }
      const status = run.status;
      renderRunStatus(status, run.error);
      if (status === "completed" || status === "failed") {
        stopPolling();
        $("analyze-btn").disabled = false;
        $("analyze-btn").textContent = "Analyze website";
        if (status === "completed") {
          try {
            await loadOpportunities();
            await loadActions();
          } catch (err) {
            showToast(err.message || "Could not refresh results.");
          }
        }
        return;
      }
    } catch (err) {
      renderRunStatus("running", null);
    }
  };
  if (immediate) {
    await run();
  }
  if (runPollTimer) clearInterval(runPollTimer);
  runPollTimer = setInterval(run, 3000);
}

function stopPolling() {
  if (runPollTimer) {
    clearInterval(runPollTimer);
    runPollTimer = null;
  }
}

async function openBusinessDetail(businessId) {
  stopPolling();
  state.businessId = businessId;
  try {
    const body = await apiFetch("/api/business/" + businessId);
    currentBusiness = body.business;
    $("biz-name").textContent = currentBusiness.name || "Untitled business";
    $("biz-industry").textContent = currentBusiness.industry || "";
    const link = $("biz-website");
    if (currentBusiness.website_url) {
      link.href = currentBusiness.website_url;
      link.textContent = currentBusiness.website_url;
    } else {
      link.removeAttribute("href");
      link.textContent = "";
    }
    $("biz-description").textContent = currentBusiness.description || "";
    $("analyze-btn").disabled = false;
    $("analyze-btn").textContent = "Analyze website";
    showView("business");
    renderRunStatus("queued", null);
    await loadOpportunities();
    await loadActions();
    pollRunStatus(true);
  } catch (err) {
    showToast(err.message || "Unable to load business.");
    if (err.status === 404 || err.status === 403) {
      showView("dashboard");
      try {
        await loadBusinesses();
      } catch (loadErr) {
        showToast(loadErr.message || "Unable to load businesses.");
      }
    }
  }
}

$("back-to-dashboard").addEventListener("click", () => {
  stopPolling();
  state.businessId = null;
  showView("dashboard");
  loadBusinesses().catch((err) => showToast(err.message || "Unable to load businesses."));
});

$("analyze-btn").addEventListener("click", startAnalysis);
$("biz-edit-btn").addEventListener("click", () => openBusinessModal(currentBusiness));
$("biz-delete-btn").addEventListener("click", () => {
  openDeleteModal(currentBusiness.id, currentBusiness.name);
});

// Dashboard cards → detail (also used by Task 4's renderBusinessCards).
// Successfully restructured login wiring for clean dashboard load:
const _origBootstrap = bootstrap;
bootstrap = async function () {
  await _origBootstrap();
  if (state.user) {
    try {
      await loadBusinesses();
    } catch (err) {
      showToast(err.message || "Unable to load businesses.");
    }
  }
};
bootstrap();