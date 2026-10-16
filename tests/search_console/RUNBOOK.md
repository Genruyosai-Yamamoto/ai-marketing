# Google Search Console — Manual E2E Runbook

Run this after the automated suite passes. You need real Google credentials
and a Firestore business document. Steps marked **[AGENT]** are run for you;
steps marked **[YOU]** require you to act in the browser or confirm output.

---

## Pre-conditions

| Requirement | Check |
|---|---|
| Flask server running | `python app.py` in the backend directory |
| `.env` has `GOOGLE_SEARCH_CONSOLE_CLIENT_ID`, `GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET`, `GOOGLE_SEARCH_CONSOLE_REDIRECT_URI` | `grep GOOGLE_SEARCH_CONSOLE .env` |
| A registered test user and a `business_id` | Note them down — you'll need both |
| curl with a cookie jar | `curl --version` |

Set these shell variables once before running any command:

```bash
BASE=http://localhost:5000
COOKIE_JAR=/tmp/gsc-test-cookies.txt
BUSINESS_ID=<your business_id here>
```

---

## Step 1 — Authenticate [AGENT]

```bash
curl -s -c "$COOKIE_JAR" -X POST "$BASE/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"<your email>","password":"<your password>"}' | python3 -m json.tool
```

✅ Expected: `"success": true` and a session cookie written to `$COOKIE_JAR`.

---

## Step 2 — Initiate OAuth [AGENT]

```bash
curl -s -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
  "$BASE/api/connections/search-console/connect?business_id=$BUSINESS_ID" \
  | python3 -m json.tool
```

✅ Expected: `"success": true` + an `authorization_url` field.  
Copy the `authorization_url` value — you need it in Step 3.

---

## Step 3 — Approve OAuth in Browser [YOU]

Open the `authorization_url` in your browser. Sign in with the Google account
that owns the Search Console properties you want to test. Click **Allow**.

Google will redirect to:
`http://localhost:5000/api/connections/search-console/callback?code=...&state=...`

✅ Expected: The browser shows `"success": true` with a `connection` object
containing `id`, `provider: "google_search_console"`, and `status: "connected"`.

If you see `"Missing OAuth code verifier"`, restart from Step 1 — the session
cookie may have expired.

---

## Step 4 — List Properties [AGENT]

```bash
curl -s -b "$COOKIE_JAR" \
  "$BASE/api/connections/search-console/properties?business_id=$BUSINESS_ID" \
  | python3 -m json.tool
```

✅ Expected: `"success": true` + a `properties` array listing your verified
Search Console sites. Note one `site_url` — you need it in Steps 5 and 6.

---

## Step 5 — Select a Property [AGENT]

Replace `<site_url>` with a value from Step 4's output:

```bash
curl -s -b "$COOKIE_JAR" -X POST "$BASE/api/connections/search-console/select-property" \
  -H "Content-Type: application/json" \
  -d "{\"business_id\":\"$BUSINESS_ID\",\"site_url\":\"<site_url>\"}" \
  | python3 -m json.tool
```

✅ Expected: `"success": true` + `"site_url"` echoed back.

---

## Step 6 — Fetch Analytics [AGENT]

```bash
curl -s -b "$COOKIE_JAR" \
  "$BASE/api/connections/search-console/analytics?business_id=$BUSINESS_ID" \
  | python3 -m json.tool
```

✅ Expected: `"success": true` + `top_queries`, `top_pages`, `totals`,
`start_date`, and `end_date`. Values may be zeroed if the property has no
recent traffic or data is still delayed (GSC delays ~3 days).

---

## Step 7 — Add a Property [AGENT]

Test adding a domain property (this does NOT require ownership; verification
is separate in Google):

```bash
curl -s -b "$COOKIE_JAR" -X POST "$BASE/api/connections/search-console/add-property" \
  -H "Content-Type: application/json" \
  -d "{\"business_id\":\"$BUSINESS_ID\",\"site_url\":\"sc-domain:<yourdomain.com>\"}" \
  | python3 -m json.tool
```

✅ Expected: `201` + `"verification_status": "verification_required"`, or `200`
+ `"already available"` if the domain is already in your account.

---

## Manual Failure Scenarios [YOU + AGENT]

### A — Reconnect without revoking (no new refresh token)

1. Repeat Steps 2–3 **without** first revoking access in
   [Google Account Permissions](https://myaccount.google.com/permissions).
2. `[AGENT]` Run Step 4 (list properties).
3. ✅ Expected: Still returns 200 — the stored refresh token was reused.

### B — Select a property not in the Google account

```bash
curl -s -b "$COOKIE_JAR" -X POST "$BASE/api/connections/search-console/select-property" \
  -H "Content-Type: application/json" \
  -d '{"business_id":"'"$BUSINESS_ID"'","site_url":"https://not-your-site.example.com/"}' \
  | python3 -m json.tool
```

✅ Expected: `403` + `"This property is not accessible to the connected Google account"`.

### C — Fetch analytics before selecting a property

1. In Firestore, clear the `site_id` field on the connection document, or use
   a fresh business_id that has a connection but no property selected yet.
2. `[AGENT]` Run Step 6.
3. ✅ Expected: `400` + `"No Search Console property selected"`.

---

## Sign-off

| Step | Result | Notes |
|---|---|---|
| 1 — Auth | ☐ Pass / ☐ Fail | |
| 2 — Initiate OAuth | ☐ Pass / ☐ Fail | |
| 3 — Browser approval | ☐ Pass / ☐ Fail | |
| 4 — List properties | ☐ Pass / ☐ Fail | |
| 5 — Select property | ☐ Pass / ☐ Fail | |
| 6 — Analytics | ☐ Pass / ☐ Fail | |
| 7 — Add property | ☐ Pass / ☐ Fail | |
| A — Reconnect fallback | ☐ Pass / ☐ Fail | |
| B — Unowned property 403 | ☐ Pass / ☐ Fail | |
| C — No property selected 400 | ☐ Pass / ☐ Fail | |
