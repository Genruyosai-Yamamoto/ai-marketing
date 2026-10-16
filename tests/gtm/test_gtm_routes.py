"""
Unit and route tests for routes.gtm_routes and tasks.run_gtm_analysis.
"""
from unittest.mock import MagicMock, patch
import pytest


def test_gtm_run_unauthenticated_returns_401(client):
    res = client.post("/api/gtm/run", json={"business_id": "biz-1"})
    assert res.status_code == 401
    assert res.json["success"] is False


def test_gtm_run_missing_business_id_returns_400(auth_client):
    res = auth_client.post("/api/gtm/run", json={})
    assert res.status_code == 400
    assert "business_id" in res.json["error"]


def test_gtm_run_business_not_found_returns_404(auth_client):
    mock_doc = MagicMock()
    mock_doc.exists = False

    with patch("firebase.db.collection") as mock_db:
        mock_db.return_value.document.return_value.get.return_value = mock_doc
        res = auth_client.post("/api/gtm/run", json={"business_id": "biz-missing"})

    assert res.status_code == 404


def test_gtm_run_unauthorized_returns_403(auth_client):
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"owner_id": "different-user"}

    with patch("firebase.db.collection") as mock_db:
        mock_db.return_value.document.return_value.get.return_value = mock_doc
        res = auth_client.post("/api/gtm/run", json={"business_id": "biz-1"})

    assert res.status_code == 403


def test_gtm_run_authorized_dispatches_task(auth_client, mock_gtm_business_doc):
    with patch("firebase.db.collection") as mock_db, \
         patch("task.run_gtm_analysis.delay") as mock_delay:
        mock_db.return_value.document.return_value.get.return_value = mock_gtm_business_doc
        mock_delay.return_value.id = "celery-task-123"

        res = auth_client.post("/api/gtm/run", json={"business_id": "biz-1"})

    assert res.status_code == 202
    assert res.json["success"] is True
    assert "run_id" in res.json
    mock_delay.assert_called_once()


def test_gtm_runs_list_route(auth_client, mock_gtm_business_doc):
    mock_run_doc = MagicMock()
    mock_run_doc.id = "run-1"
    mock_run_doc.to_dict.return_value = {
        "status": "completed",
        "gtm_scores": {"overall": 80},
    }

    with patch("firebase.db.collection") as mock_db:
        mock_db.return_value.document.return_value.get.return_value = mock_gtm_business_doc
        mock_db.return_value.document.return_value.collection.return_value.order_by.return_value.stream.return_value = [mock_run_doc]

        res = auth_client.get("/api/gtm/runs?business_id=biz-1")

    assert res.status_code == 200
    assert res.json["success"] is True
    assert len(res.json["runs"]) == 1
    assert res.json["runs"][0]["id"] == "run-1"


def test_gtm_run_detail_route(auth_client, mock_gtm_business_doc):
    mock_run_doc = MagicMock()
    mock_run_doc.exists = True
    mock_run_doc.id = "run-1"
    mock_run_doc.to_dict.return_value = {
        "status": "completed",
        "gtm_scores": {"overall": 85},
    }

    with patch("firebase.db.collection") as mock_db:
        mock_db.return_value.document.return_value.get.return_value = mock_gtm_business_doc
        mock_db.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = mock_run_doc

        res = auth_client.get("/api/gtm/runs/run-1?business_id=biz-1")

    assert res.status_code == 200
    assert res.json["run"]["id"] == "run-1"


def test_gtm_run_dossier_route(auth_client, mock_gtm_business_doc, tmp_path):
    dossier_file = tmp_path / "run-1.md"
    dossier_file.write_text("# Executive Dossier Content", encoding="utf-8")

    mock_run_doc = MagicMock()
    mock_run_doc.exists = True
    mock_run_doc.id = "run-1"
    mock_run_doc.to_dict.return_value = {
        "status": "completed",
        "dossier_path": str(dossier_file),
    }

    with patch("firebase.db.collection") as mock_db:
        mock_db.return_value.document.return_value.get.return_value = mock_gtm_business_doc
        mock_db.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = mock_run_doc

        res = auth_client.get("/api/gtm/runs/run-1/dossier?business_id=biz-1")

    assert res.status_code == 200
    assert "Executive Dossier Content" in res.data.decode("utf-8")


def test_gtm_runs_list_requires_params_and_auth(client, auth_client):
    assert client.get("/api/gtm/runs").status_code == 401
    assert auth_client.get("/api/gtm/runs").status_code == 400


