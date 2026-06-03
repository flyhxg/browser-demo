import os
import json
import aiofiles
from filelock import FileLock
from datetime import datetime, timezone

MEMORY_BASE = "backend/memory"

def _token_path(symbol: str) -> str:
    return os.path.join(MEMORY_BASE, "tokens", f"{symbol.upper()}.json")

def _ensure_dirs():
    os.makedirs(os.path.join(MEMORY_BASE, "tokens"), exist_ok=True)
    os.makedirs(os.path.join(MEMORY_BASE, "sectors"), exist_ok=True)
    os.makedirs(os.path.join(MEMORY_BASE, "sessions"), exist_ok=True)

def load_token_memory(symbol: str) -> dict:
    """Load token memory from file. Returns default structure if not found."""
    _ensure_dirs()
    path = _token_path(symbol)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "symbol": symbol.upper(),
        "first_queried": datetime.now(timezone.utc).isoformat(),
        "last_queried": datetime.now(timezone.utc).isoformat(),
        "user_interests": [],
        "key_levels": {"support": [], "resistance": []},
        "related_sectors": [],
        "notes": "",
        "analysis_history": [],
    }

def save_token_memory(symbol: str, data: dict) -> None:
    """Save token memory to file with file locking."""
    _ensure_dirs()
    path = _token_path(symbol)
    lock_path = f"{path}.lock"
    lock = FileLock(lock_path)
    with lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

async def async_save_token_memory(symbol: str, data: dict) -> None:
    """Async version of save_token_memory."""
    _ensure_dirs()
    path = _token_path(symbol)
    lock_path = f"{path}.lock"
    lock = FileLock(lock_path)
    with lock:
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))

def update_token_memory(symbol: str, **kwargs) -> dict:
    """Load, update, and save token memory."""
    memory = load_token_memory(symbol)
    memory.update(kwargs)
    memory["last_queried"] = datetime.now(timezone.utc).isoformat()
    save_token_memory(symbol, memory)
    return memory
