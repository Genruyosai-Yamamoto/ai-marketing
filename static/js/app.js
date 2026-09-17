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

bootstrap();

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

// Dashboard load on page refresh while already signed in:
window.addEventListener("load", () => {
  if ($("view-dashboard").classList.contains("hidden") === false) {
    loadBusinesses();
  }
});