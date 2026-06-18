import uuid
import asyncio
import logging
from typing import List, Any
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel

from browser_service import scan_web_form
from ai_service import map_profile_to_fields
from state import active_profiles, active_forms, active_mappings, active_runs

logger = logging.getLogger("formpilot-backend")
router = APIRouter()

class FormAnalyzeRequest(BaseModel):
    profile_id: str
    target_url: str

@router.post("/api/forms/analyze")
async def analyze_form(req: FormAnalyzeRequest):
    """
    Spawns Playwright to scan fields on target_url, and maps
    the matching profile data points, returning a structured mapping plan.
    """
    if req.profile_id not in active_profiles:
        raise HTTPException(
            status_code=404,
            detail="Active profile not found. Please upload a resume first."
        )
    
    profile_data = active_profiles[req.profile_id]["profile"]
    
    # Scan target form
    try:
        scan_result = await scan_web_form(req.target_url, profile_data)
        detected_fields = scan_result["detected_fields"]
        total_dom = scan_result["total_dom_elements"]
        total_logical = scan_result["total_logical_fields"]
    except Exception as e:
        logger.error(f"Playwright failed to scan URL: {req.target_url}. Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Playwright browser failed to scan the target form: {str(e)}"
        )

    # Perform mapping analysis
    resume_file_path = active_profiles[req.profile_id].get("resume_file_path")
    try:
        mapping_plan = map_profile_to_fields(
            profile_data, detected_fields,
            form_url=req.target_url,
            resume_file_path=resume_file_path
        )
    except Exception as e:
        logger.error(f"Failed to generate profile mappings: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate field mapping plan."
        )

    form_id = str(uuid.uuid4())
    
    # Store in-memory sessions
    active_forms[form_id] = {
        "form_id": form_id,
        "target_url": req.target_url,
        "detected_fields": detected_fields
    }
    active_mappings[form_id] = mapping_plan
    
    logger.info(f"Form analysis complete. Form ID: {form_id}, Logical Fields: {total_logical}, DOM elements: {total_dom}")
    
    return {
        "form_id": form_id,
        "detected_fields": detected_fields,
        "mapping_plan": mapping_plan,
        "total_dom_elements": total_dom,
        "total_logical_fields": total_logical,
        "grouped_fields": detected_fields
    }

@router.get("/api/mappings/{form_id}")
def get_mappings(form_id: str):
    """
    Retrieves the current mapped schema for the form.
    """
    if form_id not in active_mappings:
        raise HTTPException(status_code=404, detail="Form mapping plan not found")
    return {
        "form_id": form_id,
        "mapping_plan": active_mappings[form_id]
    }

@router.put("/api/mappings/{form_id}")
def update_mappings(form_id: str, mapping_plan: list = Body(...)):
    """
    Saves an updated mapping plan (e.g. from user approvals or edits).
    """
    if form_id not in active_mappings:
        raise HTTPException(status_code=404, detail="Form mapping plan not found")
    
    active_mappings[form_id] = mapping_plan
    logger.info(f"Updated in-memory mapping plan for Form ID: {form_id}")
    return {
        "form_id": form_id,
        "mapping_plan": active_mappings[form_id]
    }

class ConfirmRunRequest(BaseModel):
    form_id: str
    profile_id: str
    mapping_plan: List[Any]  # The user-edited mapping plan from the preview table

@router.post("/api/forms/confirm-run")
async def confirm_run(req: ConfirmRunRequest):
    """
    Called after the user reviews and edits the mapping table on the frontend.
    Saves the final mapping plan and creates a new run session using it.
    This replaces the need for the frontend to call /api/runs separately after editing.
    """
    if req.profile_id not in active_profiles:
        raise HTTPException(status_code=404, detail="Active profile not found.")
    if req.form_id not in active_forms:
        raise HTTPException(status_code=404, detail="Form session not found. Please re-scan the form.")

    # Persist the user-edited mapping plan
    active_mappings[req.form_id] = req.mapping_plan
    logger.info(f"User-confirmed mapping plan saved for Form ID: {req.form_id} ({len(req.mapping_plan)} fields)")

    # Create run session using the confirmed plan
    run_id = str(uuid.uuid4())
    form_data = active_forms[req.form_id]
    target_url = form_data.get("target_url", "")

    active_runs[run_id] = {
        "run_id": run_id,
        "form_id": req.form_id,
        "profile_id": req.profile_id,
        "status": "pending",
        "events": [],
        "target_url": target_url,
        "pause_requested": False,
        "cancel_requested": False,
        "current_field_index": 0,
        "queue": asyncio.Queue(),
        "mapping_plan": req.mapping_plan
    }

    # NOTE: No Playwright browser is launched here.
    # The frontend loads the form via /proxy in an iframe and injects values client-side.
    logger.info(f"Initialized run session (iframe mode). Run ID: {run_id}")
    return {"run_id": run_id, "form_id": req.form_id, "mapping_plan": req.mapping_plan}