def test_gtm_run_detail_requires_params_and_missing_run_returns_404(client, auth_client, mock_gtm_business_doc):
    assert client.get("/api/gtm/runs/run-1").status_code == 401
    assert auth_client.get("/api/gtm/runs/run-1").status_code == 400

    mock_run_doc = MagicMock()
    mock_run_doc.exists = False

    with patch("firebase.db.collection") as mock_db:
        mock_db.return_value.document.return_value.get.return_value = mock_gtm_business_doc
        mock_db.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = mock_run_doc

        res = auth_client.get("/api/gtm/runs/missing-run?business_id=biz-1")

    assert res.status_code == 404


def test_gtm_run_dossier_generates_inline_if_file_missing(auth_client, mock_gtm_business_doc):
    mock_run_doc = MagicMock()
    mock_run_doc.exists = True
    mock_run_doc.id = "run-no-file"
    mock_run_doc.to_dict.return_value = {
        "id": "run-no-file",
        "status": "completed",
        "dossier_path": None,
        "gtm_scores": {"overall": 75},
    }

    with patch("firebase.db.collection") as mock_db:
        mock_db.return_value.document.return_value.get.return_value = mock_gtm_business_doc
        mock_db.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = mock_run_doc

        res = auth_client.get("/api/gtm/runs/run-no-file/dossier?business_id=biz-1")

    assert res.status_code == 200
    assert "Overall Score: 75" in res.data.decode("utf-8")


def test_gtm_run_celery_dispatch_exception_handled(auth_client, mock_gtm_business_doc):
    with patch("firebase.db.collection") as mock_db, \
         patch("task.run_gtm_analysis.delay", side_effect=Exception("Redis down")):
        mock_db.return_value.document.return_value.get.return_value = mock_gtm_business_doc

        res = auth_client.post("/api/gtm/run", json={"business_id": "biz-1"})

    assert res.status_code == 202
    assert res.json["success"] is True


def test_run_gtm_analysis_task_execution(mock_gtm_business_doc, tmp_path):
    from task import run_gtm_analysis

    mock_run_ref = MagicMock()
    mock_run_doc = MagicMock()
    mock_run_doc.exists = True

    mock_manifest = {
        "url": "https://mysite.com",
        "tiles": [{"filename": "tile_0001_hero.webp", "path": str(tmp_path / "tile.webp")}],
    }
    mock_comp_manifest = {
        "url": "https://rival.com",
        "tiles": [{"filename": "tile_0001_hero.webp", "path": str(tmp_path / "tile.webp")}],
    }

    mock_analysis = {
        "gtm_scores": {"overall": 80},
        "blind_spots": ["Missing pricing"],
        "opportunities": [
            {
                "title": "Add Pricing",
                "problem": "No pricing visible",
                "problem_key": "pricing_transparency",
                "type": "conversion",
                "potential_impact": "high",
                "confidence": 0.85,
            }
        ],
    }

    with patch("firebase.db.collection") as mock_db, \
         patch("services.pixelrag_service.render_and_tile_page", side_effect=[mock_manifest, mock_comp_manifest]), \
         patch("services.gtm_discovery_service.discover_competitors", return_value=[{"url": "https://rival.com", "domain": "rival.com"}]), \
         patch("services.gtm_discovery_service.get_gtm_seed_queries", return_value=["seo tool"]), \
         patch("agent.gtm_engine.analyze_gtm_tiles", return_value=mock_analysis), \
         patch("services.gtm_dossier_service.generate_gtm_dossier_markdown", return_value="# Dossier"), \
         patch("services.gtm_dossier_service.save_dossier_to_file", return_value="static/dossiers/run-1.md"), \
         patch("services.opportunity_service.create_opportunity", return_value={"id": "opp-1"}):

        # Configure mock_db to return business doc on collection("businesses").document(id)
        # and run_ref on collection("businesses").document(id).collection("gtm_runs").document(run_id)
        mock_db.return_value.document.return_value.get.return_value = mock_gtm_business_doc
        mock_db.return_value.document.return_value.collection.return_value.document.return_value = mock_run_ref

        res = run_gtm_analysis(business_id="biz-1", user_id="user-1", run_id="run-1")

    assert res["success"] is True
    assert res["run_id"] == "run-1"
    assert res["opportunities_count"] == 1
    mock_run_ref.update.assert_called()


