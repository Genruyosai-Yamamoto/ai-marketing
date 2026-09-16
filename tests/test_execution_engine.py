import pytest


class _Snapshot:
    def __init__(self, data):
        self.exists = data is not None
        self._data = dict(data) if data else {}

    def to_dict(self):
        return dict(self._data)


class _Ref:
    _auto = 0

    def __init__(self, path, data=None):
        self.path = list(path)
        self.id = self.path[-1]
        self._set_data = dict(data) if data else None
        self.updates = []
        self.children = {}

    def get(self):
        return _Snapshot(self._set_data)

    @property
    def data(self):
        state = dict(self._set_data or {})
        for update in self.updates:
            state.update(update)
        return state

    def set(self, data):
        self._set_data = dict(data)

    def update(self, data):
        self.updates.append(dict(data))

    def collection(self, name):
        if name not in self.children:
            self.children[name] = _Collection(self.path + [name])
        return self.children[name]


def _new_id():
    _Ref._auto += 1
    return f"doc{_Ref._auto}"


class _Collection:
    def __init__(self, path):
        self.path = list(path)
        self.docs = {}

    def document(self, doc_id=None):
        if doc_id is None:
            doc_id = _new_id()
        if doc_id not in self.docs:
            self.docs[doc_id] = _Ref(self.path + [doc_id])
        return self.docs[doc_id]


class FakeTaskDb:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = _Collection([name])
        return self.collections[name]


@pytest.fixture
def execution_env(monkeypatch):
    import services.execution_engine as execution_engine

    db = FakeTaskDb()
    monkeypatch.setattr(execution_engine, "db", db)
    return execution_engine, db


def test_execute_action_completed_social(execution_env):
    execution_engine, db = execution_env
    biz_ref = db.collection("businesses").document("b1")
    biz_ref.collection("executions").document("e1").set({"action_id": "a1"})
    biz_ref.collection("actions").document("a1").set(
        {"action_type": "social", "status": "approved"}
    )

    result = execution_engine.execute_action("b1", "e1")

    assert result["success"] is True
    assert result["status"] == "not_implemented"

    execution_ref = biz_ref.collection("executions").document("e1")
    assert execution_ref.data["status"] == "completed"
    assert execution_ref.data["result"] == result
    assert execution_ref.data["started_at"]
    assert execution_ref.data["completed_at"]
    assert execution_ref.data["updated_at"]


def test_execute_action_unrouted_type_marks_failed(execution_env):
    execution_engine, db = execution_env
    biz_ref = db.collection("businesses").document("b1")
    biz_ref.collection("executions").document("e1").set({"action_id": "a1"})
    biz_ref.collection("actions").document("a1").set(
        {"action_type": "email", "status": "approved"}
    )

    with pytest.raises(
        ValueError, match="No connector available for action type: email"
    ):
        execution_engine.execute_action("b1", "e1")

    execution_ref = biz_ref.collection("executions").document("e1")
    assert execution_ref.data["status"] == "failed"
    assert (
        execution_ref.data["error"]
        == "No connector available for action type: email"
    )
    assert execution_ref.data["completed_at"]


def test_execute_action_missing_execution_raises(execution_env):
    execution_engine, _ = execution_env

    with pytest.raises(ValueError, match="Execution not found"):
        execution_engine.execute_action("b1", "missing")


def test_execute_action_missing_action_raises(execution_env):
    execution_engine, db = execution_env
    biz_ref = db.collection("businesses").document("b1")
    biz_ref.collection("executions").document("e1").set({"action_id": "nope"})

    with pytest.raises(ValueError, match="Action not found"):
        execution_engine.execute_action("b1", "e1")


def test_execute_action_unapproved_action_raises(execution_env):
    execution_engine, db = execution_env
    biz_ref = db.collection("businesses").document("b1")
    biz_ref.collection("executions").document("e1").set({"action_id": "a1"})
    biz_ref.collection("actions").document("a1").set(
        {"action_type": "social", "status": "pending"}
    )

    with pytest.raises(ValueError, match="Action must be approved before execution"):
        execution_engine.execute_action("b1", "e1")