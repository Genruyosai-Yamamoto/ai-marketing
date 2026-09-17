import pytest


@pytest.fixture
def flask_app():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


def test_home_serves_spa(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "js/api.js" in html
    assert "js/app.js" in html


def test_static_js_served(client):
    for asset in ("/static/js/api.js", "/static/js/app.js"):
        resp = client.get(asset)
        assert resp.status_code == 200
        assert len(resp.data) > 0