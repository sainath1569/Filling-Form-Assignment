import os
import uuid
import shutil
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from pypdf import PdfReader

from services.gemini_service import parse_resume_text_gemini
from state import active_profiles, UPLOAD_DIR, _save_profiles_to_disk

logger = logging.getLogger("formpilot-backend")
router = APIRouter()

@router.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    """
    Accepts a PDF file upload, saves it locally, extracts text,
    passes it to the LLM-based parse_resume_text tool, and stores the profile in-memory.
    """
    # 1. Validate file extension
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Please upload a PDF resume."
        )

    # 2. Create unique ID and filename
    profile_id = str(uuid.uuid4())
    safe_filename = f"{profile_id}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    # 3. Save PDF locally
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to save uploaded file to disk: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error saving the resume file."
        )

    # 4. Extract text using PdfReader
    extracted_text = ""
    try:
        reader = PdfReader(file_path)
        for page in reader.pages:
            text = page.extract_text()
            if text:
                extracted_text += text + "\n"
        extracted_text = extracted_text.strip()
    except Exception as e:
        logger.error(f"pypdf text extraction failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to parse text from the PDF file."
        )

    # Log extracted text
    logger.info(f"[Resume Text Extracted]\n{extracted_text}")

    # 5. Send extracted text to LLM tool
    try:
        profile_data = parse_resume_text_gemini(extracted_text).model_dump()
    except Exception as e:
        logger.error(f"Gemini parsing failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Structured profile extraction failed: {str(e)}"
        )

    # 6. Store in active_profiles runtime state
    preview_limit = 1000
    text_preview = (
        extracted_text[:preview_limit] + "..."
        if len(extracted_text) > preview_limit
        else extracted_text
    )

    result = {
        "profile_id": profile_id,
        "resume_file_path": file_path,
        "extracted_text_preview": text_preview,
        "profile": profile_data
    }
    
    active_profiles[profile_id] = result
    _save_profiles_to_disk(active_profiles)
    logger.info(f"Successfully uploaded and parsed resume. Profile ID: {profile_id}")

    return result

@router.get("/api/profile/{profile_id}")
def get_profile(profile_id: str):
    """
    Retrieves the parsed profile from the in-memory store.
    """
    if profile_id not in active_profiles:
        raise HTTPException(status_code=404, detail="Profile not found")
    return active_profiles[profile_id]

@router.put("/api/profile/{profile_id}")
def update_profile(profile_id: str, profile: dict):
    """
    Updates the parsed profile fields in the in-memory store.
    """
    if profile_id not in active_profiles:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    # We update the nested profile dictionary
    active_profiles[profile_id]["profile"] = profile
    _save_profiles_to_disk(active_profiles)
    logger.info(f"Successfully updated profile in-memory for ID: {profile_id}")
    return active_profiles[profile_id]

class RestoreProfileRequest(BaseModel):
    profile_id: str
    profile: dict

@router.post("/api/profile/{profile_id}/restore")
def restore_profile(profile_id: str, req: RestoreProfileRequest):
    """
    Called by the frontend when it has a cached profile in localStorage
    but the backend has restarted and lost it from memory.
    Re-registers the profile without calling the LLM again.
    """
    if profile_id in active_profiles:
        # Already in memory (e.g. loaded from disk on startup)
        return active_profiles[profile_id]
    
    # Reconstruct a minimal profile session from the frontend payload
    restored = {
        "profile_id": profile_id,
        "resume_file_path": None,
        "extracted_text_preview": None,
        "profile": req.profile,
    }
    active_profiles[profile_id] = restored
    _save_profiles_to_disk(active_profiles)
    logger.info(f"Restored cached profile from frontend. Profile ID: {profile_id}")
    return restored
