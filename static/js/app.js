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