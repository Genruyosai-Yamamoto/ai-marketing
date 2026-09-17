const AUTH_ROUTES = ["/api/auth/login", "/api/auth/register", "/api/auth/logout"];

async function apiFetch(path, options = {}) {
  const opts = {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
  };
  if (opts.body && typeof opts.body !== "string") {
    opts.body = JSON.stringify(opts.body);
  }

  let resp;
  try {
    resp = await fetch(path, opts);
  } catch (err) {
    throw { message: "Network error. Please try again.", status: 0 };
  }

  let body = null;
  try {
    body = await resp.json();
  } catch (err) {
    body = null;
  }

  if (!resp.ok) {
    if (resp.status === 401 && !AUTH_ROUTES.includes(path)) {
      document.dispatchEvent(new CustomEvent("session-expired"));
    }
    const message = (body && body.error) || "Request failed.";
    throw { message, status: resp.status };
  }
  return body;
}
