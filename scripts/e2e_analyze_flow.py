import os
import secrets
import sys
import time

import requests
from flask.sessions import SecureCookieSessionInterface

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.environ.get("E2E_BASE", "http://127.0.0.1:5000")


def _csrf(session_cookie):
    from app import app as flask_app
    serializer = SecureCookieSessionInterface().get_signing_serializer(flask_app)
    data = serializer.loads(session_cookie)
    return data.get("_login_csrf")


def register_and_login(rand):
    s = requests.Session()
    email = f"e2e-{rand}@blom.test"
    pw = secrets.token_urlsafe(12)
    # Random per-phase source IP keeps repeated E2E runs clear of the
    # per-IP registration/login rate limits.
    fake_ip = f"198.51.100.{int(rand, 16) % 240 + 1}"
    headers = {"X-Forwarded-For": fake_ip}

    r = s.get(f"{BASE}/login")
    assert r.status_code == 200, r.text
    csrf = _csrf(s.cookies.get("session"))

    r = s.post(
        f"{BASE}/register",
        data={"username": f"e2euser-{rand}", "email": email, "password": pw, "confirm_password": pw},
        headers=headers,
        allow_redirects=False,
    )
    assert r.status_code == 302, r.text

    r = s.post(
        f"{BASE}/login",
        data={"email": email, "password": pw, "device_id": "e2e-device", "login_token": csrf},
        headers=headers,
        allow_redirects=False,
    )
    assert r.status_code == 302, r.text
    return s, email


def create_business(s, name, url):
    r = s.post(f"{BASE}/api/business", json={"name": name, "website_url": url})
    assert r.status_code == 201, r.text
    return r.json()["business"]["id"]


def trigger_analyze(s, biz_id):
    r = s.post(f"{BASE}/api/business/{biz_id}/analyze", json={})
    assert r.status_code == 202, r.text
    return r.json()["run_id"], r.json()["task_id"]


def poll_run(biz_id, run_id, timeout=120):
    from firebase import db
    run_ref = db.collection("businesses").document(biz_id).collection("agent_runs").document(run_id)
    deadline = time.time() + timeout
    doc = None
    while time.time() < deadline:
        doc = run_ref.get()
        if not doc.exists:
            time.sleep(1)
            continue
        data = doc.to_dict()
        if data.get("status") in ("completed", "failed"):
            return data
        time.sleep(1)
    return doc.to_dict() if doc else {}


def run_happy(rand):
    s, email = register_and_login(rand)
    biz_id = create_business(s, "E2E Happy Business", "https://example.com")
    run_id, task_id = trigger_analyze(s, biz_id)
    print(f"[happy] biz={biz_id} run={run_id} task={task_id}")
    data = poll_run(biz_id, run_id)
    assert data.get("status") == "completed", f"expected completed, got {data}"
    obs_id = data.get("observation_id")
    assert obs_id, "run missing observation_id"
    from firebase import db
    obs = db.collection("businesses").document(biz_id).collection("observations").document(obs_id).get()
    assert obs.exists, "observation doc missing"
    analysis = obs.to_dict().get("analysis") or {}
    assert analysis.get("title") or analysis.get("headings"), "analysis empty"
    print(f"[happy] PASS observation={obs_id} status=completed title={analysis.get('title')!r}")
    return email, [biz_id]


def run_failure(rand):
    s, email = register_and_login(rand)
    biz_id = create_business(s, "E2E Failure Business", f"https://does-not-exist-{rand}.invalid")
    run_id, task_id = trigger_analyze(s, biz_id)
    print(f"[fail] biz={biz_id} run={run_id} task={task_id}")
    data = poll_run(biz_id, run_id)
    assert data.get("status") == "failed", f"expected failed, got {data}"
    assert data.get("error"), "failed run missing error field"
    print(f"[fail] PASS run failed with error={data['error']!r}")
    return email, [biz_id]


def cleanup(emails, biz_ids):
    from firebase import db
    from firebase_admin import auth as admin_auth
    for biz_id in biz_ids:
        ref = db.collection("businesses").document(biz_id)
        for sub in ("observations", "agent_runs"):
            for doc in ref.collection(sub).stream():
                doc.reference.delete()
        ref.delete()
        print(f"[cleanup] deleted business {biz_id}")
    for email in emails:
        q = db.collection("users").where("email", "==", email).limit(1).get()
        if q:
            uid = q[0].id
            db.collection("users").document(uid).delete()
            try:
                admin_auth.delete_user(uid)
            except Exception as exc:
                print(f"[cleanup] auth delete failed for {uid}: {exc}")
            print(f"[cleanup] deleted user {uid}")


def main():
    emails, biz_ids = [], []
    for fn in ("run_happy", "run_failure"):
        try:
            email, ids = getattr(sys.modules[__name__], fn)(secrets.token_hex(4))
            emails.append(email)
            biz_ids.extend(ids)
        except AssertionError as exc:
            print(f"[FAIL] {fn}: {exc}")
            cleanup(emails, biz_ids)
            sys.exit(1)
    cleanup(emails, biz_ids)
    print("E2E PASS")


if __name__ == "__main__":
    main()