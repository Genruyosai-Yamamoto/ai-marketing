import pytest


@pytest.fixture
def flask_app():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


class FakeQuery:
    def __init__(self, exists, data=None):
        self._exists = exists
        self._data = data or {}

    @property
    def exists(self):
        return self._exists

    def to_dict(self):
        return dict(self._data)


class FakeRef:
    def __init__(self, db, path):
        self._db = db
        self.path = list(path)
        self.id = self.path[-1]
        self.updates = []
        self.collections = {}

    def get(self):
        if self.id == "b1":
            return FakeQuery(
                True,
                {"owner_id": "u1", "name": "Test Biz", "website_url": "https://example.com"},
            )
        return FakeQuery(False)

    def collection(self, sub):
        if sub not in self.collections:
            self.collections[sub] = FakeCollection(self._db, self.path + [sub])
        return self.collections[sub]

    def set(self, data):
        self._set = data

    def update(self, data):
        self.updates.append(data)


class FakeCollection:
    def __init__(self, db, path):
        self._db = db
        self.path = list(path)
        self.docs = {}

    def document(self, doc_id=None):
        key = doc_id or "auto_run_id"
        path = self.path + [key]
        if key not in self.docs:
            self.docs[key] = FakeRef(self._db, path)
        return self.docs[key]


class FakeDb:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection(self, [name])
        return self.collections[name]


def test_app_boots_and_blueprints_register(flask_app):
    rules = {r.rule for r in flask_app.url_map.iter_rules()}
    assert "/api/business/<business_id>/analyze" in rules
    assert "/dashboard" in rules
    assert "/create-profile" in rules
    assert "/generate-logbook" in rules


def test_analyze_returns_503_and_fails_run_when_broker_down(monkeypatch, flask_app, client):
    import routes.user as routes_user

    def raise_broker(*args, **kwargs):
        raise RuntimeError("broker unreachable")

    monkeypatch.setattr(routes_user.analyze_business_website, "delay", raise_broker)
    monkeypatch.setattr(routes_user, "db", FakeDb())

    with client.session_transaction() as sess:
        sess["user_id"] = "u1"

    resp = client.post("/api/business/b1/analyze", json={})
    assert resp.status_code == 503
    assert resp.get_json()["success"] is False

    biz_ref = routes_user.db.collection("businesses").document("b1")
    run_ref = biz_ref.collection("agent_runs").document("auto_run_id")
    assert run_ref.updates, "run doc should have been updated"
    assert run_ref.updates[-1]["status"] == "failed"