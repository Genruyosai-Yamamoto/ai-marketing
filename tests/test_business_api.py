import pytest


@pytest.fixture
def flask_app():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


class BizSnapshot:
    def __init__(self, data, doc_id):
        self.exists = data is not None
        self._data = dict(data) if data else {}
        self.id = doc_id

    def to_dict(self):
        return dict(self._data)


class BizQuery:
    def __init__(self, snapshots):
        self._snapshots = list(snapshots)

    def stream(self):
        return iter(self._snapshots)


class BizRef:
    def __init__(self, db, path):
        self._db = db
        self.path = tuple(path)
        self.id = self.path[-1]

    def get(self):
        return BizSnapshot(self._db._store.get(self.path), self.id)

    def set(self, data):
        self._db._store[self.path] = dict(data)


class BizCollection:
    def __init__(self, db, path):
        self._db = db
        self.path = tuple(path)

    def document(self, doc_id):
        return BizRef(self._db, self.path + (doc_id,))

    def where(self, *args, **kwargs):
        if kwargs.get("filter") is not None:
            field, op, value = (
                kwargs["filter"].field_path,
                kwargs["filter"].op_string,
                kwargs["filter"].value,
            )
        else:
            field, op, value = args[:3]
        found = []
        for path, data in self._db._store.items():
            if len(path) == len(self.path) + 1 and path[: len(self.path)] == self.path:
                if op == "==" and data.get(field) == value:
                    found.append(BizSnapshot(data, path[-1]))
        return BizQuery(found)


class BizDb:
    def __init__(self):
        self._store = {}

    def collection(self, name):
        return BizCollection(self, (name,))


@pytest.fixture
def fake_db(monkeypatch):
    import routes.business_api as business_api

    db = BizDb()
    monkeypatch.setattr(business_api, "db", db)
    return db


def seed(db, biz_id, data):
    db.collection("businesses").document(biz_id).set(data)


def test_business_api_blueprint_registered(flask_app):
    rules = {r.rule for r in flask_app.url_map.iter_rules()}
    assert "/api/business" in rules
    assert "/api/business/<business_id>" in rules


def test_list_unauthenticated_401(client):
    resp = client.get("/api/business")
    assert resp.status_code == 401
    assert resp.get_json() == {"success": False, "error": "Authentication required"}


def test_list_returns_only_callers_businesses(fake_db, client):
    seed(fake_db, "b1", {"owner_id": "u1", "name": "One", "created_at": "t1"})
    seed(fake_db, "b2", {"owner_id": "u2", "name": "Two", "created_at": "t2"})
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"

    resp = client.get("/api/business")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["businesses"] == [
        {"id": "b1", "owner_id": "u1", "name": "One", "created_at": "t1"}
    ]


def test_list_empty(fake_db, client):
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"

    resp = client.get("/api/business")
    assert resp.status_code == 200
    assert resp.get_json() == {"success": True, "businesses": []}


def test_get_unauthenticated_401(client):
    resp = client.get("/api/business/b1")
    assert resp.status_code == 401
    assert resp.get_json() == {"success": False, "error": "Authentication required"}


def test_get_not_found_404(fake_db, client):
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"

    resp = client.get("/api/business/missing")
    assert resp.status_code == 404
    assert resp.get_json() == {"success": False, "error": "Business not found"}


def test_get_non_owner_403(fake_db, client):
    seed(fake_db, "b1", {"owner_id": "u2", "name": "Two"})
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"

    resp = client.get("/api/business/b1")
    assert resp.status_code == 403
    assert resp.get_json() == {
        "success": False,
        "error": "You do not have permission to view this business",
    }


def test_get_owner_200(fake_db, client):
    data = {
        "owner_id": "u1",
        "name": "One",
        "website_url": "https://example.com",
        "industry": "retail",
        "description": "desc",
        "created_at": "t1",
        "updated_at": "t1",
    }
    seed(fake_db, "b1", data)
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"

    resp = client.get("/api/business/b1")
    assert resp.status_code == 200
    assert resp.get_json() == {"success": True, "business": {"id": "b1", **data}}


def test_guard_order_unauthenticated_beats_404(fake_db, client):
    seed(fake_db, "b1", {"owner_id": "u1", "name": "One"})

    resp = client.get("/api/business/b1")
    assert resp.status_code == 401  # no session → 401, NOT 404 or 403