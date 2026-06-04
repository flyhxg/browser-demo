import os
import json
import aiofiles
from filelock import FileLock
from datetime import datetime, timezone

MEMORY_BASE = "backend/memory"
SEARCH_INDEX_PATH = os.path.join(MEMORY_BASE, "search_index.json")


def _token_path(symbol: str) -> str:
    return os.path.join(MEMORY_BASE, "tokens", f"{symbol.upper()}.json")


def _sector_path(sector: str) -> str:
    safe = "".join(c for c in sector.lower() if c.isalnum() or c in ("_", "-"))
    return os.path.join(MEMORY_BASE, "sectors", f"{safe}.json")


def _session_path(session_id: str) -> str:
    return os.path.join(MEMORY_BASE, "sessions", f"{session_id}.json")


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
        async with aiofiles.open(path, "w") as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))


def update_token_memory(symbol: str, **kwargs) -> dict:
    """Load, update, and save token memory.

    Also updates the search index so the token becomes discoverable.
    """
    memory = load_token_memory(symbol)
    memory.update(kwargs)
    memory["last_queried"] = datetime.now(timezone.utc).isoformat()
    save_token_memory(symbol, memory)
    _index_token(symbol, sectors=memory.get("related_sectors") or [])
    return memory


# ---------- Sector memory ----------


def load_sector_memory(sector: str) -> dict:
    """Load sector memory. Default shape: name + token list + notes."""
    _ensure_dirs()
    path = _sector_path(sector)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "name": sector.lower(),
        "tokens": [],
        "notes": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def save_sector_memory(sector: str, data: dict) -> None:
    _ensure_dirs()
    path = _sector_path(sector)
    lock = FileLock(f"{path}.lock")
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    with lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def add_token_to_sector(symbol: str, sector: str) -> dict:
    """Tag a token as belonging to a sector. Idempotent.

    Writes the sector file (appends the symbol) and the token file
    (appends the sector to related_sectors), then re-indexes.
    """
    data = load_sector_memory(sector)
    symbol = symbol.upper()
    if symbol not in data["tokens"]:
        data["tokens"].append(symbol)
    save_sector_memory(sector, data)

    token_data = load_token_memory(symbol)
    sectors = list(token_data.get("related_sectors") or [])
    if sector.lower() not in sectors:
        sectors.append(sector.lower())
    return update_token_memory(symbol, related_sectors=sectors)


def list_sectors() -> list[str]:
    """List all sectors that have a memory file."""
    _ensure_dirs()
    sectors_dir = os.path.join(MEMORY_BASE, "sectors")
    return sorted(
        fname[:-5] for fname in os.listdir(sectors_dir)
        if fname.endswith(".json")
    )


# ---------- Search index ----------


def _load_search_index() -> dict:
    if not os.path.exists(SEARCH_INDEX_PATH):
        return {"tokens": {}, "sectors": {}}
    try:
        with open(SEARCH_INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"tokens": {}, "sectors": {}}


def _save_search_index(index: dict) -> None:
    _ensure_dirs()
    with open(SEARCH_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


def _index_token(symbol: str, sectors: list[str]) -> None:
    """Update the search index. Best-effort; never raises."""
    try:
        index = _load_search_index()
        index.setdefault("tokens", {})[symbol.upper()] = {
            "sectors": [s.lower() for s in sectors],
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_search_index(index)
    except OSError:
        pass


def search_tokens(query: str, limit: int = 10) -> list[dict]:
    """Lightweight keyword search over indexed tokens.

    Returns a list of {symbol, sectors, score}. Score is the count of
    query words found in the symbol or its sectors. Empty query returns [].
    """
    query = (query or "").strip().lower()
    if not query:
        return []
    words = [w for w in query.split() if w]
    index = _load_search_index()
    results: list[dict] = []
    for symbol, meta in index.get("tokens", {}).items():
        haystacks = [symbol.lower()] + [s.lower() for s in meta.get("sectors", [])]
        score = sum(1 for w in words if any(w in h for h in haystacks))
        if score > 0:
            results.append({
                "symbol": symbol,
                "sectors": meta.get("sectors", []),
                "score": score,
            })
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]
