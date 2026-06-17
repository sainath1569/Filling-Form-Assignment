import os
import sys
import json
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import json
import re
from urllib.parse import urljoin, urlparse

# For Windows, Playwright requires ProactorEventLoop to manage subprocesses correctly.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uuid
import shutil
import logging

from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect, Body, Query, Request
from fastapi.responses import Response, HTMLResponse
import httpx
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pypdf import PdfReader
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from ai_service import map_profile_to_fields, best_option_match, normalize_text, expand_abbreviation, is_phone_country_selector, parse_phone_number, match_phone_country_option
from services.gemini_service import parse_resume_pdf_gemini, parse_resume_text_gemini
from browser_service import scan_web_form



# Set up logging format and levels
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("formpilot-backend")

# Load environment configuration
load_dotenv()

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    """Startup: restore profiles from disk so backend restarts don't need LLM re-parsing."""
    loaded = _load_profiles_from_disk()
    active_profiles.update(loaded)
    yield
    # Shutdown: nothing extra needed

# Initialize FastAPI
app = FastAPI(
    title="FormPilot API",
    description="In-memory AI Form Autofill Agent API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration to allow local frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local assignment MVP, allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session states (profiles also backed by disk cache)
active_profiles: dict = {}
active_forms: dict = {}
active_runs: dict = {}
active_mappings: dict = {}
active_instructions: dict = {}

# Ensure local uploads directory exists
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
logger.info(f"Local uploads directory initialized at: {UPLOAD_DIR}")

# Disk cache for parsed profiles (survives server restarts)
PROFILES_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles_cache.json")

def _load_profiles_from_disk() -> dict:
    """Load previously parsed profiles from disk cache."""
    if os.path.exists(PROFILES_CACHE_FILE):
        try:
            with open(PROFILES_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"Loaded {len(data)} cached profile(s) from disk.")
            return data
        except Exception as e:
            logger.warning(f"Failed to load profiles cache from disk: {e}")
    return {}

def _save_profiles_to_disk(profiles: dict) -> None:
    """Persist all current profiles to disk cache."""
    try:
        with open(PROFILES_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(profiles, f, indent=2, default=str)
    except Exception as e:
        logger.warning(f"Failed to save profiles cache to disk: {e}")

# Check Gemini API configuration state
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logger.warning("Gemini API key not configured. Mapper will use programmatic fallback.")
else:
    logger.info("Gemini API key loaded successfully.")

@app.get("/")
def read_root():
    return {
        "status": "online",
        "app": "FormPilot",
        "mode": "mock" if not GEMINI_API_KEY else "production",
        "uploads_dir": UPLOAD_DIR
    }

@app.post("/api/resume/upload")
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

@app.get("/api/profile/{profile_id}")
def get_profile(profile_id: str):
    """
    Retrieves the parsed profile from the in-memory store.
    """
    if profile_id not in active_profiles:
        raise HTTPException(status_code=404, detail="Profile not found")
    return active_profiles[profile_id]

@app.put("/api/profile/{profile_id}")
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

@app.post("/api/profile/{profile_id}/restore")
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

class FormAnalyzeRequest(BaseModel):
    profile_id: str
    target_url: str

@app.post("/api/forms/analyze")
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

@app.get("/api/mappings/{form_id}")
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

@app.put("/api/mappings/{form_id}")
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

@app.post("/api/forms/confirm-run")
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


# --- WebSocket and Run Execution Services ---

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, run_id: str, websocket: WebSocket):
        await websocket.accept()
        if run_id not in self.active_connections:
            self.active_connections[run_id] = []
        self.active_connections[run_id].append(websocket)
        logger.info(f"WebSocket client connected to Run session: {run_id}")

    def disconnect(self, run_id: str, websocket: WebSocket):
        if run_id in self.active_connections:
            if websocket in self.active_connections[run_id]:
                self.active_connections[run_id].remove(websocket)
            if not self.active_connections[run_id]:
                del self.active_connections[run_id]
        logger.info(f"WebSocket client disconnected from Run session: {run_id}")

    async def broadcast(self, run_id: str, message: dict):
        if run_id in self.active_connections:
            for connection in self.active_connections[run_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to broadcast WS message to connection: {str(e)}")

manager = ConnectionManager()


async def inject_field_into_page(page, field: dict, profile_id: str) -> dict:
    """
    Injects a value into a form field based on the action type.
    """
    import os
    field_id = field.get("field_id")
    selector = field.get("selector")
    value = field.get("value")
    action = field.get("action", "fill")
    selected_option = field.get("selected_option")
    selected_option_label = field.get("selected_option_label")
    selected_options = field.get("selected_options") or []
    field_type = field.get("type", "text")
    label = field.get("field_label") or field.get("label") or field_id

    # ── Helper: find element across page and frames ───────────────────────────
    async def find_element(sel):
        if await page.locator(sel).count() > 0:
            return page.locator(sel).first
        for frame in page.frames:
            if await frame.locator(sel).count() > 0:
                return frame.locator(sel).first
        return None

    # ── SKIP ─────────────────────────────────────────────────────────────────
    if action == "skip":
        logger.info(f"[Inject] SKIP field '{label}' ({field_id})")
        return {"status": "skipped", "field_id": field_id, "action": "skip"}

    # ── UPLOAD FILE ───────────────────────────────────────────────────────────
    if action == "upload_file":
        profile = active_profiles.get(profile_id, {})
        resume_path = profile.get("resume_file_path")
        if not resume_path or not os.path.exists(resume_path):
            resume_path = value
        if not resume_path or not os.path.exists(resume_path):
            raise Exception(f"Resume file not found at path: {resume_path}")
        el = await find_element(selector)
        if not el:
            raise Exception(f"File input '{selector}' not found on page.")
        await el.set_input_files(resume_path)
        await page.wait_for_timeout(500)
        # Dispatch input & change
        await el.evaluate("el => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }")
        return {"status": "success", "field_id": field_id, "action": "upload_file"}

    # ── SELECT ───────────────────────────────────────────────────────────────
    if action == "select":
        el = await find_element(selector)
        if not el:
            raise Exception(f"Select/Combobox element '{selector}' not found.")
        
        target_val = selected_option
        target_label = selected_option_label or selected_option or value
        
        await el.scroll_into_view_if_needed()
        await el.click()
        await page.wait_for_timeout(300)
        
        el_tag = await el.evaluate("el => el.tagName.toLowerCase()")
        
        if el_tag == "select":
            # Native select
            opts = await el.evaluate("el => Array.from(el.options).map(o => ({ value: o.value, label: o.text }))")
            matched_val = None
            # exact match label/value
            for opt in opts:
                if str(opt["value"]).strip().lower() == str(target_val).strip().lower() or str(opt["label"]).strip().lower() == str(target_label).strip().lower():
                    matched_val = opt["value"]
                    break
            # substring match
            if not matched_val:
                for opt in opts:
                    if str(target_label).strip().lower() in str(opt["label"]).strip().lower():
                        matched_val = opt["value"]
                        break
            if not matched_val and opts:
                matched_val = opts[0]["value"]
                
            if matched_val is not None:
                await el.select_option(value=matched_val)
                await page.wait_for_timeout(200)
                await el.evaluate("el => el.dispatchEvent(new Event('change', { bubbles: true }))")
                return {"status": "success", "field_id": field_id, "action": "select", "verification_value": matched_val}
            else:
                raise Exception(f"No option matched target label '{target_label}' / value '{target_val}'")
        else:
            # Custom Combobox / Searchable combobox: click -> type -> wait suggestions -> click match suggestion -> dispatch change/input
            inp_el = None
            if el_tag == "input":
                inp_el = el
            else:
                inps = el.locator("input")
                if await inps.count() > 0:
                    inp_el = inps.first
            
            if inp_el:
                await inp_el.click()
                await inp_el.fill("")
                await inp_el.type(str(target_label), delay=20)
                await page.wait_for_timeout(600)
                
                suggestion_selectors = [
                    f"[role='option']:has-text('{target_label}')",
                    f"li:has-text('{target_label}')",
                    f"[role='option']",
                    f"li",
                    f"div:has-text('{target_label}')"
                ]
                clicked = False
                for sugg_sel in suggestion_selectors:
                    matching_suggs = page.locator(sugg_sel)
                    count = await matching_suggs.count()
                    for idx in range(count):
                        sugg = matching_suggs.nth(idx)
                        if await sugg.is_visible():
                            await sugg.click()
                            clicked = True
                            break
                    if clicked:
                        break
                
                if not clicked:
                    await page.keyboard.press("ArrowDown")
                    await page.keyboard.press("Enter")
                
                await el.evaluate("el => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }")
                return {"status": "success", "field_id": field_id, "action": "select", "verification_value": target_label}
            else:
                await el.click()
                return {"status": "success", "field_id": field_id, "action": "select"}

    # ── CHECK ────────────────────────────────────────────────────────────────
    if action == "check":
        el = await find_element(selector)
        if not el:
            raise Exception(f"Checkbox '{selector}' not found.")
        await el.scroll_into_view_if_needed()
        is_checked = await el.is_checked()
        if not is_checked:
            await el.click()
        return {"status": "success", "field_id": field_id, "action": "check"}

    # ── MULTI_SELECT (checkbox group) ─────────────────────────────────────────
    if action == "multi_select":
        if not selected_options:
            return {"status": "skipped", "field_id": field_id, "action": "multi_select", "reason": "No options selected"}
        checked = []
        for opt_val in selected_options:
            chk = page.locator(f'input[type="checkbox"][value="{opt_val}"]')
            if await chk.count() == 0:
                chk = page.locator(f'label:has-text("{opt_val}") input[type="checkbox"]')
            if await chk.count() > 0:
                await chk.first.scroll_into_view_if_needed()
                await chk.first.click()
                checked.append(opt_val)
        return {"status": "success", "field_id": field_id, "action": "multi_select", "verification_value": f"Checked: {checked}"}

    # ── FILL (text, email, tel, textarea, number, url, etc.) ───────────────────
    el = await find_element(selector)
    if not el:
        raise Exception(f"Element '{selector}' not found on the page.")

    el_tag = await el.evaluate("el => el.tagName.toLowerCase()")
    el_type = await el.evaluate("el => (el.getAttribute('type') || '').toLowerCase()")

    if el_tag == "select":
        raise Exception(f"Cannot fill select field '{field_id}' with text value '{value}'. Must select a valid option.")

    await el.scroll_into_view_if_needed()
    
    # Robust fill steps:
    # 1. focus
    await el.focus()
    # 2. set value
    await el.fill("")
    await el.type(str(value), delay=20)
    # 3. dispatch input & change
    await el.evaluate("el => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }")
    # 4. blur
    await el.blur()
    
    return {"status": "success", "field_id": field_id, "action": "fill", "verification_value": str(value)}


async def execute_autofill(run_id: str, target_url: str, mapping_plan: list, profile_id: str):
    from playwright.async_api import async_playwright
    import datetime
    
    async def log_and_broadcast(event_type: str, extra: dict = None):
        evt = {
            "event": event_type,
            "run_id": run_id,
            "timestamp": datetime.datetime.utcnow().isoformat()
        }
        if extra:
            evt.update(extra)
        if run_id in active_runs:
            active_runs[run_id]["events"].append(evt)
            if event_type == "run_started":
                active_runs[run_id]["status"] = "running"
            elif event_type == "run_completed":
                active_runs[run_id]["status"] = "completed"
            elif event_type in ("error", "run_cancelled"):
                active_runs[run_id]["status"] = "cancelled" if event_type == "run_cancelled" else "failed"
        await manager.broadcast(run_id, evt)

    # Begin run
    await log_and_broadcast("run_started", {"target_url": target_url})
    
    async with async_playwright() as p:
        # Launch headless — screenshots are streamed to the frontend via WebSocket
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_viewport_size({"width": 1280, "height": 900})
            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })

            logger.info(f"[Run {run_id}] Navigating to {target_url}")
            await page.goto(target_url, wait_until="load", timeout=30000)
            await page.wait_for_timeout(1500)

            await log_and_broadcast("agent_ready", {"message": "Browser is ready and waiting for field injection requests."})

            run_state = active_runs.get(run_id)
            if not run_state:
                return

            # ── Screenshot streaming task ────────────────────────────────────
            import base64
            screenshot_active = True

            async def stream_screenshots():
                while screenshot_active and not page.is_closed():
                    try:
                        png_bytes = await page.screenshot(type="jpeg", quality=70, full_page=False)
                        b64 = base64.b64encode(png_bytes).decode("utf-8")
                        await manager.broadcast(run_id, {
                            "event": "screenshot",
                            "run_id": run_id,
                            "data": b64
                        })
                    except Exception:
                        pass
                    await asyncio.sleep(0.8)

            screenshot_task = asyncio.create_task(stream_screenshots())

            # ── Main command consumer loop ───────────────────────────────────
            while not page.is_closed():
                if run_state.get("cancel_requested", False):
                    logger.info(f"[Run {run_id}] Cancel requested. Stopping.")
                    await log_and_broadcast("run_cancelled")
                    break

                try:
                    cmd = await asyncio.wait_for(run_state["queue"].get(), timeout=0.5)
                    action = cmd.get("action")
                    if action == "close":
                        logger.info(f"[Run {run_id}] Close command received. Stopping.")
                        break
                    elif action == "inject":
                        field = cmd.get("field")
                        fut = cmd.get("future")
                        try:
                            res = await inject_field_into_page(page, field, profile_id)
                            fut.set_result(res)
                        except Exception as e:
                            fut.set_exception(e)
                except asyncio.TimeoutError:
                    continue

            # Stop screenshot loop
            screenshot_active = False
            screenshot_task.cancel()

            # Complete
            await log_and_broadcast("run_completed")

            # Send final screenshot
            try:
                png_bytes = await page.screenshot(type="jpeg", quality=80, full_page=False)
                b64 = base64.b64encode(png_bytes).decode("utf-8")
                await manager.broadcast(run_id, {"event": "screenshot", "run_id": run_id, "data": b64})
            except Exception:
                pass

        except Exception as e:
            logger.error(f"[Run {run_id}] General run exception: {str(e)}")
            await log_and_broadcast("error", {"message": str(e)})
        finally:
            await browser.close()


