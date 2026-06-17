import os
import sys
import json
import time
import logging
from typing import Optional

# Ensure the parent directory is in sys.path so we can import ai_service
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from google import genai
from google.genai import types
from ai_service import UserProfile, AdditionalInfo, MOCK_PROFILE

logger = logging.getLogger("formpilot-gemini-service")

def get_gemini_client() -> Optional[genai.Client]:
    """
    Initializes and returns the official Gemini API client.
    Reads GEMINI_API_KEY from the environment.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)

# ---------------------------------------------------------------------------
# Shared JSON schema hint and system prompt
# ---------------------------------------------------------------------------

RESUME_SYSTEM_PROMPT = (
    "You must return ONLY valid JSON matching the requested template structure.\n"
    "Do not include explanations.\n"
    "Do not include markdown.\n"
    "Do not include code fences.\n"
    "Do not include analysis text.\n"
    "Return a single JSON object only.\n\n"
    "Anti-Hallucination Constraints:\n"
    "1. Return ONLY information found in the resume.\n"
    "2. Never invent universities.\n"
    "3. Never invent companies.\n"
    "4. Never invent projects.\n"
    "5. Never invent addresses.\n"
    "6. If a field is missing, return null.\n"
    "7. Do not create placeholder values."
)

RESUME_TEMPLATE_HINT = {
    "personal_info": {
        "first_name": "string or null",
        "last_name": "string or null",
        "full_name": "string or null",
        "email": "string or null",
        "phone": "string or null",
        "linkedin": "string or null",
        "github": "string or null",
        "portfolio": "string or null",
        "location": "string or null"
    },
    "education": [
        {
            "school": "string or null",
            "degree": "string or null",
            "discipline": "string or null",
            "start_year": "string or null",
            "end_year": "string or null"
        }
    ],
    "experience": [
        {
            "company": "string or null",
            "title": "string or null",
            "start_date": "string or null",
            "end_date": "string or null",
            "description": "string or null"
        }
    ],
    "skills": ["string"],
    "projects": [
        {
            "name": "string or null",
            "description": "string or null",
            "technologies": ["string"],
            "link": "string or null"
        }
    ],
    "additional_info": {
        "visa_sponsorship": "Yes or No or null",
        "work_authorization": "string or null",
        "notice_period": "string or null",
        "current_company": "string or null",
        "current_title": "string or null"
    }
}

def _parse_gemini_response(response_text: str) -> UserProfile:
    """Parses and validates Gemini response text into a UserProfile."""
    # Strip any accidental markdown fences
    clean = response_text.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]
        clean = clean.strip()
    parsed_json = json.loads(clean)
    logger.info(f"Parsed JSON: {json.dumps(parsed_json, indent=2)}")
    profile_data = UserProfile(**parsed_json)
    logger.info("Validation result: UserProfile validation SUCCEEDED.")
    return profile_data


# ---------------------------------------------------------------------------
# Strategy 1 (PRIMARY): Native PDF → Gemini Files API
# Sends the PDF as a document — Gemini reads formatting, tables, columns.
# ---------------------------------------------------------------------------

from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1.5, min=2, max=15),
    reraise=True
)
def parse_resume_pdf_gemini(file_path: str) -> UserProfile:
    """
    Sends the PDF file DIRECTLY to Gemini using the Files API.
    Gemini processes it as a native document (multimodal), understanding
    layout, tables, columns — not just raw text.

    Falls back to text-based parsing if the Files API fails.
    """
    client = get_gemini_client()
    if not client:
        logger.warning("Gemini API key not configured. Running in mock mode.")
        return MOCK_PROFILE

    uploaded_file = None
    try:
        # Step 1: Upload the PDF to Gemini Files API
        logger.info(f"Uploading PDF to Gemini Files API: {file_path}")
        with open(file_path, "rb") as f:
            uploaded_file = client.files.upload(
                file=f,
                config=types.UploadFileConfig(
                    mime_type="application/pdf",
                    display_name=os.path.basename(file_path)
                )
            )
        logger.info(f"PDF uploaded to Gemini. File URI: {uploaded_file.uri}")

        # Step 2: Wait for the file to be in ACTIVE state (usually instant)
        max_wait = 30
        elapsed = 0
        while hasattr(uploaded_file, 'state') and str(uploaded_file.state) not in ("FileState.ACTIVE", "ACTIVE"):
            if elapsed >= max_wait:
                raise TimeoutError("Gemini file upload did not become ACTIVE in time.")
            time.sleep(1)
            elapsed += 1
            uploaded_file = client.files.get(name=uploaded_file.name)

        # Step 3: Build prompt with the PDF file part
        user_content = [
            types.Part.from_uri(
                file_uri=uploaded_file.uri,
                mime_type="application/pdf"
            ),
            types.Part.from_text(
                text=f"Extract profile metadata from the resume document above.\n"
                f"Output must conform exactly to this JSON template structure:\n"
                f"{json.dumps(RESUME_TEMPLATE_HINT, indent=2)}"
            )
        ]

        logger.info("Sending PDF to Gemini for native document understanding...")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=RESUME_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=UserProfile
            )
        )

        raw_response = response.text
        logger.info(f"Raw Gemini Response (native PDF): {raw_response}")
        return _parse_gemini_response(raw_response)

    except Exception as e:
        logger.error(f"Native PDF parsing failed: {str(e)}. Falling back to text extraction.")
        # Clean up the uploaded file even if parsing failed
        if uploaded_file:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass
        raise e

    finally:
        # Always clean up the uploaded file from Gemini
        if uploaded_file:
            try:
                client.files.delete(name=uploaded_file.name)
                logger.info(f"Cleaned up Gemini uploaded file: {uploaded_file.name}")
            except Exception as cleanup_err:
                logger.warning(f"Could not delete Gemini file: {cleanup_err}")


# ---------------------------------------------------------------------------
# Strategy 2 (FALLBACK): Plain text → Gemini
# Used when PDF native upload fails.
# ---------------------------------------------------------------------------

@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1.5, min=2, max=15),
    reraise=True
)
def parse_resume_text_gemini(text: str) -> UserProfile:
    """
    Parses plain resume text and extracts a structured JSON profile using Gemini.
    Falls back to a high-quality mock profile only if no API key is configured.
    """
    client = get_gemini_client()
    if not client:
        logger.warning("Gemini API key not configured. Running in mock mode.")
        return MOCK_PROFILE

    user_content = (
        f"Extract profile metadata from the following resume text:\n\n"
        f"--- START RESUME ---\n{text}\n--- END RESUME ---\n\n"
        f"Output must conform exactly to this JSON template structure:\n"
        f"{json.dumps(RESUME_TEMPLATE_HINT, indent=2)}"
    )

    logger.info("Sending resume text to Gemini (text fallback mode)...")

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=RESUME_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=UserProfile
            )
        )

        raw_response = response.text
        logger.info(f"Raw Gemini Response (text mode): {raw_response}")
        return _parse_gemini_response(raw_response)

    except Exception as e:
        logger.error(f"Text-based Gemini parsing failed: {str(e)}")
        raise e
