import sys
import asyncio
import logging
import os

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from state import UPLOAD_DIR, active_profiles, _load_profiles_from_disk
from routes.profile import router as profile_router
from routes.form import router as form_router
from routes.run import router as run_router
from routes.proxy import router as proxy_router

# Set up logging format and levels
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("formpilot-backend")

# Load environment configuration
load_dotenv()

# Check Gemini API configuration state
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logger.warning("Gemini API key not configured. Mapper will use programmatic fallback.")
else:
    logger.info("Gemini API key loaded successfully.")

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

@app.get("/")
def read_root():
    return {
        "status": "online",
        "app": "FormPilot",
        "mode": "mock" if not GEMINI_API_KEY else "production",
        "uploads_dir": UPLOAD_DIR
    }

app.include_router(profile_router)
app.include_router(form_router)
app.include_router(run_router)
app.include_router(proxy_router)