class RunCreateRequest(BaseModel):
    form_id: str
    profile_id: str

@app.post("/api/runs")
async def create_run(req: RunCreateRequest):
    if req.form_id not in active_forms:
        raise HTTPException(status_code=404, detail="Form session not found")
    if req.profile_id not in active_profiles:
        raise HTTPException(status_code=404, detail="Profile session not found")
        
    form = active_forms[req.form_id]
    target_url = form["target_url"]
    
    if req.form_id not in active_mappings:
        raise HTTPException(status_code=404, detail="Form mapping plan not found")
        
    mapping_plan = active_mappings[req.form_id]
    
    run_id = str(uuid.uuid4())
    
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
        "mapping_plan": mapping_plan
    }
    
    # Trigger execution as background task
    asyncio.create_task(execute_autofill(run_id, target_url, mapping_plan, req.profile_id))
    
    logger.info(f"Initialized autofill run background task. Run ID: {run_id}")
    return {
        "run_id": run_id,
        "status": "started"
    }

@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail="Autofill run session not found")
    run_data = active_runs[run_id].copy()
    if "queue" in run_data:
        del run_data["queue"]
    
    # Attach detected_fields from the form session if it exists
    form_id = run_data.get("form_id")
    if form_id in active_forms:
        run_data["detected_fields"] = active_forms[form_id].get("detected_fields", [])
    else:
        run_data["detected_fields"] = []
        
    return run_data


