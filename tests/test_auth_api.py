import types

import pytest
from firebase_admin.auth import UserNotFoundError
from werkzeug.security import check_password_hash, generate_password_hash


@pytest.fixture
def flask_app():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture(autouse=True)
def clean_auth_state(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6399/15")
    import routes.auth as routes_auth
    routes_auth.login_attempts.clear()
    routes_auth.locked_ips.clear()
    routes_auth.registration_log.clear()


class AuthSnapshot:
    def __init__(self, data, doc_id):
        self.exists = data is not None
        self._data = dict(data) if data else {}
        self.id = doc_id

    def to_dict(self):
        return dict(self._data)


class AuthQuery:
    def __init__(self, snapshots):
        self._snapshots = list(snapshots)

    def limit(self, n):
        return AuthQuery(self._snapshots[:n])

    def stream(self):
        return iter(self._snapshots)

    def get(self):
        return list(self._snapshots)


class AuthRef:
    def __init__(self, db, path):
        self._db = db
        self.path = tuple(path)
        self.id = self.path[-1]
        self.updates = []

    @property
    def data(self):
        state = dict(self._db._store.get(self.path) or {})
        for item in self.updates:
            state.update(item)
        return state

    def get(self):
        return AuthSnapshot(self._db._store.get(self.path), self.id)

    def set(self, data):
        self._db._store[self.path] = dict(data)

    def update(self, data):
        self.updates.append(dict(data))
        self._db._store[self.path] = dict(self.data)


class AuthCollection:
    def __init__(self, db, path):
        self._db = db
        self.path = tuple(path)

    def document(self, doc_id=None):
        if doc_id is None:
            doc_id = f"auto-{len(self)}"
        return AuthRef(self._db, self.path + (doc_id,))

    def where(self, *args, **kwargs):
        filt = kwargs.get("filter")
        if filt is not None:
            field, op, value = filt.field_path, filt.op_string, filt.value
        else:
            field, op, value = args[:3]
        found = []
        for path, data in self._db._store.items():
            if len(path) == len(self.path) + 1 and path[: len(self.path)] == self.path:
                if op == "==" and data.get(field) == value:
                    found.append(AuthSnapshot(data, path[-1]))
        return AuthQuery(found)

    def __len__(self):
        return sum(
            1 for path in self._db._store
            if len(path) == len(self.path) + 1 and path[: len(self.path)] == self.path
        )

    def stream(self):
        return iter([
            AuthSnapshot(data, path[-1])
            for path, data in self._db._store.items()
            if len(path) == len(self.path) + 1 and path[: len(self.path)] == self.path
        ])


class AuthDb:
    def __init__(self):
        self._store = {}

    def collection(self, name):
        return AuthCollection(self, (name,))


@pytest.fixture
def fake_firebase(monkeypatch):
    import routes.auth as routes_auth
    import routes.auth_api as auth_api

    db = AuthDb()
    monkeypatch.setattr(routes_auth, "db", db)
    monkeypatch.setattr(auth_api, "db", db)

    def raise_not_found(email):
        raise UserNotFoundError(email)

    monkeypatch.setattr(routes_auth.admin_auth, "get_user_by_email", raise_not_found)
    monkeypatch.setattr(
        routes_auth.admin_auth,
        "create_user",
        lambda **kwargs: types.SimpleNamespace(uid="firebase-uid-1"),
    )
    return db, routes_auth, auth_api


def seed_users(db, rows):
    users = db.collection("users")
    for uid, data in rows.items():
        users.document(uid).set(data)


def post_json(client, path, body, ip):
    return client.post(path, json=body, headers={"X-Forwarded-For": ip})


def test_register_blueprint_registered(flask_app):
    rules = {r.rule for r in flask_app.url_map.iter_rules()}
    assert "/api/auth/register" in rules


def test_register_creates_user(fake_firebase, client):
    db, routes_auth, auth_api = fake_firebase

    resp = post_json(client, "/api/auth/register", {
        "username": "Alice",
        "email": "Alice@Example.com",
        "password": "password123",
    }, "10.0.0.1")

    assert resp.status_code == 201
    body = resp.get_json()
    assert body["success"] is True
    assert body["user_id"] == "firebase-uid-1"

    ref = db.collection("users").document("firebase-uid-1")
    assert ref.data["email"] == "alice@example.com"
    assert ref.data["username"] == "Alice"
    assert ref.data["role"] == "user"
    assert ref.data["status"] == "Active"
    assert ref.data["password_hash"] != "password123"
    assert check_password_hash(ref.data["password_hash"], "password123") is True


def test_register_missing_fields(fake_firebase, client):
    for body in ({}, {"username": "A", "password": "password123"}, {"username": "A", "email": "a@b.co"}):
        resp = post_json(client, "/api/auth/register", body, "10.0.0.2")
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "All fields are required."


def test_register_short_password(fake_firebase, client):
    resp = post_json(client, "/api/auth/register", {
        "username": "Bob",
        "email": "bob@example.com",
        "password": "123",
    }, "10.0.0.3")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Password must be at least 8 characters."


def test_register_duplicate_email(fake_firebase, client):
    db, routes_auth, auth_api = fake_firebase
    seed_users(db, {"u-used": {"email": "used@example.com", "username": "Used"}})

    resp = post_json(client, "/api/auth/register", {
        "username": "Dup",
        "email": "used@example.com",
        "password": "password123",
    }, "10.0.0.4")

    assert resp.status_code == 409
    assert resp.get_json()["error"] == "Email already registered. Please login or use another email."
    assert "firebase-uid-1" not in db._store


def test_register_rate_limit(fake_firebase, client):
    ip = "10.0.0.9"
    for i in range(3):
        resp = post_json(client, "/api/auth/register", {
            "username": f"R{i}", "email": f"r{i}@example.com", "password": "password123",
        }, ip)
        assert resp.status_code == 201
    resp = post_json(client, "/api/auth/register", {
        "username": "R4", "email": "r4@example.com", "password": "password123",
    }, ip)
    assert resp.status_code == 429
    assert resp.get_json()["error"] == "Too many registrations from this IP. Try again later."


def test_register_500_on_unexpected_error(fake_firebase, client, monkeypatch):
    db, routes_auth, auth_api = fake_firebase

    def boom(email, password, user_data):
        raise RuntimeError("firebase down")

    monkeypatch.setattr(routes_auth, "create_firebase_user_and_firestore", boom)

    resp = post_json(client, "/api/auth/register", {
        "username": "C",
        "email": "c@example.com",
        "password": "password123",
    }, "10.0.0.5")

    assert resp.status_code == 500
    assert resp.get_json()["success"] is False