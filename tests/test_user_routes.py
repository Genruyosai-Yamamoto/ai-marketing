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
    assert "/api/business/<business_id>/opportunities/<opportunity_id>" in rules
    assert "/api/business/<business_id>/runs/latest" in rules
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


class SeedSnapshot:
    def __init__(self, data, doc_id):
        self.exists = data is not None
        self._data = dict(data) if data else {}
        self.id = doc_id

    def to_dict(self):
        return dict(self._data)


class SeedCollection:
    def __init__(self, db, path):
        self._db = db
        self.path = path

    def document(self, doc_id):
        return SeedRef(self._db, self.path + [doc_id])

    def stream(self):
        prefix = tuple(self.path)
        return [
            SeedSnapshot(data, path[-1])
            for path, data in self._db._seed.items()
            if len(path) == len(prefix) + 1 and path[: len(prefix)] == prefix
        ]


class SeedRef:
    def __init__(self, db, path):
        self._db = db
        self.path = path

    @property
    def id(self):
        return self.path[-1]

    def get(self):
        return SeedSnapshot(self._db._seed.get(tuple(self.path)), self.id)

    def collection(self, name):
        return SeedCollection(self._db, self.path + [name])


class SeedFakeDb:
    def __init__(self, seed):
        self._seed = {tuple(k): v for k, v in seed.items()}

    def collection(self, name):
        return SeedCollection(self, [name])


@pytest.fixture
def seeded(client, monkeypatch):
    import routes.user as routes_user

    seed = {
        ("businesses", "b1"): {
            "owner_id": "u1", "name": "A", "website_url": "https://a.example",
        },
        ("businesses", "b1", "opportunities", "opp1"): {
            "owner_id": "u1", "title": "Add SEO", "description": "d", "problem": "p",
            "evidence": ["e"], "potential_impact": "high", "confidence": 0.9,
            "type": "seo", "position": 0,
        },
        ("businesses", "b1", "agent_runs", "r1"): {
            "business_id": "b1", "owner_id": "u1", "type": "website_analysis",
            "status": "completed", "observation_id": "obs1",
            "opportunity_ids": ["opp1"],
            "created_at": "2026-09-16T00:00:00",
            "completed_at": "2026-09-16T00:00:01",
        },
        ("businesses", "b1", "agent_runs", "r2"): {
            "business_id": "b1", "owner_id": "u1", "type": "website_analysis",
            "status": "running",
            "created_at": "2026-09-16T01:00:00",
        },
    }
    monkeypatch.setattr(routes_user, "db", SeedFakeDb(seed))
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"
    return routes_user


def test_get_opportunity_returns_200_for_owner(client, seeded):
    resp = client.get("/api/business/b1/opportunities/opp1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["opportunity"]["id"] == "opp1"
    assert body["opportunity"]["title"] == "Add SEO"


def test_get_opportunity_403_for_non_owner(client, seeded, monkeypatch):
    import routes.user as routes_user

    seed = {
        ("businesses", "b2"): {"owner_id": "u2", "name": "B", "website_url": "https://b.example"},
        ("businesses", "b2", "opportunities", "opp1"): {"owner_id": "u2", "title": "T"},
    }
    monkeypatch.setattr(routes_user, "db", SeedFakeDb(seed))
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"
    resp = client.get("/api/business/b2/opportunities/opp1")
    assert resp.status_code == 403


def test_get_latest_run_returns_most_recent(client, seeded):
    resp = client.get("/api/business/b1/runs/latest")
    assert resp.status_code == 200
    run = resp.get_json()["run"]
    assert run["run_id"] == "r2"
    assert run["status"] == "running"
    assert run["observation_id"] is None
    assert run["opportunity_ids"] is None


def test_get_latest_run_none_when_no_runs(client, seeded, monkeypatch):
    import routes.user as routes_user

    seed = {
        ("businesses", "b1"): {"owner_id": "u1", "name": "A", "website_url": "https://a.example"},
    }
    monkeypatch.setattr(routes_user, "db", SeedFakeDb(seed))
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"
    resp = client.get("/api/business/b1/runs/latest")
    assert resp.status_code == 200
    assert resp.get_json()["run"] is None


def test_get_latest_run_404_missing_business(client, seeded):
    resp = client.get("/api/business/nope/runs/latest")
    assert resp.status_code == 404


def test_get_latest_run_403_non_owner(client, seeded, monkeypatch):
    import routes.user as routes_user

    seed = {
        ("businesses", "b2"): {"owner_id": "u2", "name": "B", "website_url": "https://b.example"},
    }
    monkeypatch.setattr(routes_user, "db", SeedFakeDb(seed))
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"
    resp = client.get("/api/business/b2/runs/latest")
    assert resp.status_code == 403


def test_get_latest_run_401_without_session(client, seeded):
    with client.session_transaction() as sess:
        sess.clear()
    resp = client.get("/api/business/b1/runs/latest")
    assert resp.status_code == 401


def test_get_latest_run_returns_full_run_from_completed(client, seeded, monkeypatch):
    import routes.user as routes_user

    seed = {
        ("businesses", "b1"): {"owner_id": "u1", "name": "A", "website_url": "https://a.example"},
        ("businesses", "b1", "agent_runs", "r1"): {
            "business_id": "b1", "owner_id": "u1", "type": "website_analysis",
            "status": "completed", "observation_id": "obs1", "opportunity_ids": ["opp1"],
            "created_at": "2026-09-16T00:00:00", "completed_at": "2026-09-16T00:00:01",
        },
    }
    monkeypatch.setattr(routes_user, "db", SeedFakeDb(seed))
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"
    resp = client.get("/api/business/b1/runs/latest")
    run = resp.get_json()["run"]
    assert run == {
        "run_id": "r1", "status": "completed", "observation_id": "obs1",
        "opportunity_ids": ["opp1"], "error": None,
        "created_at": "2026-09-16T00:00:00", "completed_at": "2026-09-16T00:00:01",
    }