# --- Guided Field Review: Step Injection Endpoint ---

class FieldInjectRequest(BaseModel):
    field_id: str
    selector: str
    value: Optional[str] = ""
    type: Optional[str] = "text"
    field_label: Optional[str] = None
    action: Optional[str] = "fill"
    selected_option: Optional[str] = None
    selected_options: Optional[List[str]] = []

@app.post("/api/runs/{run_id}/inject")
async def inject_run_field(run_id: str, req: FieldInjectRequest):
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail="Autofill run session not found")
    
    run_state = active_runs[run_id]
    if "queue" not in run_state:
        raise HTTPException(status_code=400, detail="Autofill run session does not have command queue initialized")

    fut = asyncio.get_running_loop().create_future()
    await run_state["queue"].put({
        "action": "inject",
        "field": req.dict(),
        "future": fut
    })

    try:
        result = await fut
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Phase 6: Run Control Endpoints ---

@app.post("/api/runs/{run_id}/pause")
async def pause_run(run_id: str):
    """
    Signals the autofill loop to pause after completing the current field.
    """
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail="Run session not found")
    run = active_runs[run_id]
    if run["status"] not in ("running",):
        raise HTTPException(status_code=400, detail=f"Cannot pause a run with status '{run['status']}'")
    active_runs[run_id]["pause_requested"] = True
    logger.info(f"[Run {run_id}] Pause requested via API.")
    return {"run_id": run_id, "action": "pause_requested"}


