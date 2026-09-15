from datetime import datetime
from celery import Celery
from firebase_admin import firestore
from firebase import db
from website_analyzer import fetch_website_html, analyze_html


celery = Celery(
    "ai_growth_agent",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
)

@celery.task(bind=True, name="tasks.analyze_business_website")
def analyze_business_website(self, business_id, user_id, run_id):
    business_ref = db.collection("businesses").document(business_id)
    run_ref = business_ref.collection("agent_runs").document(run_id)

    business_doc = business_ref.get()

    if not business_doc.exists:
        run_ref.update({
            "status": "failed",
            "error": "Business not found",
            "completed_at": datetime.utcnow().isoformat(),
        })
        return {
            "success": False,
            "error": "Business not found",
        }

    business = business_doc.to_dict()

    if business.get("owner_id") != user_id:
        run_ref.update({
            "status": "failed",
            "error": "Unauthorized",
            "completed_at": datetime.utcnow().isoformat(),
        })
        return {
            "success": False,
            "error": "Unauthorized",
        }

    website_url = business.get("website_url")

    if not website_url:
        run_ref.update({
            "status": "failed",
            "error": "Business has no website URL",
            "completed_at": datetime.utcnow().isoformat(),
        })
        return {
            "success": False,
            "error": "Business has no website URL",
        }

    try:
        # Mark job as running
        run_ref.update({
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
        })

        # Fetch website
        html, final_url = fetch_website_html(website_url)

        # Analyze HTML
        analysis = analyze_html(html)

        # Save observation
        observation = {
            "business_id": business_id,
            "owner_id": user_id,
            "source_url": website_url,
            "final_url": final_url,
            "analysis": analysis,
            "status": "completed",
            "created_at": datetime.utcnow().isoformat(),
        }

        observation_ref = (
            business_ref
            .collection("observations")
            .document()
        )

        observation_ref.set(observation)

        # Mark run as completed
        run_ref.update({
            "status": "completed",
            "observation_id": observation_ref.id,
            "completed_at": datetime.utcnow().isoformat(),
        })

        return {
            "success": True,
            "observation_id": observation_ref.id,
            "run_id": run_id,
        }

    except Exception as exc:
        # Mark run as failed
        run_ref.update({
            "status": "failed",
            "error": str(exc),
            "completed_at": datetime.utcnow().isoformat(),
        })

        raise