import logging
from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List

from config import settings
from database import init_db, get_db, DecisionLog, FilterSetting, CreatorProfile
from schemas import (
    PostContent, CurateResponse, CorrectionRequest, 
    FilterUpdate, FilterSettingSchema, StatsResponse
)
from graph import run_curator
from reflection import process_user_correction

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main_server")

app = FastAPI(
    title="LinkedIn Attention Guardian Backend",
    description="Local FastAPI API powering the LangGraph and memory pipeline for feed curation."
)

# Enable CORS for chrome extensions
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Safely allow Chrome Extension origins in local execution
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup routine
@app.on_event("startup")
def startup_event():
    logger.info("Initializing SQLite memory database...")
    init_db()
    logger.info("Database initialized successfully.")

@app.post("/curate", response_model=CurateResponse)
def curate_post(post: PostContent):
    """
    Fast Graph Curation Endpoint. Evaluates the incoming LinkedIn post.
    """
    logger.info(f"Incoming post for curation from author URN: {post.author_urn}")
    if not post.post_text.strip():
        return CurateResponse(post_urn=post.post_urn, action="keep", matched_detector=None, explanation="Empty post text")

    try:
        curation_result = run_curator(post)
        logger.info(f"Curation complete for {post.post_urn}. Action: {curation_result['action']}")
        return CurateResponse(
            post_urn=curation_result.get("post_urn"),
            action=curation_result.get("action", "keep"),
            matched_detector=curation_result.get("matched_detector"),
            explanation=curation_result.get("explanation")
        )
    except Exception as e:
        logger.error(f"Error executing curation: {e}")
        # Fail-open safety standard
        return CurateResponse(post_urn=post.post_urn, action="keep", matched_detector=None, explanation=f"API Error: {str(e)}")

@app.post("/action/correction")
def submit_correction(req: CorrectionRequest, background_tasks: BackgroundTasks):
    """
    Submits user correction (e.g. restore, keep, block) to the Reflection Graph asynchronously.
    """
    logger.info(f"Submitting correction action '{req.action}' for post {req.post_urn}")
    background_tasks.add_task(process_user_correction, req.post_urn, req.action)
    return {"status": "success", "message": "Correction submitted to Reflection Graph"}

@app.get("/settings/filters", response_model=List[FilterSettingSchema])
def get_filters():
    """
    Retrieve current filter enabled/disabled toggles.
    """
    try:
        with get_db() as db:
            filters = db.query(FilterSetting).all()
            return [FilterSettingSchema(detector_id=f.detector_id, enabled=f.enabled) for f in filters]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/settings/filters")
def update_filter(update: FilterUpdate):
    """
    Update state of a specific detector filter.
    """
    try:
        with get_db() as db:
            item = db.query(FilterSetting).filter_by(detector_id=update.detector_id).first()
            if not item:
                raise HTTPException(status_code=404, detail=f"Filter {update.detector_id} not found")
            item.enabled = update.enabled
            db.add(item)
        return {"status": "success", "message": f"Updated detector '{update.detector_id}' to enabled={update.enabled}"}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats", response_model=StatsResponse)
def get_curator_stats():
    """
    Get aggregated curation performance statistics.
    """
    try:
        with get_db() as db:
            logs = db.query(DecisionLog).all()
            total = len(logs)
            
            actions = {"keep": 0, "hide": 0, "collapse": 0, "highlight": 0}
            detectors = {
                "ai_slop": 0, "fake_expert": 0, "news_aggregator": 0, 
                "sales_pitch": 0, "humble_brag": 0, "generic_motivation": 0, 
                "copy_paste_influencer": 0
            }
            
            for log in logs:
                actions[log.action_taken] = actions.get(log.action_taken, 0) + 1
                if log.matched_detector and log.matched_detector in detectors:
                    detectors[log.matched_detector] += 1
            
            return StatsResponse(
                total_processed=total,
                kept_count=actions["keep"],
                hidden_count=actions["hide"],
                collapsed_count=actions["collapse"],
                highlighted_count=actions["highlight"],
                detector_breakdown=detectors
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/logs")
def get_logs(limit: int = 50):
    """
    Get recent curation history logs.
    """
    try:
        with get_db() as db:
            logs = db.query(DecisionLog).order_by(DecisionLog.created_at.desc()).limit(limit).all()
            return [
                {
                    "id": log.id,
                    "post_urn": log.post_urn,
                    "author_urn": log.author_urn,
                    "author_name": log.author_name,
                    "post_text": log.post_text[:120] + "..." if log.post_text else "",
                    "action_taken": log.action_taken,
                    "matched_detector": log.matched_detector,
                    "explanation": log.explanation,
                    "user_corrected": log.user_corrected,
                    "created_at": log.created_at.isoformat()
                }
                for log in logs
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/creators")
def get_creators(limit: int = 100):
    """
    Get creator trust statistics from memory.
    """
    try:
        with get_db() as db:
            creators = db.query(CreatorProfile).order_by(CreatorProfile.trust_score.desc()).limit(limit).all()
            return [
                {
                    "author_urn": c.author_urn,
                    "display_name": c.display_name,
                    "trust_score": round(c.trust_score, 2),
                    "times_seen": c.times_seen,
                    "times_hidden": c.times_hidden,
                    "times_restored": c.times_restored,
                    "last_seen_at": c.last_seen_at.isoformat() if c.last_seen_at else None
                }
                for c in creators
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