@app.post("/api/runs/{run_id}/resume")
async def resume_run(run_id: str):
    """
    Clears the pause flag so the autofill loop continues from current_field_index.
    """
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail="Run session not found")
    run = active_runs[run_id]
    if run["status"] not in ("paused",):
        raise HTTPException(status_code=400, detail=f"Cannot resume a run with status '{run['status']}'")
    active_runs[run_id]["pause_requested"] = False
    logger.info(f"[Run {run_id}] Resume requested via API.")
    return {"run_id": run_id, "action": "resume_requested"}


@app.post("/api/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    """
    Signals the autofill loop to stop immediately and close the browser.
    """
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail="Run session not found")
    run = active_runs[run_id]
    if run["status"] in ("completed", "cancelled", "failed"):
        raise HTTPException(status_code=400, detail=f"Run is already in terminal state '{run['status']}'")
    active_runs[run_id]["cancel_requested"] = True
    # Also clear pause so the wait loop can catch the cancel
    active_runs[run_id]["pause_requested"] = False
    logger.info(f"[Run {run_id}] Cancel requested via API.")
    return {"run_id": run_id, "action": "cancel_requested"}


@app.websocket("/ws/runs/{run_id}")
async def websocket_runs(websocket: WebSocket, run_id: str):
    await manager.connect(run_id, websocket)
    
    # Catch client up instantly
    if run_id in active_runs:
        for evt in active_runs[run_id]["events"]:
            try:
                await websocket.send_json(evt)
            except Exception:
                break
                
    try:
        while True:
            # Await text from websocket connection (keep connection alive)
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(run_id, websocket)
    except Exception as e:
        logger.error(f"WS connection closed with error: {str(e)}")
        manager.disconnect(run_id, websocket)



# ── Reverse Proxy for iframe embedding ────────────────────────────────────────

@app.api_route("/proxy", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def proxy_page(request: Request, url: str = Query(..., description="Target URL to proxy")):
    """
    Fetches the target URL, strips X-Frame-Options / CSP headers that block
    iframe embedding, and injects a <base> tag so relative URLs still resolve
    against the original domain.  This makes the form fully interactive inside
    our frontend's iframe (same-origin = full DOM access for autofill).
    """
    parsed_input = urlparse(url)
    blocked_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
    hostname = (parsed_input.hostname or "").lower()
    if parsed_input.scheme not in {"http", "https"} or not hostname:
        raise HTTPException(status_code=400, detail="Only absolute http(s) URLs can be embedded.")
    if hostname in blocked_hosts or hostname.endswith(".local"):
        raise HTTPException(status_code=400, detail="Local/private URLs cannot be proxied.")

    method = request.method
    body = await request.body()

    # Forward headers, avoiding host/connection conflicts
    forward_headers = {}
    excluded_headers = {"host", "connection", "accept-encoding", "content-length"}
    for k, v in request.headers.items():
        if k.lower() not in excluded_headers:
            forward_headers[k] = v

    # Add browser-like User-Agent and headers if not set
    if "user-agent" not in {k.lower() for k in forward_headers.keys()}:
        forward_headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    if "accept" not in {k.lower() for k in forward_headers.keys()}:
        forward_headers["Accept"] = "*/*"
    if "accept-language" not in {k.lower() for k in forward_headers.keys()}:
        forward_headers["Accept-Language"] = "en-US,en;q=0.9"

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            resp = await client.request(
                method=method,
                url=url,
                headers=forward_headers,
                content=body
            )
    except Exception as e:
        logger.error(f"Proxy fetch failed for {url}: {e}")
        accept_header = request.headers.get("accept", "")
        headers = {"Access-Control-Allow-Origin": "*"}
        if "text/html" not in accept_header:
            return Response(
                content=json.dumps({"error": "Proxy fetch failed", "details": str(e)}),
                media_type="application/json",
                status_code=502,
                headers=headers
            )
        return HTMLResponse(
            content=f"<html><body><h2>Failed to load form</h2><p>{str(e)}</p></body></html>",
            status_code=502,
            headers=headers
        )

    content_type = resp.headers.get("content-type", "")

    # Only process HTML responses
    if "text/html" not in content_type:
        response_headers = {}
        for k, v in resp.headers.items():
            if k.lower() not in {"content-length", "content-encoding", "transfer-encoding", "connection", "access-control-allow-origin"}:
                response_headers[k] = v
        response_headers["Access-Control-Allow-Origin"] = "*"
        return Response(content=resp.content, status_code=resp.status_code, headers=response_headers, media_type=content_type)

    html = resp.text

    # Inject <base href> so relative URLs (CSS, JS, images, form actions)
    # resolve against the original domain instead of localhost.
    parsed = urlparse(str(resp.url))  # use final URL after redirects
    # Build base from the directory of the current path
    path = parsed.path or "/"
    if not path.endswith("/"):
        path = path.rsplit("/", 1)[0] + "/"
    base_href = f"{parsed.scheme}://{parsed.netloc}{path}"

    base_tag = f'<base href="{base_href}">'
    history_script = (
        "<script>\n"
        "  // 1. Rewrite history pathname to match target URL path for client routers\n"
        "  try {\n"
        "    const urlParams = new URLSearchParams(window.location.search);\n"
        "    const targetUrlStr = urlParams.get('url');\n"
        "    if (targetUrlStr) {\n"
        "      const targetUrl = new URL(targetUrlStr);\n"
        "      const cleanPath = targetUrl.pathname + targetUrl.search + targetUrl.hash;\n"
        "      const absolutePath = window.location.origin + cleanPath;\n"
        "      window.history.replaceState(null, '', absolutePath);\n"
        "    }\n"
        "  } catch (e) {\n"
        "    console.error('Failed to rewrite history path:', e);\n"
        "  }\n"
        "\n"
        "  // 2. Intercept fetch & XHR to proxy relative and cross-origin requests to avoid CORS block\n"
        "  try {\n"
        "    let baseOrigin = 'https://job-boards.greenhouse.io';\n"
        "    const baseTag = document.querySelector('base');\n"
        "    if (baseTag && baseTag.href) {\n"
        "      baseOrigin = new URL(baseTag.href).origin;\n"
        "    }\n"
        "\n"
        "    function proxyUrl(url) {\n"
        "      if (!url) return url;\n"
        "      if (url.startsWith('/proxy') || url.includes('localhost') || url.includes('127.0.0.1')) {\n"
        "        return url;\n"
        "      }\n"
        "      // Only proxy external http(s) URLs or relative API paths, leave inline assets (data:, blob:) alone\n"
        "      if (url.startsWith('data:') || url.startsWith('blob:') || url.startsWith('javascript:')) {\n"
        "        return url;\n"
        "      }\n"
        "      let absoluteUrl = url;\n"
        "      if (!url.startsWith('http')) {\n"
        "        absoluteUrl = baseOrigin + (url.startsWith('/') ? '' : '/') + url;\n"
        "      }\n"
        "      // Only proxy requests targeted to external domains to avoid loops\n"
        "      if (absoluteUrl.includes(window.location.host)) {\n"
        "        return url;\n"
        "      }\n"
        "      return window.location.origin + '/proxy?url=' + encodeURIComponent(absoluteUrl);\n"
        "    }\n"
        "\n"
        "    const originalFetch = window.fetch;\n"
        "    window.fetch = function(input, init) {\n"
        "      if (!input) return originalFetch(input, init);\n"
        "      let url = typeof input === 'string' ? input : input.url;\n"
        "      let newUrl = proxyUrl(url);\n"
        "      if (newUrl !== url) {\n"
        "        if (typeof input === 'string') {\n"
        "          input = newUrl;\n"
        "        } else {\n"
        "          input = new Request(newUrl, input);\n"
        "        }\n"
        "      }\n"
        "      return originalFetch(input, init);\n"
        "    };\n"
        "\n"
        "    const originalOpen = XMLHttpRequest.prototype.open;\n"
        "    XMLHttpRequest.prototype.open = function(method, url, ...args) {\n"
        "      let newUrl = proxyUrl(url);\n"
        "      return originalOpen.call(this, method, newUrl, ...args);\n"
        "    };\n"
        "  } catch (e) {\n"
        "    console.error('Failed to initialize fetch interceptors:', e);\n"
        "  }\n"
        "</script>"
    )
    injection = base_tag + "\n" + history_script

    if '<head>' in html.lower():
        html = re.sub(r'(<head[^>]*>)', lambda m: m.group(1) + injection, html, count=1, flags=re.IGNORECASE)
    elif '<html' in html.lower():
        html = re.sub(r'(<html[^>]*>)', lambda m: m.group(1) + '<head>' + injection + '</head>', html, count=1, flags=re.IGNORECASE)
    else:
        html = injection + html

    headers = {"Access-Control-Allow-Origin": "*"}
    return HTMLResponse(content=html, headers=headers)


@app.get("/api/runs/{run_id}/resume-path")
def get_resume_path(run_id: str):
    """
    Returns the resume file path for the run's profile so the frontend
    can inform the user to manually attach it (file inputs can't be set via JS).
    """
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail="Run not found")
    profile_id = active_runs[run_id].get("profile_id")
    profile = active_profiles.get(profile_id, {})
    return {
        "resume_file_path": profile.get("resume_file_path"),
        "filename": os.path.basename(profile.get("resume_file_path", "")) if profile.get("resume_file_path") else None
    }


@app.get("/api/runs/{run_id}/resume-file")
def get_resume_file(run_id: str):
    """
    Downloads the resume file associated with the run session.
    """
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail="Run not found")
    profile_id = active_runs[run_id].get("profile_id")
    profile = active_profiles.get(profile_id, {})
    file_path = profile.get("resume_file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Resume file not found")
    
    from fastapi.responses import FileResponse
    filename = os.path.basename(file_path)
    if "_" in filename:
        filename = filename.split("_", 1)[1]
        
    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=filename,
        headers={"Access-Control-Expose-Headers": "Content-Disposition"}
    )

