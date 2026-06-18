import os
import uuid
import asyncio
import logging
import base64
import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

from state import active_runs, active_forms, active_mappings, active_profiles, manager

logger = logging.getLogger("formpilot-backend")
router = APIRouter()

async def inject_field_into_page(page, field: dict, profile_id: str) -> dict:
    """
    Injects a value into a form field based on the action type.
    """
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

            screenshot_active = False
            screenshot_task.cancel()

            await log_and_broadcast("run_completed")

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

@router.post("/api/runs")
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

@router.get("/api/runs/{run_id}")
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

class FieldInjectRequest(BaseModel):
    field_id: str
    selector: str
    value: Optional[str] = ""
    type: Optional[str] = "text"
    field_label: Optional[str] = None
    action: Optional[str] = "fill"
    selected_option: Optional[str] = None
    selected_options: Optional[List[str]] = []

@router.post("/api/runs/{run_id}/inject")
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

@router.post("/api/runs/{run_id}/pause")
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

@router.post("/api/runs/{run_id}/resume")
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

@router.post("/api/runs/{run_id}/cancel")
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
    active_runs[run_id]["pause_requested"] = False
    logger.info(f"[Run {run_id}] Cancel requested via API.")
    return {"run_id": run_id, "action": "cancel_requested"}

@router.websocket("/ws/runs/{run_id}")
async def websocket_runs(websocket: WebSocket, run_id: str):
    await manager.connect(run_id, websocket)
    
    if run_id in active_runs:
        for evt in active_runs[run_id]["events"]:
            try:
                await websocket.send_json(evt)
            except Exception:
                break
                
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(run_id, websocket)
    except Exception as e:
        logger.error(f"WS connection closed with error: {str(e)}")
        manager.disconnect(run_id, websocket)

@router.get("/api/runs/{run_id}/resume-path")
def get_resume_path(run_id: str):
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail="Run not found")
    profile_id = active_runs[run_id].get("profile_id")
    profile = active_profiles.get(profile_id, {})
    return {
        "resume_file_path": profile.get("resume_file_path"),
        "filename": os.path.basename(profile.get("resume_file_path", "")) if profile.get("resume_file_path") else None
    }

@router.get("/api/runs/{run_id}/resume-file")
def get_resume_file(run_id: str):
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail="Run not found")
    profile_id = active_runs[run_id].get("profile_id")
    profile = active_profiles.get(profile_id, {})
    file_path = profile.get("resume_file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Resume file not found")
    
    filename = os.path.basename(file_path)
    if "_" in filename:
        filename = filename.split("_", 1)[1]
        
    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=filename,
        headers={"Access-Control-Expose-Headers": "Content-Disposition"}
    )
