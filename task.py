from datetime import datetime
from celery import Celery
from firebase_admin import firestore
from firebase import db
from website_analyzer import fetch_website_html, analyze_html
from services.execution_engine import execute_action

celery = Celery(
    "ai_growth_agent",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
)

@celery.task(
    bind=True,
    name="tasks.execute_approved_action"
)
def execute_approved_action(
    self,
    business_id,
    execution_id,
):
    return execute_action(
        business_id,
        execution_id,
    )

@celery.task(bind=True, name="tasks.analyze_business_website")
def analyze_business_website(self, business_id, user_id, run_id):
    business_ref = db.collection("businesses").document(business_id)
    run_ref = business_ref.collection("agent_runs").document(run_id)

    business_doc = business_ref.get()

    if not business_doc.exists:
        run_ref.update({
            "analysis_status": "failed",
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
            "analysis_status": "failed",
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
            "analysis_status": "failed",
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
            "analysis_status": "running",
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
            "analysis_status": "completed",
            "created_at": datetime.utcnow().isoformat(),
        }

        observation_ref = (
            business_ref
            .collection("observations")
            .document()
        )

        observation_ref.set(observation)

        # Step 4-7: business understanding + opportunities.
        # Lazy imports avoid constructing a Groq() client when task.py loads.
        from agent.analyzer import analyze_observation
        from agent.opportunity_generator import generate_opportunities
        from services.opportunity_service import create_opportunity
        from services.opportunity_action_service import generate_actions_for_opportunities

        try:
            analysis = analyze_observation(observation)

            opportunities = generate_opportunities(analysis)

            opportunity_ids = []

            for position, opp in enumerate(opportunities):
                result = create_opportunity(
                    business_id=business_id,
                    opportunity=opp,
                    owner_id=user_id,
                )

                opportunity_ids.append(result["id"])
            
            planner_result = generate_actions_for_opportunities(
                business_id=business_id,
                owner_id=user_id,
                business_analysis=analysis,
                opportunity_ids=opportunity_ids,
            )

            # Single terminal completed transition
            run_ref.update({
                "analysis_status": "completed",
                "status": "awaiting_approval",
                "observation_id": observation_ref.id,
                "opportunity_ids": opportunity_ids,
                "actions_created": planner_result.get("actions_created", 0),
                "actions_existing": planner_result.get("actions_existing", 0),
                "completed_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            })
            
        except Exception as exc:
            run_ref.update({
                "analysis_status": "failed",
                "error": str(exc),
                "completed_at": datetime.utcnow().isoformat(),
            })
            raise

        return {
            "success": True,
            "observation_id": observation_ref.id,
            "opportunity_ids": opportunity_ids,
            "actions_created": planner_result["actions_created"],
            "actions_existing": planner_result["actions_existing"],
            "run_id": run_id,
        }

    except Exception as exc:
        # Mark run as failed
        run_ref.update({
            "analysis_status": "failed",
            "error": str(exc),
            "completed_at": datetime.utcnow().isoformat(),
        })

        raise

@celery.task(bind=True, name="tasks.run_agent_cycle")
def run_agent_cycle(self, business_id, user_id, run_id):
    run_ref = (
        db.collection("businesses")
        .document(business_id)
        .collection("agent_runs")
        .document(run_id)
    )

    run_ref.update({
        "status": "running",
        "analysis_status": "queued",
        "cycle_started_at": datetime.utcnow().isoformat(),
    })

    try:
        result = analyze_business_website.delay(
            business_id=business_id,
            user_id=user_id,
            run_id=run_id,
        )

        run_ref.update({
            "analysis_task_id": result.id,
            "analysis_status": "queued",
            "updated_at": datetime.utcnow().isoformat(),
        })

        return {
            "success": True,
            "run_id": run_id,
            "analysis_task_id": result.id,
        }

    except Exception as exc:
        run_ref.update({
            "status": "failed",
            "error": str(exc),
            "completed_at": datetime.utcnow().isoformat(),
        })
        raise