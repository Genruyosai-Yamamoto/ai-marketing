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


VALID_OPPORTUNITY = {
    "title": "Add SEO",
    "description": "Desc",
    "problem": "Problem",
    "evidence": ["e1"],
    "potential_impact": "high",
    "confidence": 0.9,
    "type": "seo",
}


@pytest.fixture
def agent_modules(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    import agent.analyzer as analyzer_mod
    import agent.opportunity_generator as generator_mod
    return analyzer_mod, generator_mod


@pytest.fixture
def task_env(monkeypatch, agent_modules):
    import task as task_mod

    db = FakeTaskDb()
    biz_ref = db.collection("businesses").document("b1")
    biz_ref.set({"owner_id": "u1", "name": "Acme", "website_url": "https://acme.example"})
    biz_ref.collection("agent_runs").document("r1").set(
        {"business_id": "b1", "owner_id": "u1", "type": "website_analysis", "status": "queued"}
    )

    analyzer_mod, generator_mod = agent_modules
    monkeypatch.setattr(task_mod, "db", db)
    monkeypatch.setattr(
        task_mod, "fetch_website_html",
        lambda url: ("<html><title>Acme</title></html>", url),
    )
    monkeypatch.setattr(
        task_mod, "analyze_html",
        lambda html: {"title": "Acme", "headings": [], "links": [], "meta_description": "Acme"},
    )
    monkeypatch.setattr(
        analyzer_mod, "analyze_observation",
        lambda observation: {"business_summary": "Acme sells widgets."},
    )
    monkeypatch.setattr(generator_mod, "generate_opportunities", lambda analysis: [])
    return task_mod, db


def test_happy_path_persists_opportunities_and_completes_run(task_env, monkeypatch):
    task_mod, db = task_env
    import agent.opportunity_generator as generator_mod

    monkeypatch.setattr(generator_mod, "generate_opportunities", lambda analysis: [
        dict(VALID_OPPORTUNITY),
        dict(VALID_OPPORTUNITY, title="Use Instagram", type="social", confidence=0.4),
    ])

    result = task_mod.analyze_business_website.run("b1", "u1", "r1")

    biz_ref = db.collection("businesses").document("b1")
    run_ref = biz_ref.collection("agent_runs").document("r1")

    assert result["success"] is True
    assert result["run_id"] == "r1"
    assert len(result["opportunity_ids"]) == 2

    obs_docs = list(biz_ref.collection("observations").docs.values())
    assert len(obs_docs) == 1
    assert obs_docs[0].data["analysis"]["title"] == "Acme"

    completed = [u for u in run_ref.updates if u.get("status") == "completed"]
    assert completed == [run_ref.updates[-1]]
    assert run_ref.data["status"] == "completed"
    assert run_ref.data["observation_id"] == result["observation_id"]
    assert run_ref.data["opportunity_ids"] == result["opportunity_ids"]

    opp_docs = sorted(
        biz_ref.collection("opportunities").docs.values(),
        key=lambda ref: ref.data["position"],
    )
    assert [ref.id for ref in opp_docs] == result["opportunity_ids"]
    first = opp_docs[0].data
    assert first["title"] == "Add SEO"
    assert first["business_id"] == "b1"
    assert first["owner_id"] == "u1"
    assert first["position"] == 0
    assert opp_docs[1].data["position"] == 1
    assert first["created_at"]
    for key in ("title", "description", "problem", "evidence",
                "potential_impact", "confidence", "type"):
        assert key in first


def test_observation_groq_failure_marks_run_failed(task_env, monkeypatch):
    task_mod, db = task_env
    import agent.analyzer as analyzer_mod

    monkeypatch.setattr(
        analyzer_mod, "analyze_observation",
        lambda observation: (_ for _ in ()).throw(RuntimeError("groq down")),
    )

    with pytest.raises(RuntimeError, match="groq down"):
        task_mod.analyze_business_website.run("b1", "u1", "r1")

    biz_ref = db.collection("businesses").document("b1")
    run_ref = biz_ref.collection("agent_runs").document("r1")
    assert run_ref.data["status"] == "failed"
    assert run_ref.data["error"] == "groq down"
    assert len(biz_ref.collection("observations").docs) == 1
    assert not biz_ref.collection("opportunities").docs


def test_opportunity_groq_failure_marks_run_failed(task_env, monkeypatch):
    task_mod, db = task_env
    import agent.opportunity_generator as generator_mod

    monkeypatch.setattr(
        generator_mod, "generate_opportunities",
        lambda analysis: (_ for _ in ()).throw(ValueError("bad JSON")),
    )

    with pytest.raises(ValueError, match="bad JSON"):
        task_mod.analyze_business_website.run("b1", "u1", "r1")

    biz_ref = db.collection("businesses").document("b1")
    run_ref = biz_ref.collection("agent_runs").document("r1")
    assert run_ref.data["status"] == "failed"
    assert run_ref.data["error"] == "bad JSON"
    assert len(biz_ref.collection("observations").docs) == 1
    assert not biz_ref.collection("opportunities").docs


def test_invalid_opportunity_data_marks_run_failed(task_env, monkeypatch):
    task_mod, db = task_env
    import agent.opportunity_generator as generator_mod
    from agent.opportunity_validation import validate_opportunities

    broken = dict(VALID_OPPORTUNITY, confidence=2)

    monkeypatch.setattr(
        generator_mod, "generate_opportunities",
        lambda analysis: validate_opportunities([broken]),
    )

    with pytest.raises(ValueError, match="out of range"):
        task_mod.analyze_business_website.run("b1", "u1", "r1")

    biz_ref = db.collection("businesses").document("b1")
    run_ref = biz_ref.collection("agent_runs").document("r1")
    assert run_ref.data["status"] == "failed"
    assert len(biz_ref.collection("observations").docs) == 1
    assert not biz_ref.collection("opportunities").docs


def test_empty_opportunities_completes_run_with_no_docs(task_env):
    task_mod, db = task_env

    result = task_mod.analyze_business_website.run("b1", "u1", "r1")

    biz_ref = db.collection("businesses").document("b1")
    run_ref = biz_ref.collection("agent_runs").document("r1")
    assert result["opportunity_ids"] == []
    assert run_ref.data["status"] == "completed"
    assert run_ref.data["opportunity_ids"] == []
    assert not biz_ref.collection("opportunities").docs