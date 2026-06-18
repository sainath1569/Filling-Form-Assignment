import os
import json
import logging
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger("formpilot-backend")

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
